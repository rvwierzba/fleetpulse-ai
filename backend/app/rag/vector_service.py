"""Vector search service using PostgreSQL pgvector extension and nomic-embed-text."""

import logging
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infra.database import TechDocumentRecord
from app.rag.embeddings import EmbeddingService, get_embedding_service
from app.rag.schemas import DocumentChunk

logger = logging.getLogger(__name__)


class VectorService:
    """Manages document chunk indexing and semantic vector search in PostgreSQL."""

    def __init__(self, embedding_service: EmbeddingService | None = None) -> None:
        self.embedding_service = embedding_service or get_embedding_service()

    async def insert_document(
        self,
        session: AsyncSession,
        doc_id: str,
        title: str,
        doc_type: str,
        device_type: str,
        subsystem: str,
        content: str,
        doc_metadata: dict[str, Any] | None = None,
        embedding: list[float] | None = None,
    ) -> TechDocumentRecord:
        """Insert or update a technical document with its vector embedding."""
        if embedding is None:
            embedding = await self.embedding_service.get_embedding(f"{title}\n{content}")

        existing = await session.scalar(
            select(TechDocumentRecord).where(TechDocumentRecord.doc_id == doc_id)
        )
        if existing:
            existing.title = title
            existing.doc_type = doc_type
            existing.device_type = device_type
            existing.subsystem = subsystem
            existing.content = content
            existing.doc_metadata = doc_metadata or {}
            existing.embedding = embedding
            await session.commit()
            return existing

        doc = TechDocumentRecord(
            id=uuid4(),
            doc_id=doc_id,
            title=title,
            doc_type=doc_type,
            device_type=device_type,
            subsystem=subsystem,
            content=content,
            doc_metadata=doc_metadata or {},
            embedding=embedding,
        )
        session.add(doc)
        await session.commit()
        return doc

    async def search_documents(
        self,
        session: AsyncSession,
        query_text: str,
        device_type: str | None = None,
        subsystem: str | None = None,
        limit: int = 3,
        threshold: float = 0.50,
    ) -> list[DocumentChunk]:
        """Perform semantic similarity search using pgvector cosine distance (<=>)."""
        query_vector = await self.embedding_service.get_embedding(query_text)
        distance_expr = TechDocumentRecord.embedding.cosine_distance(query_vector)

        stmt = select(
            TechDocumentRecord,
            distance_expr.label("distance"),
        )

        if device_type:
            stmt = stmt.where(TechDocumentRecord.device_type == device_type)
        if subsystem:
            stmt = stmt.where(TechDocumentRecord.subsystem == subsystem)

        stmt = stmt.order_by(distance_expr.asc()).limit(limit)

        results = await session.execute(stmt)
        chunks: list[DocumentChunk] = []

        for row in results.all():
            doc: TechDocumentRecord = row[0]
            dist: float = float(row[1]) if row[1] is not None else 1.0
            similarity = max(0.0, min(1.0, 1.0 - dist))

            if similarity >= threshold:
                chunks.append(
                    DocumentChunk(
                        doc_id=doc.doc_id,
                        title=doc.title,
                        doc_type=doc.doc_type,
                        subsystem=doc.subsystem,
                        content=doc.content,
                        similarity_score=round(similarity, 4),
                    )
                )

        return chunks


_vector_service: VectorService | None = None


def get_vector_service() -> VectorService:
    """Return singleton VectorService."""
    global _vector_service
    if _vector_service is None:
        _vector_service = VectorService()
    return _vector_service
