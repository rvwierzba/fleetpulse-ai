"""Domain and contract tests for POST /v1/alerts ingestion."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import httpx
import pytest

from app.api.deps import get_db_session, get_redis
from app.domain.enums import AlertStatus, SLATier, can_transition, get_sla_targets
from app.infra.config import Settings, get_settings
from app.infra.database import AlertEventRecord, AlertRecord
from app.main import app

SAMPLE_PAYLOAD = {
    "source_id": "agent-corp-sp-01",
    "device_id": "NB-2026-0042",
    "device_type": "NOTEBOOK",
    "model_code": "T14-GEN5",
    "batch_id": "BATCH-2026-Q3",
    "firmware_version": "BIOS-1.24.0",
    "sla_tier": "PLATINUM",
    "age_days": 410,
    "subsystem": "STORAGE_NVME",
    "error_code": "NVME_MEDIA_ERR_04",
    "description": "Increased bad block warnings after firmware update",
    "telemetry": {
        "battery_cycles": 310,
        "battery_health_pct": 84.5,
        "temperature_c": 71.2,
        "nvme_wear_pct": 18.0,
        "smart_errors": 4,
        "kernel_panics_24h": 1,
    },
}


def test_domain_sla_targets_and_state_machine_transitions() -> None:
    assert get_sla_targets(SLATier.PLATINUM) == (4, 24)
    assert get_sla_targets(SLATier.GOLD) == (8, 48)
    assert get_sla_targets(SLATier.STANDARD) == (24, 72)

    assert can_transition(AlertStatus.RECEIVED, AlertStatus.DEDUPED) is True
    assert can_transition(AlertStatus.RECEIVED, AlertStatus.IGNORED_DUPLICATE) is True
    assert can_transition(AlertStatus.RECEIVED, AlertStatus.RESOLVED) is False
    assert can_transition(AlertStatus.HUMAN_REVIEW, AlertStatus.RESOLVED) is True
    assert can_transition(AlertStatus.RESOLVED, AlertStatus.RECEIVED) is False


@pytest.mark.asyncio
async def test_ingest_alert_requires_idempotency_key_header() -> None:
    fake_redis = AsyncMock()
    app.dependency_overrides[get_redis] = lambda: fake_redis
    app.dependency_overrides[get_db_session] = lambda: AsyncMock()

    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            missing = await client.post("/v1/alerts", json=SAMPLE_PAYLOAD)
            blank = await client.post(
                "/v1/alerts",
                json=SAMPLE_PAYLOAD,
                headers={"Idempotency-Key": "   "},
            )
    finally:
        app.dependency_overrides.clear()

    assert missing.status_code == 422
    assert blank.status_code == 422
    fake_redis.rpush.assert_not_awaited()


@pytest.mark.asyncio
async def test_ingest_alert_returns_202_and_enqueues_job() -> None:
    fake_redis = AsyncMock()
    fake_redis.incr.return_value = 1
    fake_redis.get.return_value = None
    fake_redis.rpush.return_value = 1

    alert_id = uuid4()
    created_at = datetime.now(UTC)
    fake_record = AlertRecord(
        id=alert_id,
        idempotency_key="key-001",
        source_id=SAMPLE_PAYLOAD["source_id"],
        device_id=SAMPLE_PAYLOAD["device_id"],
        device_type=SAMPLE_PAYLOAD["device_type"],
        model_code=SAMPLE_PAYLOAD["model_code"],
        batch_id=SAMPLE_PAYLOAD["batch_id"],
        firmware_version=SAMPLE_PAYLOAD["firmware_version"],
        sla_tier=SAMPLE_PAYLOAD["sla_tier"],
        age_days=SAMPLE_PAYLOAD["age_days"],
        subsystem=SAMPLE_PAYLOAD["subsystem"],
        error_code=SAMPLE_PAYLOAD["error_code"],
        description=SAMPLE_PAYLOAD["description"],
        telemetry=SAMPLE_PAYLOAD["telemetry"],
        current_status=AlertStatus.RECEIVED.value,
        created_at=created_at,
        updated_at=created_at,
    )

    fake_event = AlertEventRecord(
        id=uuid4(),
        alert_id=alert_id,
        from_status=None,
        to_status=AlertStatus.RECEIVED.value,
        reason="Ingested via POST /v1/alerts",
        event_metadata={"source_id": SAMPLE_PAYLOAD["source_id"]},
        created_at=created_at,
    )

    app.dependency_overrides[get_redis] = lambda: fake_redis
    app.dependency_overrides[get_db_session] = lambda: AsyncMock()

    try:
        with patch(
            "app.api.alerts.create_alert_with_received_event",
            new=AsyncMock(return_value=(fake_record, fake_event, False)),
        ):
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post(
                    "/v1/alerts",
                    json=SAMPLE_PAYLOAD,
                    headers={"Idempotency-Key": "key-001"},
                )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 202
    body = response.json()
    assert body["alert_id"] == str(alert_id)
    assert body["status"] == "RECEIVED"
    assert body["sla_first_response_hours"] == 4
    assert body["sla_resolution_hours"] == 24
    assert body["deduplicated_request"] is False
    fake_redis.rpush.assert_awaited_once()
    fake_redis.set.assert_awaited_once()


@pytest.mark.asyncio
async def test_ingest_alert_replays_cached_idempotency_without_reenqueue() -> None:
    cached_payload = {
        "alert_id": str(uuid4()),
        "status": "RECEIVED",
        "idempotency_key": "key-replay",
        "sla_first_response_hours": 4,
        "sla_resolution_hours": 24,
        "created_at": datetime.now(UTC).isoformat(),
        "deduplicated_request": False,
    }
    import json

    fake_redis = AsyncMock()
    fake_redis.incr.return_value = 1
    fake_redis.get.return_value = json.dumps(cached_payload)

    app.dependency_overrides[get_redis] = lambda: fake_redis
    app.dependency_overrides[get_db_session] = lambda: AsyncMock()

    try:
        with patch(
            "app.api.alerts.create_alert_with_received_event",
            new=AsyncMock(),
        ) as create_mock:
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post(
                    "/v1/alerts",
                    json=SAMPLE_PAYLOAD,
                    headers={"Idempotency-Key": "key-replay"},
                )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 202
    assert response.json()["deduplicated_request"] is True
    assert response.json()["alert_id"] == cached_payload["alert_id"]
    create_mock.assert_not_awaited()
    fake_redis.rpush.assert_not_awaited()


@pytest.mark.asyncio
async def test_ingest_alert_enforces_rate_limit_429() -> None:
    fake_redis = AsyncMock()
    fake_redis.incr.return_value = 5
    fake_redis.ttl.return_value = 42

    app.dependency_overrides[get_redis] = lambda: fake_redis
    app.dependency_overrides[get_db_session] = lambda: AsyncMock()
    app.dependency_overrides[get_settings] = lambda: Settings(rate_limit_per_minute=4)

    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/v1/alerts",
                json=SAMPLE_PAYLOAD,
                headers={"Idempotency-Key": "key-limit"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 429
    assert response.headers["Retry-After"] == "42"


@pytest.mark.asyncio
async def test_list_alerts_and_metrics_endpoints() -> None:
    """Sprint 5: Verify dashboard list and metrics summary endpoints."""
    fake_redis = AsyncMock()
    fake_redis.llen.return_value = 0
    fake_session = AsyncMock()

    mock_alert = AlertRecord(
        id=uuid4(),
        idempotency_key="key-test-list",
        source_id="agent-01",
        device_id="DEV-NB-001",
        device_type="NOTEBOOK",
        model_code="LATITUDE-7440",
        batch_id="BATCH-01",
        firmware_version="BIOS-1.24",
        sla_tier="PLATINUM",
        age_days=150,
        subsystem="THERMAL_BOARD",
        error_code="ERR_THERMAL_RUNAWAY",
        description="Overheating",
        telemetry={},
        current_status=AlertStatus.HUMAN_REVIEW.value,
        rma_risk_score=0.82,
        sla_breach_risk=0.45,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )

    with patch("app.api.alerts.list_recent_alerts") as mock_list, \
         patch("app.api.alerts.get_system_metrics_summary") as mock_summary:
        mock_list.return_value = [(mock_alert, [])]
        mock_summary.return_value = {
            "total_alerts": 1,
            "alerts_by_status": {"HUMAN_REVIEW": 1},
            "high_rma_alerts": 1,
            "pending_human_review": 1,
            "semantic_cache_hit_rate": 0.85,
        }

        app.dependency_overrides[get_redis] = lambda: fake_redis
        app.dependency_overrides[get_db_session] = lambda: fake_session

        try:
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                # 1. Test list
                list_res = await client.get("/v1/alerts")
                assert list_res.status_code == 200
                items = list_res.json()
                assert len(items) == 1
                assert items[0]["device_id"] == "DEV-NB-001"
                assert items[0]["current_status"] == "HUMAN_REVIEW"

                # 2. Test metrics
                metrics_res = await client.get("/v1/alerts/metrics/summary")
                assert metrics_res.status_code == 200
                metrics_data = metrics_res.json()
                assert metrics_data["total_alerts"] == 1
                assert metrics_data["high_rma_alerts"] == 1
                assert metrics_data["pending_human_review"] == 1
                assert metrics_data["circuit_breaker_state"] in ("CLOSED", "OPEN", "HALF_OPEN")
        finally:
            app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_resolve_alert_by_operator_transitions_to_resolved() -> None:
    """Sprint 5: Operator approves human-in-the-loop alert and marks it RESOLVED."""
    alert_id = uuid4()
    fake_redis = AsyncMock()
    fake_session = AsyncMock()

    mock_alert = AlertRecord(
        id=alert_id,
        idempotency_key=f"key-{alert_id}",
        source_id="agent-01",
        device_id="DEV-NB-001",
        device_type="NOTEBOOK",
        model_code="LATITUDE-7440",
        batch_id="BATCH-01",
        firmware_version="BIOS-1.24",
        sla_tier="PLATINUM",
        age_days=150,
        subsystem="THERMAL_BOARD",
        error_code="ERR_THERMAL_RUNAWAY",
        description="Overheating",
        telemetry={},
        current_status=AlertStatus.HUMAN_REVIEW.value,
        rma_risk_score=0.82,
        sla_breach_risk=0.45,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )

    resolved_event = AlertEventRecord(
        id=uuid4(),
        alert_id=alert_id,
        from_status=AlertStatus.HUMAN_REVIEW.value,
        to_status=AlertStatus.RESOLVED.value,
        reason="Operator engineer-n2 resolved",
        event_metadata={"operator_id": "engineer-n2"},
        created_at=datetime.now(UTC),
    )

    mock_alert_resolved = AlertRecord(
        id=alert_id,
        idempotency_key=f"key-{alert_id}",
        source_id="agent-01",
        device_id="DEV-NB-001",
        device_type="NOTEBOOK",
        model_code="LATITUDE-7440",
        batch_id="BATCH-01",
        firmware_version="BIOS-1.24",
        sla_tier="PLATINUM",
        age_days=150,
        subsystem="THERMAL_BOARD",
        error_code="ERR_THERMAL_RUNAWAY",
        description="Overheating",
        telemetry={},
        current_status=AlertStatus.RESOLVED.value,
        rma_risk_score=0.82,
        sla_breach_risk=0.45,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )

    with patch("app.api.alerts.get_alert_with_events") as mock_get, \
         patch("app.api.alerts.transition_alert_state") as mock_trans:
        mock_get.side_effect = [
            (mock_alert, []),
            (mock_alert_resolved, [resolved_event]),
        ]
        mock_trans.return_value = resolved_event

        app.dependency_overrides[get_redis] = lambda: fake_redis
        app.dependency_overrides[get_db_session] = lambda: fake_session

        try:
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                res = await client.post(
                    f"/v1/alerts/{alert_id}/resolve",
                    json={
                        "resolution_note": "Thermal paste reapplied and fan replaced.",
                        "action_taken": "DISPATCH_CONFIRMED",
                        "operator_id": "engineer-n2",
                    },
                )
        finally:
            app.dependency_overrides.clear()

    assert res.status_code == 200
    resolved_data = res.json()
    assert resolved_data["current_status"] == "RESOLVED"
    fake_redis.publish.assert_awaited_once()
