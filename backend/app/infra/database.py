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


async def seed_simulated_fleet_alerts(
    session: AsyncSession,
) -> list[tuple[AlertRecord, list[AlertEventRecord]]]:
    """Generate realistic industrial fleet alerts for live demonstration and telemetry auditing."""
    scenarios = [
        {
            "device_id": "NOTEBOOK-THINKPAD-T14-7429",
            "device_type": "NOTEBOOK",
            "model_code": "LENOVO-21AH001RUS",
            "batch_id": "BATCH-2024-Q1-T14",
            "firmware_version": "1.42.0",
            "sla_tier": "PLATINUM",
            "age_days": 420,
            "subsystem": "BATTERY_POWER",
            "error_code": "BATT_THERMAL_RUNAWAY",
            "description": "Temperatura da célula térmica atingiu 82.4°C sob carga rápida contínua. Ciclo de degradação acelerado.",
            "telemetry": {"cycle_count": 924, "operating_temp_c": 82.4, "voltage_mv": 12800, "firmware_age_days": 380},
            "current_status": AlertStatus.HUMAN_REVIEW.value,
            "rma_risk_score": 0.88,
            "sla_breach_risk": 0.72,
            "predicted_subsystem": "BATTERY_POWER",
            "shap_factors": [
                {"feature": "cycle_count", "importance": 0.38, "value": 924},
                {"feature": "operating_temp_c", "importance": 0.31, "value": 82.4},
                {"feature": "firmware_age_days", "importance": 0.15, "value": 380},
                {"feature": "device_age_days", "importance": 0.08, "value": 420},
            ],
            "rag_context": {
                "bulletin_id": "TB-2024-BATT-09",
                "title": "Degradação crítica em células Li-Ion sob carregamento rápido",
                "graph_lineage": ["ThinkPad T14", "Firmware 1.42.0", "Battery Subsystem", "Thermal Runaway", "RMA Bulletin #09"],
            },
            "matched_runbook_id": "RB-BATT-REPLACE-01",
            "matched_bulletin_id": "TB-2024-BATT-09",
            "semantic_cache_hit": True,
            "agent_confidence": 0.94,
            "requires_human_approval": True,
            "triage_action": "OPERATOR_DISPATCH_RMA",
            "agent_diagnosis": {
                "summary": "Alto risco de inchaço de célula térmica. Recomendada substituição imediata da bateria via suporte N2.",
                "protocol": "PROTO_RMA_EXPEDITED",
                "safety_action": "LIMIT_CHARGING_50PCT",
            },
        },
        {
            "device_id": "NOTEBOOK-MBP-M2-3108",
            "device_type": "NOTEBOOK",
            "model_code": "APPLE-A2779-M2",
            "batch_id": "BATCH-2023-Q4-M2",
            "firmware_version": "14.5.1",
            "sla_tier": "GOLD",
            "age_days": 210,
            "subsystem": "STORAGE_NVME",
            "error_code": "NVME_SECTOR_CORRUPTION",
            "description": "Múltiplos blocos I/O ilegíveis detectados no barramento PCIe durante paginação de kernel.",
            "telemetry": {"cycle_count": 180, "operating_temp_c": 54.0, "nvme_errors": 1420, "wear_level_pct": 74},
            "current_status": AlertStatus.HUMAN_REVIEW.value,
            "rma_risk_score": 0.76,
            "sla_breach_risk": 0.45,
            "predicted_subsystem": "STORAGE_NVME",
            "shap_factors": [
                {"feature": "nvme_errors", "importance": 0.42, "value": 1420},
                {"feature": "wear_level_pct", "importance": 0.26, "value": 74},
                {"feature": "operating_temp_c", "importance": -0.05, "value": 54.0},
            ],
            "rag_context": {
                "bulletin_id": "TB-NVME-CORRUPT-102",
                "title": "Corrupção de firmware em controladora PCIe NAND sob I/O concorrente",
                "graph_lineage": ["MacBook Pro M2", "SSD AP0512Z", "Kernel Panic IOStorageFamily", "KB-7712"],
            },
            "matched_runbook_id": "RB-NVME-FLASH-03",
            "matched_bulletin_id": "TB-NVME-CORRUPT-102",
            "semantic_cache_hit": False,
            "agent_confidence": 0.89,
            "requires_human_approval": True,
            "triage_action": "REPLACE_LOGIC_BOARD",
            "agent_diagnosis": {
                "summary": "Controladora NVMe apresentando setores defeituosos irrecuperáveis. Substituição recomendada.",
                "protocol": "HARDWARE_RMA_REPAIR",
            },
        },
        {
            "device_id": "PHONE-PIXEL8-PRO-9182",
            "device_type": "SMARTPHONE",
            "model_code": "GOOGLE-GC368",
            "batch_id": "BATCH-2024-Q2-P8P",
            "firmware_version": "AP2A.240505",
            "sla_tier": "STANDARD",
            "age_days": 95,
            "subsystem": "FIRMWARE_OS",
            "error_code": "MODEM_5G_CRASH_LOOP",
            "description": "Reinicialização contínua do modem baseband após handshake em banda n78 NSA.",
            "telemetry": {"operating_temp_c": 41.2, "handshake_retries": 18, "packet_loss_pct": 84},
            "current_status": AlertStatus.AUTO_RECOMMENDED.value,
            "rma_risk_score": 0.22,
            "sla_breach_risk": 0.15,
            "predicted_subsystem": "FIRMWARE_OS",
            "shap_factors": [
                {"feature": "packet_loss_pct", "importance": 0.25, "value": 84},
                {"feature": "operating_temp_c", "importance": -0.18, "value": 41.2},
                {"feature": "device_age_days", "importance": -0.12, "value": 95},
            ],
            "rag_context": {
                "bulletin_id": "TB-MODEM-N78-PATCH",
                "title": "Bug transitório no modem Shannon 5300 resolvido via patch de APN",
                "graph_lineage": ["Pixel 8 Pro", "Modem Shannon 5300", "5G Subsystem", "Carrier Patch #441"],
            },
            "matched_runbook_id": "RB-MODEM-PROVISION-02",
            "matched_bulletin_id": "TB-MODEM-N78-PATCH",
            "semantic_cache_hit": True,
            "agent_confidence": 0.96,
            "requires_human_approval": False,
            "triage_action": "APPLY_OTA_MODEM_PROFILE",
            "agent_diagnosis": {
                "summary": "Falha transitória no firmware do modem. Correção autônoma aplicada com sucesso via OTA.",
                "protocol": "OTA_AUTONOMOUS_FIX",
            },
        },
        {
            "device_id": "NOTEBOOK-SURFACE-1044",
            "device_type": "NOTEBOOK",
            "model_code": "MS-SURFACE-LAPTOP-5",
            "batch_id": "BATCH-2023-Q3-SL5",
            "firmware_version": "17.4.1",
            "sla_tier": "STANDARD",
            "age_days": 310,
            "subsystem": "THERMAL_BOARD",
            "error_code": "CPU_THROTTLE_LOCK",
            "description": "Frequência dos núcleos de performance travada em 800MHz após pico térmico em renderização.",
            "telemetry": {"operating_temp_c": 68.0, "clock_freq_mhz": 800, "ambient_temp_c": 26.5},
            "current_status": AlertStatus.AUTO_RECOMMENDED.value,
            "rma_risk_score": 0.35,
            "sla_breach_risk": 0.28,
            "predicted_subsystem": "THERMAL_BOARD",
            "shap_factors": [
                {"feature": "operating_temp_c", "importance": 0.24, "value": 68.0},
                {"feature": "clock_freq_mhz", "importance": 0.19, "value": 800},
            ],
            "rag_context": {
                "bulletin_id": "TB-THERMAL-GOVERNOR-RESET",
                "title": "Travamento de governor térmico no SoC após suspensão em background",
                "graph_lineage": ["Surface Laptop", "Thermal Daemon", "ThermalGovernor", "KB-3180"],
            },
            "matched_runbook_id": "RB-THERMAL-RECALIBRATE",
            "matched_bulletin_id": "TB-THERMAL-GOVERNOR-RESET",
            "semantic_cache_hit": True,
            "agent_confidence": 0.91,
            "requires_human_approval": False,
            "triage_action": "THERMAL_DAEMON_RESTART",
            "agent_diagnosis": {
                "summary": "Daemon térmico preso em proteção de emergência. Recalibração de governor concluída.",
                "protocol": "AUTO_HEALING_AGENT",
            },
        },
        {
            "device_id": "NOTEBOOK-DELL-XPS-5521",
            "device_type": "NOTEBOOK",
            "model_code": "DELL-XPS-9530",
            "batch_id": "BATCH-2024-Q1-XPS",
            "firmware_version": "1.8.0",
            "sla_tier": "PLATINUM",
            "age_days": 180,
            "subsystem": "THERMAL_BOARD",
            "error_code": "MEM_PARITY_ECC_ERROR",
            "description": "Erros corrigíveis de ECC na memória LPDDR5 ultrapassaram o limiar aceitável de degradação.",
            "telemetry": {"ecc_single_bit_errors": 4820, "operating_temp_c": 62.0, "uptime_hours": 720},
            "current_status": AlertStatus.HUMAN_REVIEW.value,
            "rma_risk_score": 0.82,
            "sla_breach_risk": 0.65,
            "predicted_subsystem": "THERMAL_BOARD",
            "shap_factors": [
                {"feature": "ecc_single_bit_errors", "importance": 0.45, "value": 4820},
                {"feature": "uptime_hours", "importance": 0.18, "value": 720},
                {"feature": "operating_temp_c", "importance": 0.12, "value": 62.0},
            ],
            "rag_context": {
                "bulletin_id": "TB-LPDDR5-SUBCH-FAIL",
                "title": "Falha progressiva no subcanal B de memória LPDDR5 soldada",
                "graph_lineage": ["Dell XPS 9530", "LPDDR5-6000", "Memory Controller", "Hardware Bulletin #12"],
            },
            "matched_runbook_id": "RB-MOTHERBOARD-EXCHANGE",
            "matched_bulletin_id": "TB-LPDDR5-SUBCH-FAIL",
            "semantic_cache_hit": False,
            "agent_confidence": 0.95,
            "requires_human_approval": True,
            "triage_action": "REPLACE_MOTHERBOARD_ASSEMBLY",
            "agent_diagnosis": {
                "summary": "Taxa de erro de paridade ECC indicando falha física irreversível na memória integrada.",
                "protocol": "EXPEDITED_RMA_HUMAN_APPROVAL",
            },
        },
        {
            "device_id": "PHONE-SAMSUNG-S24-4410",
            "device_type": "SMARTPHONE",
            "model_code": "SAMSUNG-SM-S928B",
            "batch_id": "BATCH-2024-Q2-S24",
            "firmware_version": "S928BXXU1AXCA",
            "sla_tier": "STANDARD",
            "age_days": 80,
            "subsystem": "BATTERY_POWER",
            "error_code": "BATT_CHARGE_PROTECT_TRIP",
            "description": "Proteção de sobretensão ativada temporariamente por carregador de terceiros não calibrado.",
            "telemetry": {"operating_temp_c": 36.5, "charger_wattage": 65, "cycle_count": 82},
            "current_status": AlertStatus.RESOLVED.value,
            "rma_risk_score": 0.12,
            "sla_breach_risk": 0.05,
            "predicted_subsystem": "BATTERY_POWER",
            "shap_factors": [
                {"feature": "operating_temp_c", "importance": -0.25, "value": 36.5},
                {"feature": "cycle_count", "importance": -0.30, "value": 82},
            ],
            "rag_context": {
                "bulletin_id": "TB-USB-PD-HANDSHAKE-RESET",
                "title": "Desarme preventivo de barramento USB-PD",
                "graph_lineage": ["Galaxy S24", "PMIC Maxim", "Battery Circuit", "Auto-Cleared"],
            },
            "matched_runbook_id": "RB-CHARGER-DIAG-01",
            "matched_bulletin_id": "TB-USB-PD-HANDSHAKE-RESET",
            "semantic_cache_hit": True,
            "agent_confidence": 0.98,
            "requires_human_approval": False,
            "triage_action": "OPERATOR_DISPATCH_CONFIRMED",
            "agent_diagnosis": {
                "summary": "Evento transitório resolvido. Bateria operando 100% dentro dos parâmetros nominais.",
                "protocol": "RESOLVED_NOMINAL",
            },
        },
    ]

    results: list[tuple[AlertRecord, list[AlertEventRecord]]] = []

    for sc in scenarios:
        alert_id = uuid4()
        idemp = f"sim-{alert_id.hex[:12]}"
        alert = AlertRecord(
            id=alert_id,
            idempotency_key=idemp,
            source_id="fleetpulse-simulator",
            device_id=sc["device_id"],
            device_type=sc["device_type"],
            model_code=sc["model_code"],
            batch_id=sc["batch_id"],
            firmware_version=sc["firmware_version"],
            sla_tier=sc["sla_tier"],
            age_days=sc["age_days"],
            subsystem=sc["subsystem"],
            error_code=sc["error_code"],
            description=sc["description"],
            telemetry=sc["telemetry"],
            current_status=sc["current_status"],
            rma_risk_score=sc["rma_risk_score"],
            sla_breach_risk=sc["sla_breach_risk"],
            predicted_subsystem=sc["predicted_subsystem"],
            shap_factors=sc["shap_factors"],
            rag_context=sc["rag_context"],
            matched_runbook_id=sc["matched_runbook_id"],
            matched_bulletin_id=sc["matched_bulletin_id"],
            semantic_cache_hit=sc["semantic_cache_hit"],
            agent_diagnosis=sc["agent_diagnosis"],
            triage_action=sc["triage_action"],
            agent_confidence=sc["agent_confidence"],
            requires_human_approval=sc["requires_human_approval"],
        )
        session.add(alert)
        await session.flush()

        # Build chronological audit trail
        history_steps = [
            (None, AlertStatus.RECEIVED.value, "Telemetry packet ingested"),
            (AlertStatus.RECEIVED.value, AlertStatus.DEDUPED.value, "Idempotency hash verified"),
            (AlertStatus.DEDUPED.value, AlertStatus.ML_SCORED.value, f"Random Forest scored RMA={sc['rma_risk_score']}"),
            (AlertStatus.ML_SCORED.value, AlertStatus.CONTEXT_RETRIEVED.value, "Hybrid RAG retrieved bulletins and graph lineage"),
            (AlertStatus.CONTEXT_RETRIEVED.value, AlertStatus.AGENT_DIAGNOSED.value, f"AI Triage Agent evaluated action: {sc['triage_action']}"),
            (AlertStatus.AGENT_DIAGNOSED.value, AlertStatus.SCHEMA_VALIDATED.value, "Pydantic contract validated"),
        ]

        if sc["current_status"] == AlertStatus.HUMAN_REVIEW.value:
            history_steps.append(
                (AlertStatus.SCHEMA_VALIDATED.value, AlertStatus.HUMAN_REVIEW.value, "High RMA risk requires operator sign-off")
            )
        elif sc["current_status"] == AlertStatus.AUTO_RECOMMENDED.value:
            history_steps.append(
                (AlertStatus.SCHEMA_VALIDATED.value, AlertStatus.AUTO_RECOMMENDED.value, "Low RMA risk eligible for automated dispatch")
            )
        elif sc["current_status"] == AlertStatus.RESOLVED.value:
            history_steps.append(
                (AlertStatus.SCHEMA_VALIDATED.value, AlertStatus.AUTO_RECOMMENDED.value, "Low RMA risk eligible for automated dispatch")
            )
            history_steps.append(
                (AlertStatus.AUTO_RECOMMENDED.value, AlertStatus.RESOLVED.value, "Auto-remediation telemetry confirmed healthy state")
            )

        events: list[AlertEventRecord] = []
        for from_st, to_st, reason in history_steps:
            ev = AlertEventRecord(
                alert_id=alert.id,
                from_status=from_st,
                to_status=to_st,
                reason=reason,
                event_metadata={"simulated": True},
            )
            session.add(ev)
            events.append(ev)

        await session.flush()
        results.append((alert, events))

    await session.commit()
    return results

