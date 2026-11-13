"""Inference and local SHAP explainability service for fleet telemetry alerts."""

from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd

from app.domain.enums import Subsystem
from app.ml.schemas import MLScoreResult, SHAPFactor
from app.ml.train import ALL_FEATURES, ARTIFACTS_DIR, train_and_export_pipeline


class MLInferenceService:
    """Production inference service executing tabular risk prediction and SHAP attribution."""

    def __init__(self, artifacts_path: Path | None = None) -> None:
        self.artifacts_dir = artifacts_path or ARTIFACTS_DIR
        self.artifacts_file = self.artifacts_dir / "model_artifacts.joblib"
        self._artifacts: dict[str, Any] | None = None

    def _ensure_artifacts(self) -> dict[str, Any]:
        """Load persisted models or train pipeline on-the-fly if artifacts are missing."""
        if self._artifacts is not None:
            return self._artifacts

        if not self.artifacts_file.exists():
            train_and_export_pipeline(artifacts_dir=self.artifacts_dir)

        self._artifacts = joblib.load(self.artifacts_file)
        return self._artifacts

    def _build_dataframe_row(
        self, alert_data: dict[str, Any]
    ) -> tuple[pd.DataFrame, dict[str, Any]]:
        """Normalize alert input and nested telemetry snapshot into tabular row."""
        telemetry = alert_data.get("telemetry") or {}
        if hasattr(telemetry, "model_dump"):
            telemetry = telemetry.model_dump()

        raw_row: dict[str, Any] = {
            "device_type": str(alert_data.get("device_type", "NOTEBOOK")),
            "model_code": str(alert_data.get("model_code", "GENERIC-MODEL")),
            "batch_id": str(alert_data.get("batch_id", "BATCH-DEFAULT")),
            "firmware_version": str(alert_data.get("firmware_version", "1.0.0")),
            "sla_tier": str(alert_data.get("sla_tier", "STANDARD")),
            "subsystem": str(alert_data.get("subsystem", "BATTERY_POWER")),
            "error_code": str(alert_data.get("error_code", "GENERIC_ERROR")),
            "age_days": int(alert_data.get("age_days", 180)),
            "battery_cycles": int(telemetry.get("battery_cycles") or 350),
            "battery_health_pct": float(telemetry.get("battery_health_pct") or 85.0),
            "temperature_c": float(telemetry.get("temperature_c") or 45.0),
            "nvme_wear_pct": float(telemetry.get("nvme_wear_pct") or 20.0),
            "smart_errors": int(telemetry.get("smart_errors") or 0),
            "kernel_panics_24h": int(telemetry.get("kernel_panics_24h") or 0),
        }
        df_row = pd.DataFrame([raw_row])[ALL_FEATURES]
        return df_row, raw_row

    def score_alert(self, alert_data: dict[str, Any]) -> MLScoreResult:
        """Score alert: predict RMA risk, SLA breach probability, and top-3 SHAP attributions."""
        artifacts = self._ensure_artifacts()
        preprocessor = artifacts["preprocessor"]
        rma_clf = artifacts["rma_clf"]
        sla_clf = artifacts["sla_clf"]
        explainer = artifacts["explainer"]
        feature_names: list[str] = artifacts["feature_names"]
        model_version: str = artifacts.get("model_version", "v1.0.0")

        df_row, raw_row = self._build_dataframe_row(alert_data)
        x_trans = preprocessor.transform(df_row)

        # 1. Predict probabilities
        rma_prob = float(rma_clf.predict_proba(x_trans)[0][1])
        sla_prob = float(sla_clf.predict_proba(x_trans)[0][1])

        rma_risk_score = round(rma_prob * 100.0, 1)
        sla_breach_risk = round(sla_prob * 100.0, 1)

        # 2. Local explainability via TreeExplainer
        raw_shap = explainer.shap_values(x_trans)

        # TreeExplainer on binary classifier returns either ndarray of shape (1, n_features, 2)
        # or list of [class_0_values, class_1_values], or (1, n_features).
        if isinstance(raw_shap, list):
            class1_shap = raw_shap[1][0]
        elif isinstance(raw_shap, np.ndarray):
            if raw_shap.ndim == 3:
                class1_shap = raw_shap[0, :, 1]
            elif raw_shap.ndim == 2:
                class1_shap = raw_shap[0]
            else:
                class1_shap = raw_shap
        else:
            class1_shap = np.array(raw_shap)

        # Group one-hot encoded categories back or present feature impact cleanly
        attributions: list[dict[str, Any]] = []
        for feat_name, attr in zip(feature_names, class1_shap, strict=False):
            attr_val = float(attr)
            # Find matching raw value
            if feat_name in raw_row:
                orig_val = raw_row[feat_name]
                display_name = feat_name
            elif "_" in feat_name:
                # One-hot encoded feature like error_code_BAT_HEALTH_DEGRADED
                prefix = feat_name.split("_")[0]
                display_name = feat_name
                orig_val = raw_row.get(prefix, feat_name)
            else:
                orig_val = None
                display_name = feat_name

            attributions.append(
                {
                    "feature": display_name,
                    "attribution": round(attr_val, 4),
                    "abs_attr": abs(attr_val),
                    "value": orig_val,
                }
            )

        # Sort by absolute impact and take top 3
        attributions.sort(key=lambda item: item["abs_attr"], reverse=True)
        top_factors_raw = attributions[:3]

        shap_factors: list[SHAPFactor] = []
        for factor in top_factors_raw:
            pts = round(factor["attribution"] * 100.0, 1)
            sign_str = f"+{pts}" if pts > 0 else f"{pts}"
            impact_desc = "elevou o risco" if pts > 0 else "reduziu o risco"
            val_str = f"={factor['value']}" if factor["value"] is not None else ""
            human_text = f"{factor['feature']}{val_str} {impact_desc} ({sign_str} pts)"

            shap_factors.append(
                SHAPFactor(
                    feature=factor["feature"],
                    attribution=factor["attribution"],
                    value=factor["value"],
                    human_readable=human_text,
                )
            )

        subsystem_str = str(alert_data.get("subsystem", Subsystem.BATTERY_POWER.value))
        try:
            predicted_subsystem = Subsystem(subsystem_str)
        except ValueError:
            predicted_subsystem = Subsystem.BATTERY_POWER

        return MLScoreResult(
            rma_risk_score=rma_risk_score,
            sla_breach_risk=sla_breach_risk,
            predicted_subsystem=predicted_subsystem,
            shap_factors=shap_factors,
            model_version=model_version,
        )


_global_ml_service: MLInferenceService | None = None


def get_ml_service() -> MLInferenceService:
    """Return singleton instance of MLInferenceService."""
    global _global_ml_service
    if _global_ml_service is None:
        _global_ml_service = MLInferenceService()
    return _global_ml_service
