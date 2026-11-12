"""Async PostgreSQL engine, ORM models for alerts/events, and state machine repository."""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Uuid, select, text
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
    """Create missing relational tables on application startup."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


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
