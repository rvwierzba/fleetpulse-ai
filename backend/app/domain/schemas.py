"""Pydantic v2 contracts for alert ingestion and Redis queue payloads."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.domain.enums import AlertStatus, DeviceType, SLATier, Subsystem


class TelemetrySnapshot(BaseModel):
    """Structured hardware and firmware metrics attached to an alert."""

    model_config = ConfigDict(extra="forbid")

    battery_cycles: int | None = Field(default=None, ge=0)
    battery_health_pct: float | None = Field(default=None, ge=0.0, le=100.0)
    temperature_c: float | None = Field(default=None, ge=-30.0, le=130.0)
    nvme_wear_pct: float | None = Field(default=None, ge=0.0, le=100.0)
    smart_errors: int = Field(default=0, ge=0)
    kernel_panics_24h: int = Field(default=0, ge=0)


class AlertCreateRequest(BaseModel):
    """Incoming telemetry alert payload accepted by POST /v1/alerts."""

    model_config = ConfigDict(str_strip_whitespace=True)

    source_id: str = Field(min_length=1, max_length=100)
    device_id: str = Field(min_length=1, max_length=100)
    device_type: DeviceType
    model_code: str = Field(min_length=1, max_length=100)
    batch_id: str = Field(min_length=1, max_length=100)
    firmware_version: str = Field(min_length=1, max_length=64)
    sla_tier: SLATier
    age_days: int = Field(ge=0, le=3650)
    subsystem: Subsystem
    error_code: str = Field(min_length=1, max_length=64)
    description: str = Field(default="", max_length=2000)
    telemetry: TelemetrySnapshot = Field(default_factory=TelemetrySnapshot)


class AlertAcceptedResponse(BaseModel):
    """Immediate 202 Accepted response returned without blocking on ML or LLM."""

    alert_id: UUID
    status: AlertStatus
    idempotency_key: str
    sla_first_response_hours: int
    sla_resolution_hours: int
    created_at: datetime
    deduplicated_request: bool = False


class AlertJobMessage(BaseModel):
    """Serialized job contract published onto the Redis queue for async workers."""

    alert_id: UUID
    device_id: str
    device_type: DeviceType
    subsystem: Subsystem
    error_code: str
    sla_tier: SLATier
    attempt: int = Field(default=0, ge=0)
    enqueued_at: datetime


class AlertStreamEvent(BaseModel):
    """State-change event persisted in audit log and streamed via SSE."""

    event_id: UUID
    alert_id: UUID
    from_status: AlertStatus | None
    to_status: AlertStatus
    reason: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class AlertDetailResponse(BaseModel):
    """Full alert snapshot with chronological state transition history."""

    alert_id: UUID
    device_id: str
    device_type: DeviceType
    subsystem: Subsystem
    error_code: str
    sla_tier: SLATier
    current_status: AlertStatus
    rma_risk_score: float | None = None
    sla_breach_risk: float | None = None
    predicted_subsystem: Subsystem | None = None
    shap_factors: list[dict[str, Any]] | None = None
    rag_context: dict[str, Any] | None = None
    matched_runbook_id: str | None = None
    matched_bulletin_id: str | None = None
    semantic_cache_hit: bool | None = None
    created_at: datetime
    updated_at: datetime
    events: list[AlertStreamEvent]
