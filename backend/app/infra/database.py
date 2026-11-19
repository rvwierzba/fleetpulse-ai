"""Async PostgreSQL engine, ORM models for alerts/events, and state machine repository."""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from pgvector.sqlalchemy import Vector
from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text, Uuid, select, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from app.domain.enums import AlertStatus, can_transition
from app.domain.schemas import AlertCreateRequest, AlertStreamEvent


class AlertNotFoundError(LookupError):
    """Raised when an alert ID does not exist in PostgreSQL."""


class InvalidStateTransitionError(ValueError):
    """Raised when a state machine transition violates VALID_TRANSITIONS."""


def utc_now() -> datetime:
    """Return current timezone-aware UTC timestamp."""
    return datetime.now(UTC)


class Base(DeclarativeBase):
    """Base class for SQLAlchemy ORM models."""


class AlertRecord(Base):
    """Current snapshot and attributes of an ingested fleet alert."""

    __tablename__ = "alerts"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    idempotency_key: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    source_id: Mapped[str] = mapped_column(String(100), index=True)
    device_id: Mapped[str] = mapped_column(String(100), index=True)
    device_type: Mapped[str] = mapped_column(String(32))
    model_code: Mapped[str] = mapped_column(String(100))
    batch_id: Mapped[str] = mapped_column(String(100), index=True)
    firmware_version: Mapped[str] = mapped_column(String(64))
    sla_tier: Mapped[str] = mapped_column(String(32))
    age_days: Mapped[int] = mapped_column(Integer)
    subsystem: Mapped[str] = mapped_column(String(32))
    error_code: Mapped[str] = mapped_column(String(64), index=True)
    description: Mapped[str] = mapped_column(String(2000), default="")
    telemetry: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    current_status: Mapped[str] = mapped_column(
        String(32), default=AlertStatus.RECEIVED.value, index=True
    )
    rma_risk_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    sla_breach_risk: Mapped[float | None] = mapped_column(Float, nullable=True)
    predicted_subsystem: Mapped[str | None] = mapped_column(String(32), nullable=True)
    shap_factors: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON, nullable=True)
    rag_context: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    matched_runbook_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    matched_bulletin_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    semantic_cache_hit: Mapped[bool | None] = mapped_column(nullable=True, default=False)
    agent_diagnosis: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    triage_action: Mapped[str | None] = mapped_column(String(64), nullable=True)
    agent_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    requires_human_approval: Mapped[bool | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )
    events: Mapped[list["AlertEventRecord"]] = relationship(
        back_populates="alert", cascade="all, delete-orphan"
    )


class AlertEventRecord(Base):
    """Immutable audit trail of state machine transitions for each alert."""

    __tablename__ = "alert_events"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    alert_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("alerts.id"), index=True)
    from_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    to_status: Mapped[str] = mapped_column(String(32), index=True)
    reason: Mapped[str] = mapped_column(String(255), default="")
    event_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    alert: Mapped[AlertRecord] = relationship(back_populates="events")


class TechDocumentRecord(Base):
    """Technical bulletins, service manuals, and post-mortems indexed with pgvector."""

    __tablename__ = "tech_documents"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    doc_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(255))
    doc_type: Mapped[str] = mapped_column(String(64), index=True)
    device_type: Mapped[str] = mapped_column(String(32), index=True)
    subsystem: Mapped[str] = mapped_column(String(32), index=True)
    content: Mapped[str] = mapped_column(Text)
    doc_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    embedding: Mapped[Any] = mapped_column(Vector(768))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class SemanticCacheRecord(Base):
    """Semantic cache entries storing embeddings and cached diagnostic enrichments."""

    __tablename__ = "semantic_cache_entries"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    cache_key: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    signature: Mapped[str] = mapped_column(String(255), index=True)
    query_text: Mapped[str] = mapped_column(Text)
    embedding: Mapped[Any] = mapped_column(Vector(768))
    response_data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    ttl_seconds: Mapped[int] = mapped_column(Integer, default=3600)


def create_db_engine(database_url: str, timeout_seconds: float = 5.0) -> AsyncEngine:
    """Create an async SQLAlchemy engine with explicit asyncpg connection timeouts."""
    return create_async_engine(
        database_url,
        pool_pre_ping=True,
        connect_args={
            "timeout": timeout_seconds,
            "command_timeout": timeout_seconds,
        },
    )


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Create a session factory configured for non-expiring async commits."""
    return async_sessionmaker(bind=engine, expire_on_commit=False)


async def init_db(engine: AsyncEngine) -> None:
    """Create missing relational tables on application startup and ensure ML and RAG columns exist."""
    async with engine.begin() as conn:
        if engine.dialect.name == "postgresql":
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
        await conn.run_sync(Base.metadata.create_all)
        if engine.dialect.name == "postgresql":
            alter_statements = [
                "ALTER TABLE alerts ADD COLUMN IF NOT EXISTS rma_risk_score DOUBLE PRECISION;",
                "ALTER TABLE alerts ADD COLUMN IF NOT EXISTS sla_breach_risk DOUBLE PRECISION;",
                "ALTER TABLE alerts ADD COLUMN IF NOT EXISTS predicted_subsystem VARCHAR(32);",
                "ALTER TABLE alerts ADD COLUMN IF NOT EXISTS shap_factors JSONB;",
                "ALTER TABLE alerts ADD COLUMN IF NOT EXISTS rag_context JSONB;",
                "ALTER TABLE alerts ADD COLUMN IF NOT EXISTS matched_runbook_id VARCHAR(64);",
                "ALTER TABLE alerts ADD COLUMN IF NOT EXISTS matched_bulletin_id VARCHAR(64);",
                "ALTER TABLE alerts ADD COLUMN IF NOT EXISTS semantic_cache_hit BOOLEAN DEFAULT FALSE;",
                "ALTER TABLE alerts ADD COLUMN IF NOT EXISTS agent_diagnosis JSONB;",
                "ALTER TABLE alerts ADD COLUMN IF NOT EXISTS triage_action VARCHAR(64);",
                "ALTER TABLE alerts ADD COLUMN IF NOT EXISTS agent_confidence DOUBLE PRECISION;",
                "ALTER TABLE alerts ADD COLUMN IF NOT EXISTS requires_human_approval BOOLEAN;",
            ]
            for stmt in alter_statements:
                await conn.execute(text(stmt))


async def ping_db(engine: AsyncEngine) -> bool:
    """Verify PostgreSQL connectivity via a lightweight SELECT 1 query."""
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except SQLAlchemyError:
        return False


def to_stream_event(event: AlertEventRecord) -> AlertStreamEvent:
    """Convert an AlertEventRecord ORM row into the SSE/API event schema."""
    return AlertStreamEvent(
        event_id=event.id,
        alert_id=event.alert_id,
        from_status=AlertStatus(event.from_status) if event.from_status else None,
        to_status=AlertStatus(event.to_status),
        reason=event.reason,
        metadata=event.event_metadata or {},
        created_at=event.created_at,
    )


async def create_alert_with_received_event(
    session: AsyncSession,
    payload: AlertCreateRequest,
    idempotency_key: str,
) -> tuple[AlertRecord, AlertEventRecord | None, bool]:
    """Persist an alert in RECEIVED state alongside its initial audit event.

    Returns (record, initial_event, already_existed). Concurrent replays with
    the same idempotency_key are caught by the unique constraint.
    """
    now = utc_now()
    alert = AlertRecord(
        id=uuid4(),
        idempotency_key=idempotency_key,
        source_id=payload.source_id,
        device_id=payload.device_id,
        device_type=payload.device_type.value,
        model_code=payload.model_code,
        batch_id=payload.batch_id,
        firmware_version=payload.firmware_version,
        sla_tier=payload.sla_tier.value,
        age_days=payload.age_days,
        subsystem=payload.subsystem.value,
        error_code=payload.error_code,
        description=payload.description,
        telemetry=payload.telemetry.model_dump(),
        current_status=AlertStatus.RECEIVED.value,
        created_at=now,
        updated_at=now,
    )
    event = AlertEventRecord(
        id=uuid4(),
        alert_id=alert.id,
        from_status=None,
        to_status=AlertStatus.RECEIVED.value,
        reason="Ingested via POST /v1/alerts",
        event_metadata={"source_id": payload.source_id},
        created_at=now,
    )

    session.add(alert)
    try:
        # Flush parent alert before inserting child event so FK order is deterministic.
        await session.flush()
        session.add(event)
        await session.commit()
        return alert, event, False
    except IntegrityError:
        await session.rollback()
        existing = await session.scalar(
            select(AlertRecord).where(AlertRecord.idempotency_key == idempotency_key)
        )
        if existing is None:
            raise
        return existing, None, True


async def transition_alert_state(
    session: AsyncSession,
    alert_id: UUID,
    target_status: AlertStatus,
    reason: str,
    metadata: dict[str, Any] | None = None,
) -> AlertEventRecord:
    """Validate and persist a state transition + immutable audit event."""
    alert = await session.get(AlertRecord, alert_id)
    if alert is None:
        raise AlertNotFoundError(f"Alert {alert_id} not found")

    current_status = AlertStatus(alert.current_status)
    if not can_transition(current_status, target_status):
        raise InvalidStateTransitionError(
            f"Invalid transition {current_status.value} -> {target_status.value}"
        )

    now = utc_now()
    alert.current_status = target_status.value
    alert.updated_at = now

    if metadata:
        if "rma_risk_score" in metadata and metadata["rma_risk_score"] is not None:
            alert.rma_risk_score = float(metadata["rma_risk_score"])
        if "sla_breach_risk" in metadata and metadata["sla_breach_risk"] is not None:
            alert.sla_breach_risk = float(metadata["sla_breach_risk"])
        if "predicted_subsystem" in metadata and metadata["predicted_subsystem"] is not None:
            alert.predicted_subsystem = str(metadata["predicted_subsystem"])
        if "shap_factors" in metadata and metadata["shap_factors"] is not None:
            alert.shap_factors = metadata["shap_factors"]
        if "rag_context" in metadata and metadata["rag_context"] is not None:
            alert.rag_context = metadata["rag_context"]
        if "matched_runbook_id" in metadata and metadata["matched_runbook_id"] is not None:
            alert.matched_runbook_id = str(metadata["matched_runbook_id"])
        if "matched_bulletin_id" in metadata and metadata["matched_bulletin_id"] is not None:
            alert.matched_bulletin_id = str(metadata["matched_bulletin_id"])
        if "semantic_cache_hit" in metadata and metadata["semantic_cache_hit"] is not None:
            alert.semantic_cache_hit = bool(metadata["semantic_cache_hit"])
        if "agent_diagnosis" in metadata and metadata["agent_diagnosis"] is not None:
            alert.agent_diagnosis = metadata["agent_diagnosis"]
        if "triage_action" in metadata and metadata["triage_action"] is not None:
            alert.triage_action = str(metadata["triage_action"])
        if "agent_confidence" in metadata and metadata["agent_confidence"] is not None:
            alert.agent_confidence = float(metadata["agent_confidence"])
        if "requires_human_approval" in metadata and metadata["requires_human_approval"] is not None:
            alert.requires_human_approval = bool(metadata["requires_human_approval"])

    event = AlertEventRecord(
        id=uuid4(),
        alert_id=alert.id,
        from_status=current_status.value,
        to_status=target_status.value,
        reason=reason,
        event_metadata=metadata or {},
        created_at=now,
    )
    session.add(event)
    await session.commit()
    return event


async def get_alert_with_events(
    session: AsyncSession,
    alert_id: UUID,
) -> tuple[AlertRecord, list[AlertEventRecord]] | None:
    """Fetch an alert and its chronological state transition history."""
    alert = await session.get(AlertRecord, alert_id)
    if alert is None:
        return None

    result = await session.scalars(
        select(AlertEventRecord)
        .where(AlertEventRecord.alert_id == alert_id)
        .order_by(AlertEventRecord.created_at.asc())
    )
    return alert, list(result.all())


async def list_recent_alerts(
    session: AsyncSession,
    limit: int = 50,
    offset: int = 0,
    status_filter: str | None = None,
) -> list[tuple[AlertRecord, list[AlertEventRecord]]]:
    """Fetch paginated alerts alongside their chronological events."""
    stmt = select(AlertRecord).order_by(AlertRecord.created_at.desc())
    if status_filter:
        stmt = stmt.where(AlertRecord.current_status == status_filter)
    stmt = stmt.limit(limit).offset(offset)
    alerts = list((await session.scalars(stmt)).all())

    results: list[tuple[AlertRecord, list[AlertEventRecord]]] = []
    for alert in alerts:
        event_stmt = (
            select(AlertEventRecord)
            .where(AlertEventRecord.alert_id == alert.id)
            .order_by(AlertEventRecord.created_at.asc())
        )
        events = list((await session.scalars(event_stmt)).all())
        results.append((alert, events))
    return results


async def get_system_metrics_summary(session: AsyncSession) -> dict[str, Any]:
    """Calculate aggregate counts across alerts table."""
    all_alerts = list((await session.scalars(select(AlertRecord))).all())
    status_counts: dict[str, int] = {}
    high_rma = 0
    human_review = 0
    cache_hits = 0

    for a in all_alerts:
        status_counts[a.current_status] = status_counts.get(a.current_status, 0) + 1
        if a.rma_risk_score and a.rma_risk_score >= 0.70:
            high_rma += 1
        if a.current_status == AlertStatus.HUMAN_REVIEW.value:
            human_review += 1
        if a.semantic_cache_hit:
            cache_hits += 1

    total = len(all_alerts)
    hit_rate = (cache_hits / total) if total > 0 else 0.0

    return {
        "total_alerts": total,
        "alerts_by_status": status_counts,
        "high_rma_alerts": high_rma,
        "pending_human_review": human_review,
        "semantic_cache_hit_rate": round(hit_rate, 4),
    }
