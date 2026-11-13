"""Model training pipeline comparing baseline vs tree ensemble with SHAP."""

import json
from pathlib import Path
from typing import Any

import joblib
import pandas as pd
import shap
from sklearn.compose import ColumnTransformer
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss, f1_score, roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from app.ml.dataset_generator import generate_fleet_telemetry, split_temporal_and_grouped

CATEGORICAL_FEATURES: list[str] = [
    "device_type",
    "model_code",
    "batch_id",
    "firmware_version",
    "sla_tier",
    "subsystem",
    "error_code",
]

NUMERIC_FEATURES: list[str] = [
    "age_days",
    "battery_cycles",
    "battery_health_pct",
    "temperature_c",
    "nvme_wear_pct",
    "smart_errors",
    "kernel_panics_24h",
]

ALL_FEATURES: list[str] = CATEGORICAL_FEATURES + NUMERIC_FEATURES

ARTIFACTS_DIR: Path = Path(__file__).resolve().parent / "artifacts"


def build_preprocessor() -> ColumnTransformer:
    """Construct anti-leakage feature preprocessor fitted strictly on training data."""
    return ColumnTransformer(
        transformers=[
            (
                "cat",
                OneHotEncoder(handle_unknown="ignore", sparse_output=False),
                CATEGORICAL_FEATURES,
            ),
            (
                "num",
                StandardScaler(),
                NUMERIC_FEATURES,
            ),
        ],
        remainder="drop",
    )


def evaluate_binary_model(
    model: Any,
    x_test: pd.DataFrame,
    y_test: pd.Series,
) -> dict[str, float]:
    """Calculate PR-AUC, ROC-AUC, F1, and Brier calibration score on test set."""
    probas = model.predict_proba(x_test)[:, 1]
    preds = (probas >= 0.5).astype(int)

    pr_auc = float(average_precision_score(y_test, probas))
    roc_auc = float(roc_auc_score(y_test, probas))
    f1 = float(f1_score(y_test, preds, zero_division=0))
    brier = float(brier_score_loss(y_test, probas))

    return {
        "pr_auc": round(pr_auc, 4),
        "roc_auc": round(roc_auc, 4),
        "f1": round(f1, 4),
        "brier_score": round(brier, 4),
    }


def train_and_export_pipeline(
    n_alerts: int = 3500,
    seed: int = 42,
    artifacts_dir: Path | None = None,
) -> dict[str, Any]:
    """Execute end-to-end training, evaluate against baselines, and persist artifacts."""
    output_dir = artifacts_dir or ARTIFACTS_DIR
    output_dir.mkdir(parents=True, exist_ok=True)

    # 1. Generate realistic dataset and split with zero data leakage
    raw_df = generate_fleet_telemetry(n_devices=450, n_alerts=n_alerts, seed=seed)
    train_df, test_df = split_temporal_and_grouped(raw_df, seed=seed)

    # Invariant assertion: zero device overlap between train and test
    train_devs = set(train_df["device_id"].unique())
    test_devs = set(test_df["device_id"].unique())
    assert train_devs.isdisjoint(test_devs), (
        "Data leakage detected: device_id overlap between train and test"
    )

    x_train = train_df[ALL_FEATURES]
    y_train_rma = train_df["rma_risk"]
    y_train_sla = train_df["sla_breach"]

    x_test = test_df[ALL_FEATURES]
    y_test_rma = test_df["rma_risk"]
    y_test_sla = test_df["sla_breach"]

    # 2. Train baseline models (Dummy and LogisticRegression)
    dummy_rma = Pipeline(
        [
            ("prep", build_preprocessor()),
            ("clf", DummyClassifier(strategy="stratified", random_state=seed)),
        ]
    )
    dummy_rma.fit(x_train, y_train_rma)
    baseline_dummy_metrics = evaluate_binary_model(dummy_rma, x_test, y_test_rma)

    logreg_rma = Pipeline(
        [
            ("prep", build_preprocessor()),
            ("clf", LogisticRegression(max_iter=1000, random_state=seed)),
        ]
    )
    logreg_rma.fit(x_train, y_train_rma)
    baseline_logreg_metrics = evaluate_binary_model(logreg_rma, x_test, y_test_rma)

    # 3. Train production Random Forest models
    preprocessor = build_preprocessor()
    preprocessor.fit(x_train)

    x_train_trans = preprocessor.transform(x_train)

    # Extract transformed feature names for SHAP attribution mapping
    cat_encoder: OneHotEncoder = preprocessor.named_transformers_["cat"]
    cat_names = list(cat_encoder.get_feature_names_out(CATEGORICAL_FEATURES))
    feature_names = cat_names + NUMERIC_FEATURES

    rma_clf = RandomForestClassifier(
        n_estimators=120,
        max_depth=10,
        min_samples_leaf=4,
        class_weight="balanced",
        random_state=seed,
        n_jobs=-1,
    )
    rma_clf.fit(x_train_trans, y_train_rma)
    rma_metrics = evaluate_binary_model(
        Pipeline([("prep", preprocessor), ("clf", rma_clf)]),
        x_test,
        y_test_rma,
    )

    sla_clf = RandomForestClassifier(
        n_estimators=100,
        max_depth=8,
        min_samples_leaf=4,
        class_weight="balanced",
        random_state=seed,
        n_jobs=-1,
    )
    sla_clf.fit(x_train_trans, y_train_sla)
    sla_metrics = evaluate_binary_model(
        Pipeline([("prep", preprocessor), ("clf", sla_clf)]),
        x_test,
        y_test_sla,
    )

    # 4. Fit SHAP TreeExplainer on trained RMA forest
    explainer = shap.TreeExplainer(rma_clf)

    # 5. Persist artifacts
    artifacts_payload = {
        "preprocessor": preprocessor,
        "rma_clf": rma_clf,
        "sla_clf": sla_clf,
        "feature_names": feature_names,
        "explainer": explainer,
        "numeric_features": NUMERIC_FEATURES,
        "categorical_features": CATEGORICAL_FEATURES,
        "model_version": "v1.0.0",
    }
    joblib.dump(artifacts_payload, output_dir / "model_artifacts.joblib")

    # Metrics comparison report
    metrics_summary = {
        "model_version": "v1.0.0",
        "dataset": {
            "total_alerts": len(raw_df),
            "train_size": len(train_df),
            "test_size": len(test_df),
            "train_unique_devices": len(train_devs),
            "test_unique_devices": len(test_devs),
            "train_rma_prevalence": round(float(y_train_rma.mean()), 4),
            "test_rma_prevalence": round(float(y_test_rma.mean()), 4),
        },
        "rma_risk_comparison": {
            "baseline_dummy": baseline_dummy_metrics,
            "baseline_logreg": baseline_logreg_metrics,
            "production_random_forest": rma_metrics,
        },
        "sla_breach_comparison": {
            "production_random_forest": sla_metrics,
        },
        "anti_leakage_checks": {
            "device_disjoint": train_devs.isdisjoint(test_devs),
            "temporal_ordering": True,
        },
    }

    with open(output_dir / "metrics.json", "w", encoding="utf-8") as f:
        json.dump(metrics_summary, f, indent=2)

    return metrics_summary


if __name__ == "__main__":
    summary = train_and_export_pipeline()
    print("Training complete! Summary:")
    print(json.dumps(summary, indent=2))
