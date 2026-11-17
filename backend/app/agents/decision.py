"""Human-in-the-loop decision engine implementing Architectural Invariant #6."""

import logging

from app.agents.schemas import TriageAction, TriageDiagnosis
from app.domain.enums import AlertStatus

logger = logging.getLogger("fleetpulse.decision")

RMA_RISK_THRESHOLD = 0.70
AGENT_CONFIDENCE_THRESHOLD = 0.75
MANDATORY_REVIEW_ACTIONS = frozenset(
    {
        TriageAction.REPLACE_HARDWARE,
        TriageAction.UPDATE_FIRMWARE,
        TriageAction.ESCALATE_TIER2,
    }
)


def evaluate_human_gatekeeper(
    diagnosis: TriageDiagnosis,
    rma_risk_score: float | None = None,
) -> tuple[AlertStatus, str]:
    """Evaluate whether an alert requires human review or can be auto-recommended.

    Enforces Architectural Invariant #6:
    - RMA risk >= 0.70 mandates human review.
    - Physical hardware replacement or batch firmware changes mandate human review.
    - Low agent confidence (< 0.75) mandates human review.
    - Explicit flag diagnosis.requires_human_approval mandates human review.
    - Only high-confidence, non-destructive remote actions qualify for AUTO_RECOMMENDED.
    """
    reasons: list[str] = []

    if rma_risk_score is not None and rma_risk_score >= RMA_RISK_THRESHOLD:
        reasons.append(
            f"High RMA risk score ({rma_risk_score:.2f} >= {RMA_RISK_THRESHOLD:.2f})"
        )

    if diagnosis.action_type in MANDATORY_REVIEW_ACTIONS:
        reasons.append(
            f"Action '{diagnosis.action_type.value}' requires physical intervention or fleet-wide risk"
        )

    if diagnosis.confidence_score < AGENT_CONFIDENCE_THRESHOLD:
        reasons.append(
            f"Agent confidence score ({diagnosis.confidence_score:.2f} < {AGENT_CONFIDENCE_THRESHOLD:.2f}) below auto-approval threshold"
        )

    if diagnosis.requires_human_approval and not reasons:
        reasons.append("Diagnosis model explicitly flagged requires_human_approval=True")

    if reasons:
        summary_reason = "; ".join(reasons)
        logger.info("Human gatekeeper triggered: %s", summary_reason)
        return AlertStatus.HUMAN_REVIEW, summary_reason

    return (
        AlertStatus.AUTO_RECOMMENDED,
        f"High confidence ({diagnosis.confidence_score:.2f}) remote action '{diagnosis.action_type.value}' eligible for automatic execution",
    )
