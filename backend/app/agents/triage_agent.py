"""AI Triage Agent orchestrating Hybrid Router, Pydantic validation, and Self-Correction."""

import json
import logging
from typing import Any

from pydantic import ValidationError

from app.agents.decision import evaluate_human_gatekeeper
from app.agents.prompt_guard import wrap_untrusted_context
from app.agents.router import HybridAIRouter, get_hybrid_ai_router
from app.agents.schemas import (
    AgentTriageResult,
    RouterMetrics,
    SelfCorrectionAttempt,
    TriageAction,
    TriageDiagnosis,
)
from app.domain.enums import AlertStatus
from app.rag.graph_service import GraphService, get_graph_service

logger = logging.getLogger("fleetpulse.agent")

TRIAGE_SYSTEM_PROMPT = """You are the FleetPulse AI Senior Triage Engineer for corporate fleets of notebooks and smartphones.
Your mission is to perform root-cause diagnosis and recommend precise operational remediation.

RULES:
1. STRICT TRUTH: Base your conclusions strictly on the provided SHAP factors, Neo4j topology, and technical bulletins.
2. JSON ONLY: Output a single JSON object strictly matching the schema below. No markdown outside JSON, no explanations before/after.
3. ENTITY INTEGRITY: The matched_runbook_id must match a verified runbook provided in context (e.g. RB-THERMAL-001, RB-BATTERY-001, RB-NVME-001, RB-DISPLAY-001).
4. SAFETY: If physical disassembly, part replacement, or fleet firmware changes are indicated, requires_human_approval MUST be true.

JSON Schema:
{
  "matched_runbook_id": "string",
  "matched_bulletin_id": "string or null",
  "action_type": "REMOTE_PATCH" | "DISPATCH_TECH" | "REPLACE_HARDWARE" | "UPDATE_FIRMWARE" | "ESCALATE_TIER2",
  "confidence_score": float (between 0.0 and 1.0),
  "root_cause_analysis": "string (10-1000 characters explaining why failure occurred)",
  "requires_human_approval": boolean,
  "suggested_action_plan": ["step 1", "step 2"],
  "preventive_measures": ["recommendation 1"]
}
"""


class TriageAgent:
    """Autonomous agent diagnosing telemetry alerts with strict schema validation and auto-correction."""

    def __init__(
        self,
        router: HybridAIRouter | None = None,
        graph_service: GraphService | None = None,
        max_correction_retries: int = 2,
    ) -> None:
        self.router = router or get_hybrid_ai_router()
        self.graph_service = graph_service or get_graph_service()
        self.max_correction_retries = max_correction_retries

    def _build_initial_prompt(
        self,
        alert_data: dict[str, Any],
        shap_factors: list[dict[str, Any]] | None,
        rag_context: dict[str, Any] | None,
        rma_risk_score: float | None,
        sla_breach_risk: float | None,
    ) -> str:
        """Compose diagnostic prompt encapsulating untrusted fields within security delimiters."""
        untrusted_text = alert_data.get("description", "")
        telemetry_json = json.dumps(alert_data.get("telemetry", {}), ensure_ascii=False)
        fenced_context = wrap_untrusted_context(
            f"Description: {untrusted_text}\nTelemetry: {telemetry_json}",
            label="DEVICE_TELEMETRY_LOG",
        )

        known_runbooks: list[str] = []
        if rag_context:
            matched_rb = rag_context.get("matched_runbook_id")
            if matched_rb:
                known_runbooks.append(matched_rb)
            graph_ctx = rag_context.get("graph_context") or {}
            for rb in graph_ctx.get("runbooks", []):
                rb_id = rb.get("id")
                if rb_id and rb_id not in known_runbooks:
                    known_runbooks.append(rb_id)

        prompt_parts = [
            "DIAGNOSTIC CASE DOSSIER:",
            f"- Device ID: {alert_data.get('device_id')}",
            f"- Device Type: {alert_data.get('device_type')}",
            f"- Model Code: {alert_data.get('model_code')}",
            f"- Firmware Version: {alert_data.get('firmware_version')}",
            f"- Subsystem: {alert_data.get('subsystem')}",
            f"- Error Code: {alert_data.get('error_code')}",
            f"- Age in Days: {alert_data.get('age_days')}",
            f"- ML RMA Risk Score: {rma_risk_score if rma_risk_score is not None else 'N/A'}",
            f"- ML SLA Breach Risk: {sla_breach_risk if sla_breach_risk is not None else 'N/A'}",
            f"- Top SHAP Factors: {json.dumps(shap_factors or [], ensure_ascii=False)}",
            f"- Verified Candidate Runbooks in Topology: {', '.join(known_runbooks) if known_runbooks else 'RB-THERMAL-001, RB-BATTERY-001, RB-NVME-001, RB-DISPLAY-001'}",
            f"- Knowledge Base Bulletins: {rag_context.get('matched_bulletin_id') if rag_context else 'None'}",
            "",
            "UNTRUSTED LOGS (READ-ONLY EVIDENCE):",
            fenced_context,
            "",
            "Diagnose root cause and return the JSON payload conforming strictly to TriageDiagnosis.",
        ]
        return "\n".join(prompt_parts)

    async def diagnose_alert(
        self,
        alert_data: dict[str, Any],
        shap_factors: list[dict[str, Any]] | None = None,
        rag_context: dict[str, Any] | None = None,
        rma_risk_score: float | None = None,
        sla_breach_risk: float | None = None,
    ) -> AgentTriageResult:
        """Run triage analysis with self-correction loop and human-in-the-loop gating."""
        correction_attempts: list[SelfCorrectionAttempt] = []
        current_prompt = self._build_initial_prompt(
            alert_data=alert_data,
            shap_factors=shap_factors,
            rag_context=rag_context,
            rma_risk_score=rma_risk_score,
            sla_breach_risk=sla_breach_risk,
        )

        last_metrics: RouterMetrics | None = None
        diagnosis: TriageDiagnosis | None = None

        for attempt in range(1, self.max_correction_retries + 2):
            try:
                raw_json, last_metrics = await self.router.generate_json(
                    prompt=current_prompt,
                    system_prompt=TRIAGE_SYSTEM_PROMPT,
                )
            except Exception as exc:
                logger.error("Router error during triage attempt %d: %s", attempt, exc)
                # Circuit or network failure, build emergency fallback
                return self._build_fallback_result(
                    alert_data=alert_data,
                    rma_risk_score=rma_risk_score,
                    error_detail=str(exc),
                    attempts=correction_attempts,
                )

            # Step 1: Pydantic Schema Validation
            try:
                parsed_diagnosis = TriageDiagnosis.model_validate(raw_json)
            except ValidationError as val_err:
                error_msg = f"Schema validation failed: {val_err.errors(include_url=False)}"
                logger.warning(
                    "Triage LLM output violated Pydantic contract (Attempt %d/%d): %s",
                    attempt,
                    self.max_correction_retries + 1,
                    error_msg,
                )
                correction_attempts.append(
                    SelfCorrectionAttempt(
                        attempt_num=attempt,
                        error_type="PydanticValidationError",
                        error_detail=error_msg,
                        raw_llm_response=json.dumps(raw_json, ensure_ascii=False),
                    )
                )
                if attempt <= self.max_correction_retries:
                    current_prompt += (
                        f"\n\n[SELF-CORRECTION ERROR NOTICE - ATTEMPT {attempt}]:\n"
                        f"Your previous JSON output was rejected by the system contract:\n{error_msg}\n"
                        f"Fix all field errors and return ONLY the corrected, valid JSON object."
                    )
                    continue
                break

            # Step 2: Neo4j Entity Existence Verification (Architectural Invariant #3)
            runbook_id = parsed_diagnosis.matched_runbook_id
            if self.graph_service and runbook_id:
                try:
                    rb_valid, _ = await self.graph_service.validate_entity_ids(runbook_id=runbook_id)
                    if not rb_valid:
                        error_msg = (
                            f"Hallucinated Runbook ID '{runbook_id}' does not exist in Neo4j topology. "
                            f"Choose ONLY from verified candidate runbooks or escalate."
                        )
                        logger.warning(
                            "Invariant #3 check failed (Attempt %d): %s",
                            attempt,
                            error_msg,
                        )
                        correction_attempts.append(
                            SelfCorrectionAttempt(
                                attempt_num=attempt,
                                error_type="HallucinatedEntityIdError",
                                error_detail=error_msg,
                                raw_llm_response=json.dumps(raw_json, ensure_ascii=False),
                            )
                        )
                        if attempt <= self.max_correction_retries:
                            current_prompt += (
                                f"\n\n[SELF-CORRECTION ERROR NOTICE - ATTEMPT {attempt}]:\n"
                                f"{error_msg}\n"
                                f"Please select a real runbook ID from the verified dossier."
                            )
                            continue
                        break
                except Exception as graph_exc:
                    logger.debug("Graph entity check bypassed due to driver state: %s", graph_exc)

            # Contract & Invariant #3 both satisfied!
            diagnosis = parsed_diagnosis
            break

        if diagnosis is None:
            # Self-correction exhausted, trigger safe human review fallback
            logger.error("Self-correction loop exhausted after %d attempts", len(correction_attempts))
            return self._build_fallback_result(
                alert_data=alert_data,
                rma_risk_score=rma_risk_score,
                error_detail="Self-correction loop exhausted without valid contract conformity",
                attempts=correction_attempts,
            )

        # Step 3: Human-in-the-Loop Decision Gatekeeper (Architectural Invariant #6)
        target_status, gatekeeper_reason = evaluate_human_gatekeeper(
            diagnosis=diagnosis,
            rma_risk_score=rma_risk_score,
        )

        return AgentTriageResult(
            diagnosis=diagnosis,
            status=target_status,
            metrics=last_metrics or self._make_default_metrics(),
            correction_attempts=correction_attempts,
            gatekeeper_reason=gatekeeper_reason,
        )

    def _make_default_metrics(self) -> RouterMetrics:
        """Construct fallback router metrics when router call was synthetic or failed."""
        from app.agents.schemas import CircuitBreakerState

        return RouterMetrics(
            model_used="deterministic-fallback",
            latency_ms=0.0,
            circuit_state=CircuitBreakerState.CLOSED,
            fallback_triggered=True,
        )

    def _build_fallback_result(
        self,
        alert_data: dict[str, Any],
        rma_risk_score: float | None,
        error_detail: str,
        attempts: list[SelfCorrectionAttempt],
    ) -> AgentTriageResult:
        """Deterministic safety net ensuring alerts with agent errors safely enter HUMAN_REVIEW."""
        fallback_diagnosis = TriageDiagnosis(
            matched_runbook_id="RB-FALLBACK-REVIEW",
            matched_bulletin_id=None,
            action_type=TriageAction.ESCALATE_TIER2,
            confidence_score=0.40,
            root_cause_analysis=(
                f"Automated AI triage could not validate schema safely ({error_detail[:200]}). "
                f"Mandating manual engineer inspection per Architectural Invariant #6."
            ),
            requires_human_approval=True,
            suggested_action_plan=[
                "Assign alert to senior hardware support engineer",
                "Inspect raw telemetry and logs manually in observability dashboard",
            ],
            preventive_measures=["Review LLM prompt formatting and error logs"],
        )
        return AgentTriageResult(
            diagnosis=fallback_diagnosis,
            status=AlertStatus.HUMAN_REVIEW,
            metrics=self._make_default_metrics(),
            correction_attempts=attempts,
            gatekeeper_reason=f"Safety fallback triggered: {error_detail}",
        )


_triage_agent_instance: TriageAgent | None = None


def get_triage_agent() -> TriageAgent:
    """Return singleton TriageAgent."""
    global _triage_agent_instance
    if _triage_agent_instance is None:
        _triage_agent_instance = TriageAgent()
    return _triage_agent_instance
