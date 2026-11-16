"""Two-level semantic cache: Redis L1 for exact keys and pgvector L2 for cosine similarity."""

import hashlib
import json
import logging
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import redis.asyncio as aioredis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infra.config import get_settings
from app.infra.database import SemanticCacheRecord
from app.rag.embeddings import EmbeddingService, get_embedding_service

logger = logging.getLogger(__name__)


class SemanticCache:
    """Combines sub-millisecond Redis L1 cache with pgvector cosine similarity L2 cache."""

    def __init__(
        self,
        embedding_service: EmbeddingService | None = None,
        threshold: float | None = None,
        default_ttl_seconds: int | None = None,
    ) -> None:
        settings = get_settings()
        self.embedding_service = embedding_service or get_embedding_service()
        self.threshold = threshold or settings.semantic_cache_threshold
        self.default_ttl = default_ttl_seconds or settings.semantic_cache_ttl_seconds

    @staticmethod
    def compute_signature(
        device_type: str,
        model_code: str,
        firmware_version: str,
        subsystem: str,
        error_code: str,
    ) -> str:
        """Create a deterministic signature key for fleet alert context."""
        return (
            f"{device_type.upper()}:{model_code.upper()}:{firmware_version.upper()}:"
            f"{subsystem.upper()}:{error_code.upper()}"
        )

    async def get(
        self,
        session: AsyncSession,
        redis_client: aioredis.Redis,
        signature: str,
        query_text: str,
    ) -> tuple[dict[str, Any] | None, str | None]:
        """Check L1 Redis cache first, then L2 pgvector cosine similarity (>= threshold)."""
        # 1. Level 1: Redis Exact Match
        redis_key = f"fleetpulse:semcache:l1:{hashlib.sha256(signature.encode()).hexdigest()}"
        try:
            cached_raw = await redis_client.get(redis_key)
            if cached_raw:
                logger.debug("Semantic Cache L1 HIT (Redis): %s", signature)
                return json.loads(cached_raw), "redis_l1"
        except Exception as exc:
            logger.debug("Redis L1 cache read error: %s", exc)

        # 2. Level 2: pgvector Cosine Distance in PostgreSQL
        try:
            query_vector = await self.embedding_service.get_embedding(query_text)
            distance_expr = SemanticCacheRecord.embedding.cosine_distance(query_vector)

            cutoff_time = datetime.now(UTC) - timedelta(seconds=self.default_ttl)
            stmt = (
                select(SemanticCacheRecord, distance_expr.label("distance"))
                .where(SemanticCacheRecord.created_at >= cutoff_time)
                .order_by(distance_expr.asc())
                .limit(1)
            )

            res = await session.execute(stmt)
            row = res.first()
            if row:
                record: SemanticCacheRecord = row[0]
                dist: float = float(row[1]) if row[1] is not None else 1.0
                similarity = max(0.0, min(1.0, 1.0 - dist))

                if similarity >= self.threshold:
                    logger.info(
                        "Semantic Cache L2 HIT (pgvector): similarity=%.4f (threshold=%.2f)",
                        similarity,
                        self.threshold,
                    )
                    # Re-populate L1 cache for subsequent identical requests
                    try:
                        await redis_client.set(
                            redis_key,
                            json.dumps(record.response_data),
                            ex=self.default_ttl,
                        )
                    except Exception:
                        pass
                    return record.response_data, "pgvector_l2"
        except Exception as exc:
            logger.warning("pgvector L2 cache lookup error: %s", exc)

        return None, None

    async def put(
        self,
        session: AsyncSession,
        redis_client: aioredis.Redis,
        signature: str,
        query_text: str,
        response_data: dict[str, Any],
        ttl_seconds: int | None = None,
    ) -> None:
        """Store enriched diagnostic context in both Redis L1 and pgvector L2."""
        ttl = ttl_seconds or self.default_ttl
        cache_key = hashlib.sha256(f"{signature}:{query_text}".encode()).hexdigest()[:64]

        # 1. Store in Redis L1
        redis_key = f"fleetpulse:semcache:l1:{hashlib.sha256(signature.encode()).hexdigest()}"
        try:
            await redis_client.set(redis_key, json.dumps(response_data), ex=ttl)
        except Exception as exc:
            logger.debug("Redis L1 cache write error: %s", exc)

        # 2. Store in pgvector L2
        try:
            embedding = await self.embedding_service.get_embedding(query_text)
            cache_entry = SemanticCacheRecord(
                id=uuid4(),
                cache_key=cache_key,
                signature=signature,
                query_text=query_text,
                embedding=embedding,
                response_data=response_data,
                ttl_seconds=ttl,
                created_at=datetime.now(UTC),
            )
            session.add(cache_entry)
            await session.commit()
        except Exception as exc:
            logger.warning("pgvector L2 cache write error: %s", exc)


_semantic_cache: SemanticCache | None = None


def get_semantic_cache() -> SemanticCache:
    """Return singleton SemanticCache."""
    global _semantic_cache
    if _semantic_cache is None:
        _semantic_cache = SemanticCache()
    return _semantic_cache
