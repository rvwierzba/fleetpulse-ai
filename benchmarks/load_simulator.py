"""Firmware Storm Load Simulator: High-concurrency telemetry bursts for Sprint 5."""

import asyncio
import random
import time
from dataclasses import dataclass
from uuid import uuid4

import httpx


@dataclass
class BenchmarkResult:
    total_requests: int
    successful_requests: int
    failed_requests: int
    duration_seconds: float
    throughput_rps: float
    latencies_ms: list[float]
    p50_ms: float
    p90_ms: float
    p95_ms: float
    p99_ms: float
    deduplicated_count: int


def calculate_percentiles(latencies: list[float]) -> tuple[float, float, float, float]:
    """Calculate P50, P90, P95, and P99 latencies."""
    if not latencies:
        return 0.0, 0.0, 0.0, 0.0
    sorted_lats = sorted(latencies)
    n = len(sorted_lats)

    def pct(p: float) -> float:
        idx = min(int(n * p), n - 1)
        return round(sorted_lats[idx], 2)

    return pct(0.50), pct(0.90), pct(0.95), pct(0.99)


async def send_single_alert(
    client: httpx.AsyncClient,
    base_url: str,
    payload: dict,
    idempotency_key: str,
) -> tuple[bool, float, bool]:
    """Send an alert and measure response latency in milliseconds.

    Returns (success, latency_ms, was_deduplicated).
    """
    url = f"{base_url}/v1/alerts"
    headers = {
        "Idempotency-Key": idempotency_key,
        "Content-Type": "application/json",
    }
    start = time.perf_counter()
    try:
        response = await client.post(url, json=payload, headers=headers)
        latency_ms = (time.perf_counter() - start) * 1000.0
        if response.status_code == 202:
            data = response.json()
            is_dedup = data.get("deduplicated_request", False)
            return True, latency_ms, is_dedup
        return False, latency_ms, False
    except Exception:
        latency_ms = (time.perf_counter() - start) * 1000.0
        return False, latency_ms, False


def generate_storm_alert(device_idx: int, is_critical: bool = False) -> tuple[dict, str]:
    """Generate realistic telemetry payload matching fleet firmware failure profiles."""
    device_type = "NOTEBOOK" if device_idx % 2 == 0 else "SMARTPHONE"
    model_code = "LATITUDE-7440" if device_type == "NOTEBOOK" else "EDGE-40-PRO"
    batch_id = "BATCH-2026-Q1"
    firmware_version = "BIOS-1.24" if device_type == "NOTEBOOK" else "RETBR-14.2"
    subsystem = "THERMAL_BOARD" if device_idx % 3 == 0 else "BATTERY_POWER"
    error_code = "ERR_THERMAL_RUNAWAY" if subsystem == "THERMAL_BOARD" else "ERR_BATTERY_IMBALANCE"

    if is_critical:
        temp = random.uniform(96.0, 108.0)
        cycles = random.randint(750, 1100)
        health = random.uniform(45.0, 62.0)
        smart_err = random.randint(15, 45)
        panics = random.randint(4, 9)
    else:
        temp = random.uniform(65.0, 82.0)
        cycles = random.randint(250, 480)
        health = random.uniform(85.0, 94.0)
        smart_err = 0
        panics = 0

    payload = {
        "source_id": f"agent-collector-{device_idx % 5}",
        "device_id": f"DEV-{device_type[:2]}-{device_idx:04d}",
        "device_type": device_type,
        "model_code": model_code,
        "batch_id": batch_id,
        "firmware_version": firmware_version,
        "sla_tier": "PLATINUM" if device_idx % 4 == 0 else "GOLD",
        "age_days": random.randint(120, 650),
        "subsystem": subsystem,
        "error_code": error_code,
        "description": (
            f"Thermal throttling and kernel stability degradation following {firmware_version} push."
        ),
        "telemetry": {
            "battery_cycles": cycles,
            "battery_health_pct": round(health, 1),
            "temperature_c": round(temp, 1),
            "nvme_wear_pct": random.uniform(10.0, 75.0),
            "smart_errors": smart_err,
            "kernel_panics_24h": panics,
        },
    }
    idem_key = f"storm-{batch_id}-{device_idx:04d}-{uuid4().hex[:8]}"
    return payload, idem_key


async def run_storm_simulation(
    base_url: str = "http://localhost:8000",
    total_burst_count: int = 50,
    concurrency_limit: int = 10,
) -> BenchmarkResult:
    """Execute the concurrent Firmware Storm benchmark."""
    semaphore = asyncio.Semaphore(concurrency_limit)
    latencies: list[float] = []
    success_count = 0
    fail_count = 0
    dedup_count = 0

    # Build alerts with a mix of identical deduplications and critical failures
    tasks_data: list[tuple[dict, str]] = []
    for i in range(total_burst_count):
        is_crit = i % 3 == 0
        payload, idem_key = generate_storm_alert(i, is_critical=is_crit)
        tasks_data.append((payload, idem_key))

    # Add 10 intentional duplicates with same idempotency key
    for j in range(10):
        target = tasks_data[j]
        tasks_data.append((target[0], target[1]))

    start_benchmark = time.perf_counter()

    async with httpx.AsyncClient(timeout=10.0) as client:
        async def worker(payload: dict, key: str) -> None:
            nonlocal success_count, fail_count, dedup_count
            async with semaphore:
                ok, lat, is_dedup = await send_single_alert(client, base_url, payload, key)
                latencies.append(lat)
                if ok:
                    success_count += 1
                    if is_dedup:
                        dedup_count += 1
                else:
                    fail_count += 1

        await asyncio.gather(*(worker(p, k) for p, k in tasks_data))

    duration = time.perf_counter() - start_benchmark
    rps = len(tasks_data) / duration if duration > 0 else 0.0
    p50, p90, p95, p99 = calculate_percentiles(latencies)

    return BenchmarkResult(
        total_requests=len(tasks_data),
        successful_requests=success_count,
        failed_requests=fail_count,
        duration_seconds=round(duration, 3),
        throughput_rps=round(rps, 1),
        latencies_ms=latencies,
        p50_ms=p50,
        p90_ms=p90,
        p95_ms=p95,
        p99_ms=p99,
        deduplicated_count=dedup_count,
    )


def print_benchmark_report(res: BenchmarkResult) -> None:
    """Render terminal report of the Firmware Storm load test."""
    print("\n" + "=" * 68)
    print(" 🚀 FLEETPULSE AI — RELATÓRIO DO SIMULADOR 'TEMPESTADE DE FIRMWARE' (SPRINT 5)")
    print("=" * 68)
    print(f" Total de Requisições:     {res.total_requests}")
    print(f" Requisições com Sucesso:  {res.successful_requests} (202 Accepted)")
    print(f" Falhas / Rejeições:       {res.failed_requests}")
    print(f" Deduplicações Atômicas:   {res.deduplicated_count} (Idempotency-Key hit)")
    print(f" Tempo Total da Rajada:    {res.duration_seconds}s")
    print(f" Throughput da Ingestão:   {res.throughput_rps} req/s")
    print("-" * 68)
    print(" ⏱️ DISTRIBUIÇÃO DE LATÊNCIA (MÉTRICAS REAIS DA MÁQUINA)")
    print(f"  - P50 (Mediana):         {res.p50_ms} ms")
    print(f"  - P90:                   {res.p90_ms} ms")
    print(f"  - P95:                   {res.p95_ms} ms")
    print(f"  - P99:                   {res.p99_ms} ms")
    print("=" * 68 + "\n")


if __name__ == "__main__":
    result = asyncio.run(run_storm_simulation())
    print_benchmark_report(result)
