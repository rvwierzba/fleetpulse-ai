"""Pydantic contracts for machine learning scoring, risk metrics, and SHAP explanations."""

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.domain.enums import Subsystem


class SHAPFactor(BaseModel):
    """Single feature attribution explaining the alert risk score."""

    model_config = ConfigDict(extra="forbid")

    feature: str
    attribution: float
    value: Any = None
    human_readable: str


class MLScoreResult(BaseModel):
    """Complete predictive risk assessment and local explainability payload."""

    model_config = ConfigDict(extra="forbid")

    rma_risk_score: float = Field(ge=0.0, le=100.0, description="Component replacement / RMA risk")
    sla_breach_risk: float = Field(
        ge=0.0, le=100.0, description="Probability of exceeding SLA deadline"
    )
    predicted_subsystem: Subsystem
    shap_factors: list[SHAPFactor] = Field(
        default_factory=list, description="Top contributing factors"
    )
    model_version: str = "v1.0.0"
    scored_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
