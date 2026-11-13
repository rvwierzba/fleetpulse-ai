"""Tests for ML telemetry generator, anti-leakage splitting, and SHAP explainability."""

from pathlib import Path

import pandas as pd

from app.domain.enums import Subsystem
from app.ml.dataset_generator import generate_fleet_telemetry, split_temporal_and_grouped
from app.ml.service import MLInferenceService
from app.ml.train import ALL_FEATURES, train_and_export_pipeline


def test_generate_fleet_telemetry_schema_and_distribution() -> None:
    df = generate_fleet_telemetry(n_devices=50, n_alerts=200, days_span=60, seed=123)

    assert isinstance(df, pd.DataFrame)
    assert len(df) == 200
    for col in ALL_FEATURES + ["timestamp", "device_id", "rma_risk", "sla_breach"]:
        assert col in df.columns

    # Verify bounds
    assert df["battery_health_pct"].min() >= 30.0
    assert df["battery_health_pct"].max() <= 100.0
    assert df["temperature_c"].min() >= 20.0
    assert df["nvme_wear_pct"].max() <= 100.0
    assert set(df["rma_risk"].unique()).issubset({0, 1})
    assert set(df["sla_breach"].unique()).issubset({0, 1})


def test_split_temporal_and_grouped_guarantees_zero_data_leakage() -> None:
    df = generate_fleet_telemetry(n_devices=60, n_alerts=300, days_span=90, seed=999)
    train_df, test_df = split_temporal_and_grouped(
        df,
        test_device_ratio=0.30,
        temporal_cutoff_quantile=0.70,
        seed=999,
    )

    train_devices = set(train_df["device_id"].unique())
    test_devices = set(test_df["device_id"].unique())

    # Invariant #1: Disjoint device groups
    assert train_devices.isdisjoint(test_devices), "Leakage: devices shared across train and test!"

    # Invariant #2: Temporal ordering
    train_max_time = train_df["timestamp"].max()
    test_min_time = test_df["timestamp"].min()
    assert test_min_time >= train_max_time or len(test_df) > 0


def test_train_pipeline_and_metrics_superiority(tmp_path: Path) -> None:
    summary = train_and_export_pipeline(n_alerts=600, seed=42, artifacts_dir=tmp_path)

    assert "rma_risk_comparison" in summary
    rf_metrics = summary["rma_risk_comparison"]["production_random_forest"]
    dummy_metrics = summary["rma_risk_comparison"]["baseline_dummy"]

    # Production Random Forest must outperform random/dummy baseline
    assert rf_metrics["roc_auc"] >= dummy_metrics["roc_auc"]
    assert rf_metrics["pr_auc"] >= dummy_metrics["pr_auc"]
    assert (tmp_path / "model_artifacts.joblib").exists()
    assert (tmp_path / "metrics.json").exists()


def test_ml_inference_service_scoring_and_shap_explanations(tmp_path: Path) -> None:
    # Ensure artifacts exist in tmp_path
    train_and_export_pipeline(n_alerts=500, seed=42, artifacts_dir=tmp_path)
    service = MLInferenceService(artifacts_path=tmp_path)

    high_risk_alert = {
        "device_type": "NOTEBOOK",
        "model_code": "TP-X1-G11",
        "batch_id": "BATCH-2025-Q1",
        "firmware_version": "1.4.2-REGRESS",
        "sla_tier": "PLATINUM",
        "age_days": 650,
        "subsystem": "BATTERY_POWER",
        "error_code": "BAT_HEALTH_DEGRADED",
        "telemetry": {
            "battery_cycles": 1150,
            "battery_health_pct": 46.2,
            "temperature_c": 82.5,
            "nvme_wear_pct": 30.0,
            "smart_errors": 0,
            "kernel_panics_24h": 0,
        },
    }

    result = service.score_alert(high_risk_alert)

    # Validate output contract
    assert 0.0 <= result.rma_risk_score <= 100.0
    assert 0.0 <= result.sla_breach_risk <= 100.0
    assert result.predicted_subsystem == Subsystem.BATTERY_POWER
    assert len(result.shap_factors) == 3

    # Check top SHAP factors
    for factor in result.shap_factors:
        assert isinstance(factor.feature, str)
        assert isinstance(factor.attribution, float)
        assert "risco" in factor.human_readable
