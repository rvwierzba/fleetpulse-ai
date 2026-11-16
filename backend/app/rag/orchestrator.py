"""Hybrid RAG orchestrator unifying Semantic Cache, Neo4j Graph, and pgvector search."""

import logging
from typing import Any

import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import AsyncSession

from app.rag.graph_service import GraphService, get_graph_service
from app.rag.schemas import HybridRAGResult
from app.rag.semantic_cache import SemanticCache, get_semantic_cache
from app.rag.vector_service import VectorService, get_vector_service

logger = logging.getLogger(__name__)


class HybridRAGOrchestrator:
    """Orchestrates 3-tier retrieval: Semantic Cache -> Neo4j Knowledge Graph -> pgvector."""

    def __init__(
        self,
        graph_service: GraphService | None = None,
        vector_service: VectorService | None = None,
        semantic_cache: SemanticCache | None = None,
    ) -> None:
        self.graph = graph_service or get_graph_service()
        self.vector = vector_service or get_vector_service()
        self.cache = semantic_cache or get_semantic_cache()

    async def enrich_alert_context(
        self,
        session: AsyncSession,
        redis_client: aioredis.Redis,
        device_type: str,
        model_code: str,
        batch_id: str,
        firmware_version: str,
        error_code: str,
        subsystem: str,
        description: str = "",
        telemetry: dict[str, Any] | None = None,
    ) -> HybridRAGResult:
        """Enrich fleet alert with diagnostic context, checking cache before querying graph/vectors."""
        signature = self.cache.compute_signature(
            device_type=device_type,
            model_code=model_code,
            firmware_version=firmware_version,
            subsystem=subsystem,
            error_code=error_code,
        )
        query_text = (
            f"Device {device_type} {model_code} Batch {batch_id} Firmware {firmware_version} "
            f"Subsystem {subsystem} Error {error_code}: {description}"
        ).strip()

        # Tier 1 & 2: Check Semantic Cache (Redis L1 + pgvector L2)
        cached_data, cache_type = await self.cache.get(
            session=session,
            redis_client=redis_client,
            signature=signature,
            query_text=query_text,
        )
        if cached_data:
            result = HybridRAGResult.model_validate(cached_data)
            result.cache_hit = True
            result.cache_type = cache_type
            return result

        # Tier 3: Query Neo4j Knowledge Graph for deterministic topology context
        graph_context = await self.graph.get_graph_context(
            device_type=device_type,
            model_code=model_code,
            batch_id=batch_id,
            firmware_version=firmware_version,
            error_code=error_code,
            subsystem=subsystem,
        )

        # Tier 4: Query pgvector for semantic excerpts in manuals and bulletins
        vector_docs = await self.vector.search_documents(
            session=session,
            query_text=f"{error_code} {description} {subsystem}",
            device_type=device_type,
            subsystem=subsystem,
            limit=3,
        )

        # Synthesize human-readable diagnostic context
        matched_rb_id = (
            graph_context.matched_runbook.runbook_id if graph_context.matched_runbook else None
        )
        matched_tb_id = (
            graph_context.active_bulletins[0].bulletin_id
            if graph_context.active_bulletins
            else None
        )

        lines = [
            f"=== CONTEXTO DE DIAGNÓSTICO FLEETPULSE ({device_type} - {model_code}) ===",
            f"• Lote: {batch_id} (Dispositivos afetados correlatos: {graph_context.batch_failure_count})",
            f"• Firmware: {firmware_version} | Subsistema: {subsystem} | Código de Erro: {error_code}",
        ]
        if graph_context.active_bulletins:
            lines.append("• Boletins de Engenharia Ativos:")
            for b in graph_context.active_bulletins:
                lines.append(f"  - [{b.bulletin_id}] ({b.severity}) {b.title}: {b.summary}")
        if graph_context.matched_runbook:
            rb = graph_context.matched_runbook
            approval_str = " (Requer Aprovação Humana)" if rb.requires_human_approval else ""
            lines.append(f"• Runbook Recomendado: [{rb.runbook_id}] {rb.title}{approval_str}")
            lines.append(f"  - SLA Alvo: {rb.sla_target_hours}h")
            for idx, step in enumerate(rb.steps, start=1):
                lines.append(f"    {idx}. {step}")
        if vector_docs:
            lines.append("• Trechos Relevantes da Base de Conhecimento (Busca Vetorial):")
            for doc in vector_docs:
                lines.append(
                    f"  - [{doc.doc_id}] {doc.title} (Similaridade: {doc.similarity_score:.2f})"
                )
                lines.append(f'    "{doc.content[:180]}..."')

        synthesized_text = "\n".join(lines)

        result = HybridRAGResult(
            cache_hit=False,
            cache_type=None,
            graph_context=graph_context,
            vector_documents=vector_docs,
            synthesized_context=synthesized_text,
            matched_runbook_id=matched_rb_id,
            matched_bulletin_id=matched_tb_id,
        )

        # Save into Semantic Cache for subsequent identical/similar alerts
        await self.cache.put(
            session=session,
            redis_client=redis_client,
            signature=signature,
            query_text=query_text,
            response_data=result.model_dump(),
        )

        return result


_hybrid_rag_orchestrator: HybridRAGOrchestrator | None = None


def get_hybrid_rag_orchestrator() -> HybridRAGOrchestrator:
    """Return singleton HybridRAGOrchestrator."""
    global _hybrid_rag_orchestrator
    if _hybrid_rag_orchestrator is None:
        _hybrid_rag_orchestrator = HybridRAGOrchestrator()
    return _hybrid_rag_orchestrator
