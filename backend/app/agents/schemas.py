"""Pydantic v2 schemas and enumerations for AI Triage Agent, Router, and Self-Correction."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from app.domain.enums import AlertStatus


class TriageAction(StrEnum):
    """Prescribed remediation actions decided by the AI Triage Agent."""

    REMOTE_PATCH = "REMOTE_PATCH"
    DISPATCH_TECH = "DISPATCH_TECH"
    REPLACE_HARDWARE = "REPLACE_HARDWARE"
    UPDATE_FIRMWARE = "UPDATE_FIRMWARE"
    ESCALATE_TIER2 = "ESCALATE_TIER2"


class CircuitBreakerState(StrEnum):
    """Runtime states of the Hybrid AI Router Circuit Breaker."""

    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


class TriageDiagnosis(BaseModel):
    """Strict structured output contract expected from the LLM during triage."""

    model_config = ConfigDict(extra="forbid")

    matched_runbook_id: str = Field(
        description="ID of the official runbook verified in Neo4j, e.g. RB-THERMAL-001"
    )
    matched_bulletin_id: str | None = Field(
        default=None,
        description="Optional ID of the technical bulletin verified in Neo4j or pgvector",
    )
    action_type: TriageAction = Field(
        description="Prescribed remediation action category"
    )
    confidence_score: float = Field(
        ge=0.0,
        le=1.0,
        description="Agent certainty score between 0.0 (uncertain) and 1.0 (certain)",
    )
    root_cause_analysis: str = Field(
        min_length=10,
        max_length=1000,
        description="Concise technical explanation of the failure mechanism",
    )
    requires_human_approval: bool = Field(
        description="True if remediation involves physical replacement, high risk, or low confidence",
    )
    suggested_action_plan: list[str] = Field(
        default_factory=list,
        description="Sequential operational steps for technician execution",
    )
    preventive_measures: list[str] = Field(
        default_factory=list,
        description="Recommendations to prevent recurrence across the fleet",
    )


class RouterMetrics(BaseModel):
    """Telemetry capturing latency, model selection, circuit health, and tokens."""

    model_used: str
    latency_ms: float = Field(ge=0.0)
    circuit_state: CircuitBreakerState
    fallback_triggered: bool
    prompt_tokens: int | None = None
    completion_tokens: int | None = None


class SelfCorrectionAttempt(BaseModel):
    """Log record of an intercepted schema violation or hallucinated entity ID retry."""

    attempt_num: int = Field(ge=1)
    error_type: str
    error_detail: str
    raw_llm_response: str


class AgentTriageResult(BaseModel):
    """Final output of the Agent Triage pipeline ready for state machine transition."""

    diagnosis: TriageDiagnosis | None = None
    status: AlertStatus
    metrics: RouterMetrics
    correction_attempts: list[SelfCorrectionAttempt] = Field(default_factory=list)
    gatekeeper_reason: str = ""
