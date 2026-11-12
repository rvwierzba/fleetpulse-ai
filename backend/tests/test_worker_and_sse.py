"""Tests for async worker (dedup, exponential retry, DLQ) and SSE streaming."""

import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import httpx
import pytest

from app.api.deps import get_db_session, get_redis
from app.domain.enums import AlertStatus, DeviceType, SLATier, Subsystem
from app.domain.schemas import AlertJobMessage, AlertStreamEvent
from app.infra.config import Settings
from app.infra.database import AlertEventRecord, AlertRecord
from app.main import app
from app.workers.alert_worker import compute_backoff_seconds, process_single_job


def _make_job(attempt: int = 0) -> AlertJobMessage:
    return AlertJobMessage(
        alert_id=uuid4(),
        device_id="NB-2026-0099",
        device_type=DeviceType.NOTEBOOK,
        subsystem=Subsystem.BATTERY_POWER,
        error_code="BAT_CELL_IMBALANCE",
        sla_tier=SLATier.GOLD,
        attempt=attempt,
        enqueued_at=datetime.now(UTC),
    )


def _make_session_factory(alert: AlertRecord) -> MagicMock:
    """Create an async context-manager session factory returning a mocked AsyncSession."""
    session = AsyncMock()
    session.add = MagicMock()
    session.get.return_value = alert

    cm = AsyncMock()
    cm.__aenter__.return_value = session
    cm.__aexit__.return_value = False
    return MagicMock(return_value=cm)


def _make_alert_record(job: AlertJobMessage, status: AlertStatus) -> AlertRecord:
    now = datetime.now(UTC)
    return AlertRecord(
        id=job.alert_id,
        idempotency_key=f"idem-{job.alert_id}",
        source_id="agent-01",
        device_id=job.device_id,
        device_type=job.device_type.value,
        model_code="T14-GEN5",
        batch_id="BATCH-01",
        firmware_version="BIOS-1.24",
        sla_tier=job.sla_tier.value,
        age_days=200,
        subsystem=job.subsystem.value,
        error_code=job.error_code,
        description="Battery imbalance detected",
        telemetry={},
        current_status=status.value,
        created_at=now,
        updated_at=now,
    )


def test_compute_backoff_seconds_grows_exponentially() -> None:
    assert compute_backoff_seconds(0, 2.0) == 2.0
    assert compute_backoff_seconds(1, 2.0) == 4.0
    assert compute_backoff_seconds(2, 2.0) == 8.0


@pytest.mark.asyncio
async def test_worker_dedup_transitions_unique_alert_and_publishes_sse() -> None:
    job = _make_job()
    alert = _make_alert_record(job, AlertStatus.RECEIVED)
    session_factory = _make_session_factory(alert)
    redis_client = AsyncMock()
    redis_client.set.return_value = True  # Acquired dedup lock

    result = await process_single_job(
        raw_job=job.model_dump_json(),
        redis_client=redis_client,
        session_factory=session_factory,
        settings=Settings(worker_max_retries=3),
    )

    assert result == AlertStatus.DEDUPED
    assert alert.current_status == AlertStatus.DEDUPED.value
    redis_client.publish.assert_awaited_once()
    redis_client.rpush.assert_not_awaited()


@pytest.mark.asyncio
async def test_worker_marks_duplicate_within_window_as_ignored_duplicate() -> None:
    job = _make_job()
    alert = _make_alert_record(job, AlertStatus.RECEIVED)
    session_factory = _make_session_factory(alert)
    redis_client = AsyncMock()
    redis_client.set.return_value = None  # Lock already held by recent alert

    result = await process_single_job(
        raw_job=job.model_dump_json(),
        redis_client=redis_client,
        session_factory=session_factory,
        settings=Settings(),
    )

    assert result == AlertStatus.IGNORED_DUPLICATE
    assert alert.current_status == AlertStatus.IGNORED_DUPLICATE.value
    redis_client.publish.assert_awaited_once()


@pytest.mark.asyncio
async def test_worker_schedules_exponential_retry_before_max_retries() -> None:
    job = _make_job(attempt=1)
    alert = _make_alert_record(job, AlertStatus.DEDUPED)
    session_factory = _make_session_factory(alert)
    redis_client = AsyncMock()

    async def failing_step(_: AlertJobMessage) -> None:
        raise RuntimeError("transient downstream timeout")

    result = await process_single_job(
        raw_job=job.model_dump_json(),
        redis_client=redis_client,
        session_factory=session_factory,
        settings=Settings(worker_max_retries=3, worker_retry_base_seconds=2.0),
        pipeline_step=failing_step,
    )

    assert result == AlertStatus.RECEIVED
    redis_client.zadd.assert_awaited_once()
    scheduled_mapping = redis_client.zadd.call_args.args[1]
    scheduled_job_json = next(iter(scheduled_mapping))
    assert AlertJobMessage.model_validate_json(scheduled_job_json).attempt == 2
    redis_client.rpush.assert_not_awaited()


@pytest.mark.asyncio
async def test_worker_moves_exhausted_job_to_dlq_and_publishes_sse() -> None:
    job = _make_job(attempt=3)
    alert = _make_alert_record(job, AlertStatus.DEDUPED)
    session_factory = _make_session_factory(alert)
    redis_client = AsyncMock()

    async def failing_step(_: AlertJobMessage) -> None:
        raise RuntimeError("permanent failure")

    result = await process_single_job(
        raw_job=job.model_dump_json(),
        redis_client=redis_client,
        session_factory=session_factory,
        settings=Settings(worker_max_retries=3),
        pipeline_step=failing_step,
    )

    assert result == AlertStatus.FAILED_DLQ
    assert alert.current_status == AlertStatus.FAILED_DLQ.value
    redis_client.publish.assert_awaited_once()
    redis_client.rpush.assert_awaited_once()
    dlq_payload = json.loads(redis_client.rpush.call_args.args[1])
    assert dlq_payload["job"]["alert_id"] == str(job.alert_id)
    assert "RuntimeError: permanent failure" in dlq_payload["error"]


@pytest.mark.asyncio
async def test_get_alert_detail_and_sse_stream_replay_and_live_events() -> None:
    job = _make_job()
    alert = _make_alert_record(job, AlertStatus.RECEIVED)
    now = datetime.now(UTC)

    initial_event = AlertEventRecord(
        id=uuid4(),
        alert_id=alert.id,
        from_status=None,
        to_status=AlertStatus.RECEIVED.value,
        reason="Ingested via POST /v1/alerts",
        event_metadata={},
        created_at=now,
    )
    live_terminal_event = AlertStreamEvent(
        event_id=uuid4(),
        alert_id=alert.id,
        from_status=AlertStatus.RECEIVED,
        to_status=AlertStatus.IGNORED_DUPLICATE,
        reason="Duplicate alert",
        metadata={},
        created_at=now,
    )

    fake_pubsub = AsyncMock()
    # First message repeats initial_event (must be deduped); second is terminal live event.
    duplicate_msg = AlertStreamEvent(
        event_id=initial_event.id,
        alert_id=alert.id,
        from_status=None,
        to_status=AlertStatus.RECEIVED,
        reason="Ingested via POST /v1/alerts",
        metadata={},
        created_at=now,
    )
    fake_pubsub.get_message.side_effect = [
        {"type": "message", "data": duplicate_msg.model_dump_json()},
        {"type": "message", "data": live_terminal_event.model_dump_json()},
    ]

    fake_redis = MagicMock()
    fake_redis.pubsub.return_value = fake_pubsub

    app.dependency_overrides[get_redis] = lambda: fake_redis
    app.dependency_overrides[get_db_session] = lambda: AsyncMock()

    try:
        with patch(
            "app.api.alerts.get_alert_with_events",
            new=AsyncMock(return_value=(alert, [initial_event])),
        ):
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                detail = await client.get(f"/v1/alerts/{alert.id}")
                stream = await client.get(f"/v1/alerts/{alert.id}/stream")
    finally:
        app.dependency_overrides.clear()

    assert detail.status_code == 200
    assert detail.json()["alert_id"] == str(alert.id)
    assert len(detail.json()["events"]) == 1

    assert stream.status_code == 200
    assert stream.headers["content-type"].startswith("text/event-stream")
    body = stream.text
    assert body.count("event: alert_status") == 2
    assert "RECEIVED" in body
    assert "IGNORED_DUPLICATE" in body
    fake_pubsub.unsubscribe.assert_awaited_once()
    fake_pubsub.aclose.assert_awaited_once()
