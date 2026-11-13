"""Synthetic telemetry dataset generator with physics-grounded risk and anti-leakage splitting."""

import random
from datetime import UTC, datetime, timedelta
from typing import Any

import numpy as np
import pandas as pd

from app.domain.enums import DeviceType, SLATier, Subsystem

# Realistic corporate fleet device catalogs
NOTEBOOK_MODELS: list[str] = ["TP-X1-G11", "TP-T14-G4", "TP-P16S-G2", "TP-L13-G4"]
SMARTPHONE_MODELS: list[str] = ["MOTO-EDGE50", "THINKPHONE-25", "MOTO-G84-ENT"]
BATCH_POOL: list[str] = [
    "BATCH-2024-Q3",
    "BATCH-2024-Q4",
    "BATCH-2025-Q1",
    "BATCH-2025-Q2",
    "BATCH-2025-Q3",
]
FIRMWARE_VERSIONS: dict[DeviceType, list[str]] = {
    DeviceType.NOTEBOOK: ["1.2.0", "1.3.1", "1.4.2-REGRESS", "1.5.0"],
    DeviceType.SMARTPHONE: ["U1.0.4", "U1.1.2", "U1.2.0-REGRESS", "U2.0.1"],
}

ERROR_CODE_MAP: dict[Subsystem, list[str]] = {
    Subsystem.BATTERY_POWER: [
        "BAT_HEALTH_DEGRADED",
        "BAT_THERMAL_WARN",
        "BAT_VOLTAGE_IRREGULAR",
        "BAT_CYCLE_EXCEEDED",
    ],
    Subsystem.STORAGE_NVME: [
        "NVME_SMART_CRITICAL",
        "NVME_WEAR_HIGH",
        "NVME_READ_TIMEOUT",
        "NVME_SECTOR_CORRUPT",
    ],
    Subsystem.THERMAL_BOARD: [
        "THERMAL_THROTTLE_LOCK",
        "FAN_RPM_FAILURE",
        "VRM_HOTSPOT_ALERT",
        "BOARD_POWER_FAULT",
    ],
    Subsystem.FIRMWARE_OS: [
        "KERNEL_PANIC_WDT",
        "FW_ASSERT_REBOOT",
        "BOOTLOADER_SEC_FAULT",
        "DRIVER_BSOD_SPIKE",
    ],
    Subsystem.DISPLAY_PERIPHERAL: [
        "PANEL_LINE_FAILURE",
        "TOUCH_DIGITIZER_FAIL",
        "EDP_SIGNAL_LOSS",
        "DOCK_COMM_FAILURE",
    ],
}


def generate_fleet_telemetry(
    n_devices: int = 400,
    n_alerts: int = 3000,
    days_span: int = 180,
    seed: int = 42,
) -> pd.DataFrame:
    """Generate realistic corporate fleet telemetry dataset with physics-based RMA ground truth."""
    random.seed(seed)
    np.random.seed(seed)

    base_time = datetime.now(UTC) - timedelta(days=days_span)

    # 1. Generate fleet device registry
    devices: list[dict[str, Any]] = []
    for i in range(1, n_devices + 1):
        dtype = DeviceType.NOTEBOOK if random.random() < 0.65 else DeviceType.SMARTPHONE
        model = random.choice(
            NOTEBOOK_MODELS if dtype == DeviceType.NOTEBOOK else SMARTPHONE_MODELS
        )
        batch = random.choice(BATCH_POOL)
        fw = random.choice(FIRMWARE_VERSIONS[dtype])
        sla = random.choices(
            [SLATier.PLATINUM, SLATier.GOLD, SLATier.STANDARD],
            weights=[0.25, 0.45, 0.30],
        )[0]
        age_days = random.randint(30, 950)

        # Baseline wear depends on age
        daily_cycles = (
            random.uniform(0.5, 0.9) if dtype == DeviceType.NOTEBOOK else random.uniform(0.9, 1.4)
        )
        base_cycles = int(min(1400, age_days * daily_cycles + random.gauss(0, 40)))
        base_health = max(42.0, min(100.0, 100.0 - (base_cycles * 0.035) + random.gauss(0, 4)))
        base_nvme_wear = max(1.0, min(99.0, (age_days / 950.0) * 70.0 + random.gauss(0, 10)))

        # Inherent hardware flaw in specific batch/firmware combination (firmware regression)
        has_firmware_bug = "REGRESS" in fw and batch in ["BATCH-2025-Q1", "BATCH-2025-Q2"]

        devices.append(
            {
                "device_id": f"{'nb' if dtype == DeviceType.NOTEBOOK else 'ph'}-{i:04d}",
                "device_type": dtype.value,
                "model_code": model,
                "batch_id": batch,
                "firmware_version": fw,
                "sla_tier": sla.value,
                "age_days": age_days,
                "base_cycles": max(10, base_cycles),
                "base_health": base_health,
                "base_nvme_wear": base_nvme_wear,
                "has_firmware_bug": has_firmware_bug,
            }
        )

    # 2. Generate chronological alert observations across the time window
    records: list[dict[str, Any]] = []
    for _ in range(n_alerts):
        dev = random.choice(devices)
        # Observation time along the timeline
        day_offset = random.uniform(0, days_span)
        timestamp = base_time + timedelta(days=day_offset)

        # Pick primary affected subsystem
        if dev["has_firmware_bug"] and random.random() < 0.45:
            subsystem = Subsystem.FIRMWARE_OS
        elif dev["base_health"] < 70.0 and random.random() < 0.60:
            subsystem = Subsystem.BATTERY_POWER
        elif dev["base_nvme_wear"] > 75.0 and random.random() < 0.55:
            subsystem = Subsystem.STORAGE_NVME
        else:
            subsystem = random.choice(list(Subsystem))

        error_code = random.choice(ERROR_CODE_MAP[subsystem])

        # Telemetry metrics with physics distributions
        battery_cycles = int(max(10, dev["base_cycles"] + random.randint(0, 50)))
        battery_health_pct = round(
            max(35.0, min(100.0, dev["base_health"] + random.gauss(0, 2))), 1
        )

        # Thermal stress
        if subsystem == Subsystem.THERMAL_BOARD:
            temperature_c = round(random.uniform(78.0, 96.0), 1)
            kernel_panics_24h = random.choices([0, 1, 2, 4], weights=[0.2, 0.3, 0.3, 0.2])[0]
        elif subsystem == Subsystem.FIRMWARE_OS:
            temperature_c = round(random.uniform(45.0, 82.0), 1)
            kernel_panics_24h = random.choices([1, 2, 3, 5], weights=[0.3, 0.3, 0.25, 0.15])[0]
        else:
            temperature_c = round(random.uniform(32.0, 72.0), 1)
            kernel_panics_24h = random.choices([0, 1], weights=[0.92, 0.08])[0]

        # NVMe metrics
        if subsystem == Subsystem.STORAGE_NVME:
            nvme_wear_pct = round(
                max(10.0, min(99.0, dev["base_nvme_wear"] + random.uniform(5, 20))), 1
            )
            smart_errors = random.choices([2, 5, 12, 28], weights=[0.3, 0.3, 0.25, 0.15])[0]
        else:
            nvme_wear_pct = round(
                max(1.0, min(80.0, dev["base_nvme_wear"] + random.gauss(0, 3))), 1
            )
            smart_errors = random.choices([0, 1], weights=[0.90, 0.10])[0]

        # Ground truth RMA risk calculation (physics + component failure thresholds)
        rma_prob = 0.05  # baseline non-RMA alert rate (software/glitch)

        if subsystem == Subsystem.BATTERY_POWER:
            if battery_health_pct < 65.0 or battery_cycles > 900:
                rma_prob += 0.70
            elif battery_health_pct < 75.0:
                rma_prob += 0.35

        if subsystem == Subsystem.STORAGE_NVME:
            if smart_errors >= 5 or nvme_wear_pct > 85.0:
                rma_prob += 0.75
            elif smart_errors >= 2:
                rma_prob += 0.40

        if subsystem == Subsystem.THERMAL_BOARD:
            if temperature_c > 88.0 and kernel_panics_24h >= 2:
                rma_prob += 0.80
            elif temperature_c > 80.0:
                rma_prob += 0.30

        if subsystem == Subsystem.DISPLAY_PERIPHERAL:
            rma_prob += 0.45

        if dev["has_firmware_bug"]:
            # Firmware bug requires motherboard/BIOS field replacement if severe
            rma_prob += 0.25

        rma_risk = 1 if random.random() < min(0.95, rma_prob) else 0

        # SLA breach ground truth:
        # Tighter SLA (Platinum 24h) breaches much more frequently when RMA is required
        sla_tier = dev["sla_tier"]
        sla_prob = 0.08
        if rma_risk == 1:
            if sla_tier == SLATier.PLATINUM.value:
                sla_prob = 0.65  # Hard to dispatch and swap in 24h
            elif sla_tier == SLATier.GOLD.value:
                sla_prob = 0.38  # 48h resolution
            else:
                sla_prob = 0.18  # 72h resolution allows standard shipping
        else:
            if kernel_panics_24h > 2:
                sla_prob += 0.20

        sla_breach = 1 if random.random() < min(0.90, sla_prob) else 0

        records.append(
            {
                "timestamp": timestamp.isoformat(),
                "device_id": dev["device_id"],
                "device_type": dev["device_type"],
                "model_code": dev["model_code"],
                "batch_id": dev["batch_id"],
                "firmware_version": dev["firmware_version"],
                "sla_tier": dev["sla_tier"],
                "age_days": dev["age_days"],
                "subsystem": subsystem.value,
                "error_code": error_code,
                "battery_cycles": battery_cycles,
                "battery_health_pct": battery_health_pct,
                "temperature_c": temperature_c,
                "nvme_wear_pct": nvme_wear_pct,
                "smart_errors": smart_errors,
                "kernel_panics_24h": kernel_panics_24h,
                "rma_risk": rma_risk,
                "sla_breach": sla_breach,
            }
        )

    df = pd.DataFrame(records)
    # Sort chronologically by timestamp
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.sort_values("timestamp").reset_index(drop=True)
    return df


def split_temporal_and_grouped(
    df: pd.DataFrame,
    test_device_ratio: float = 0.25,
    temporal_cutoff_quantile: float = 0.75,
    seed: int = 42,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Split dataset with zero data leakage: test set uses distinct devices AND temporal future.

    Architectural Invariant #5:
    1. Group disjointness: devices in test_df NEVER appear in train_df.
    2. Temporal ordering: test_df observations strictly occur at or after temporal cutoff.
    """
    random.seed(seed)
    df_sorted = df.sort_values("timestamp").reset_index(drop=True)

    # 1. Determine temporal cutoff timestamp
    cutoff_idx = int(len(df_sorted) * temporal_cutoff_quantile)
    cutoff_time = df_sorted.iloc[cutoff_idx]["timestamp"]

    # 2. Split unique devices into train devices and test devices
    all_devices = sorted(df_sorted["device_id"].unique())
    n_test_devices = max(1, int(len(all_devices) * test_device_ratio))
    test_devices = set(random.sample(all_devices, n_test_devices))
    train_devices = set(all_devices) - test_devices

    # Train: train devices observed BEFORE or up to cutoff
    train_mask = df_sorted["device_id"].isin(train_devices) & (
        df_sorted["timestamp"] <= cutoff_time
    )
    train_df = df_sorted[train_mask].copy().reset_index(drop=True)

    # Test: test devices observed strictly in the future (after cutoff)
    test_mask = df_sorted["device_id"].isin(test_devices) & (df_sorted["timestamp"] > cutoff_time)
    test_df = df_sorted[test_mask].copy().reset_index(drop=True)

    # Fallback guard if test cutoff leaves too few records
    if len(test_df) < 50:
        test_mask = df_sorted["device_id"].isin(test_devices)
        test_df = df_sorted[test_mask].copy().reset_index(drop=True)

    return train_df, test_df
