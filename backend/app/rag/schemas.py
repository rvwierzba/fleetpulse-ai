"""Pydantic schemas for Hybrid RAG retrieval, knowledge graph context, and semantic cache."""

from pydantic import BaseModel, Field


class RunbookSummary(BaseModel):
    """Structured resolution runbook linked to hardware and errors."""

    runbook_id: str
    title: str
    sla_target_hours: int = 4
    steps: list[str] = Field(default_factory=list)
    requires_human_approval: bool = False


class TechBulletinSummary(BaseModel):
    """Engineering technical bulletin for batches, firmwares, or component defects."""

    bulletin_id: str
    title: str
    severity: str = "MEDIUM"
    summary: str = ""
    affected_batches: list[str] = Field(default_factory=list)
    affected_firmwares: list[str] = Field(default_factory=list)


class DocumentChunk(BaseModel):
    """Semantic document chunk retrieved from pgvector."""

    doc_id: str
    title: str
    doc_type: str
    subsystem: str
    content: str
    similarity_score: float = 0.0


class GraphContext(BaseModel):
    """Structured entities retrieved from Neo4j knowledge graph."""

    device_type: str
    model_code: str
    batch_id: str
    firmware_version: str
    error_code: str
    subsystem: str
    matched_runbook: RunbookSummary | None = None
    active_bulletins: list[TechBulletinSummary] = Field(default_factory=list)
    batch_failure_count: int = 0


class HybridRAGResult(BaseModel):
    """Unified context combining semantic cache, graph traversal, and vector search."""

    cache_hit: bool = False
    cache_type: str | None = None
    graph_context: GraphContext
    vector_documents: list[DocumentChunk] = Field(default_factory=list)
    synthesized_context: str = ""
    matched_runbook_id: str | None = None
    matched_bulletin_id: str | None = None
