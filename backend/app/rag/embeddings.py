"""Embedding client for local Ollama nomic-embed-text with deterministic fallback."""

import hashlib
import logging
from typing import Any

import httpx
import numpy as np

from app.infra.config import get_settings

logger = logging.getLogger(__name__)


class EmbeddingService:
    """Generates 768-dimensional vector embeddings via Ollama nomic-embed-text."""

    def __init__(
        self,
        base_url: str | None = None,
        model_name: str | None = None,
        dim: int | None = None,
        timeout_seconds: float = 5.0,
    ) -> None:
        settings = get_settings()
        self.base_url = (base_url or settings.ollama_base_url).rstrip("/")
        self.model_name = model_name or settings.embedding_model
        self.dim = dim or settings.embedding_dim
        self.timeout_seconds = timeout_seconds

    def _deterministic_fallback(self, text: str) -> list[float]:
        """Generate a deterministic normalized unit vector when Ollama is offline."""
        seed = int(hashlib.sha256(text.encode("utf-8")).hexdigest()[:8], 16)
        rng = np.random.default_rng(seed)
        vec = rng.standard_normal(self.dim).astype(np.float32)
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec = vec / norm
        return vec.tolist()

    async def get_embedding(self, text: str) -> list[float]:
        """Fetch embedding for a text string, falling back cleanly if offline."""
        if not text.strip():
            return [0.0] * self.dim

        endpoint = f"{self.base_url}/api/embeddings"
        payload: dict[str, Any] = {
            "model": self.model_name,
            "prompt": text,
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.post(endpoint, json=payload)
                if response.status_code == 200:
                    data = response.json()
                    embedding = data.get("embedding")
                    if embedding and len(embedding) == self.dim:
                        return [float(x) for x in embedding]
                logger.warning(
                    "Ollama returned HTTP %d for embedding. Using deterministic fallback.",
                    response.status_code,
                )
        except Exception as exc:
            logger.debug(
                "Ollama embeddings endpoint %s unavailable (%s). Using deterministic fallback.",
                endpoint,
                exc,
            )

        return self._deterministic_fallback(text)

    async def get_embeddings(self, texts: list[str]) -> list[list[float]]:
        """Batch embedding generation."""
        return [await self.get_embedding(t) for t in texts]


_embedding_service: EmbeddingService | None = None


def get_embedding_service() -> EmbeddingService:
    """Return singleton EmbeddingService."""
    global _embedding_service
    if _embedding_service is None:
        _embedding_service = EmbeddingService()
    return _embedding_service
