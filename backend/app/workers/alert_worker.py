"""Async Redis queue consumer implementing dedup, exponential retry, and DLQ."""

import asyncio
import json
import logging
import signal
import time
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.domain.enums import AlertStatus
from app.domain.schemas import AlertJobMessage
from app.infra.config import Settings, get_settings
from app.infra.database import (
    AlertRecord,
    create_db_engine,
    create_session_factory,
    init_db,
    to_stream_event,
    transition_alert_state,
)
from app.infra.redis_client import (
    acquire_dedup_lock,
    claim_due_retries,
    create_redis_client,
    pop_alert_job,
    publish_alert_event,
    push_to_dlq,
    schedule_retry_job,
)
from app.ml.service import get_ml_service
from app.rag.orchestrator import get_hybrid_rag_orchestrator

logger = logging.getLogger("fleetpulse.worker")

PipelineStep = Callable[[AlertJobMessage], Awaitable[None]]


def compute_backoff_seconds(attempt: int, base_seconds: float) -> float:
    """Calculate exponential backoff delay in seconds for a failed attempt."""
    return float(base_seconds * (2**attempt))


async def _default_pipeline_step(job: AlertJobMessage) -> None:
    """Placeholder downstream hook extended by ML/RAG/Agent sprints."""
    _ = job


async def _transition_and_publish(
    session_factory: async_sessionmaker[AsyncSession],
    redis_client: Redis,
    job: AlertJobMessage,
    target_status: AlertStatus,
    reason: str,
    metadata: dict[str, object] | None = None,
) -> None:
    """Persist state transition in PostgreSQL and broadcast it to SSE subscribers."""
    async with session_factory() as session:
        event = await transition_alert_state(
            session=session,
            alert_id=job.alert_id,
            target_status=target_status,
            reason=reason,
            metadata=metadata,
        )
    stream_event = to_stream_event(event)
    await publish_alert_event(redis_client, job.alert_id, stream_event.model_dump_json())


async def process_single_job(
    raw_job: str,
    redis_client: Redis,
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    pipeline_step: PipelineStep | None = None,
) -> AlertStatus:
    """Process one dequeued alert job with deduplication, exponential retry, and DLQ."""
    job = AlertJobMessage.model_validate_json(raw_job)
    step = pipeline_step or _default_pipeline_step

    try:
        async with session_factory() as session:
            alert = await session.get(AlertRecord, job.alert_id)
            if alert is None:
                raise LookupError(f"Alert {job.alert_id} missing from PostgreSQL")
            current_status = AlertStatus(alert.current_status)

        # Skip dedup on retries of an already-deduped job so retries are never misclassified.
        if current_status == AlertStatus.RECEIVED:
            is_first = await acquire_dedup_lock(
                client=redis_client,
                device_id=job.device_id,
                error_code=job.error_code,
                window_seconds=settings.alert_dedup_window_seconds,
            )
            if not is_first:
                await _transition_and_publish(
                    session_factory=session_factory,
                    redis_client=redis_client,
                    job=job,
                    target_status=AlertStatus.IGNORED_DUPLICATE,
                    reason="Duplicate device_id + error_code within deduplication window",
                    metadata={"window_seconds": settings.alert_dedup_window_seconds},
                )
                return AlertStatus.IGNORED_DUPLICATE

            await _transition_and_publish(
                session_factory=session_factory,
                redis_client=redis_client,
                job=job,
                target_status=AlertStatus.DEDUPED,
                reason="Passed deduplication window",
                metadata={"attempt": job.attempt},
            )
            current_status = AlertStatus.DEDUPED

        # ML Scoring Step: Predict RMA risk, SLA breach probability, and local SHAP attributions
        if current_status == AlertStatus.DEDUPED:
            async with session_factory() as session:
                alert = await session.get(AlertRecord, job.alert_id)
                if alert is None:
                    raise LookupError(f"Alert {job.alert_id} missing from PostgreSQL")
                alert_dict = {
                    "device_type": alert.device_type,
                    "model_code": alert.model_code,
                    "batch_id": alert.batch_id,
                    "firmware_version": alert.firmware_version,
                    "sla_tier": alert.sla_tier,
                    "age_days": alert.age_days,
                    "subsystem": alert.subsystem,
                    "error_code": alert.error_code,
                    "telemetry": alert.telemetry,
                }

            ml_service = get_ml_service()
            score_res = ml_service.score_alert(alert_dict)

            await _transition_and_publish(
                session_factory=session_factory,
                redis_client=redis_client,
                job=job,
                target_status=AlertStatus.ML_SCORED,
                reason="Tabular ML scoring and SHAP attribution completed",
                metadata={
                    "rma_risk_score": score_res.rma_risk_score,
                    "sla_breach_risk": score_res.sla_breach_risk,
                    "predicted_subsystem": score_res.predicted_subsystem.value,
                    "shap_factors": [f.model_dump() for f in score_res.shap_factors],
                    "model_version": score_res.model_version,
                },
            )
            current_status = AlertStatus.ML_SCORED

        if current_status == AlertStatus.ML_SCORED:
            async with session_factory() as session:
                alert = await session.get(AlertRecord, job.alert_id)
                if alert is None:
                    raise LookupError(f"Alert {job.alert_id} missing from PostgreSQL")

                rag_orchestrator = get_hybrid_rag_orchestrator()
                rag_res = await rag_orchestrator.enrich_alert_context(
                    session=session,
                    redis_client=redis_client,
                    device_type=alert.device_type,
                    model_code=alert.model_code,
                    batch_id=alert.batch_id,
                    firmware_version=alert.firmware_version,
                    error_code=alert.error_code,
                    subsystem=alert.subsystem,
                    description=alert.description or "",
                    telemetry=alert.telemetry or {},
                )

            await _transition_and_publish(
                session_factory=session_factory,
                redis_client=redis_client,
                job=job,
                target_status=AlertStatus.CONTEXT_RETRIEVED,
                reason="Hybrid RAG context retrieved (Neo4j + pgvector + Cache)",
                metadata={
                    "rag_context": rag_res.model_dump(),
                    "matched_runbook_id": rag_res.matched_runbook_id,
                    "matched_bulletin_id": rag_res.matched_bulletin_id,
                    "semantic_cache_hit": rag_res.cache_hit,
                    "cache_type": rag_res.cache_type,
                },
            )
            current_status = AlertStatus.CONTEXT_RETRIEVED

        await step(job)
        return current_status

    except Exception as exc:
        if job.attempt < settings.worker_max_retries:
            delay_seconds = compute_backoff_seconds(job.attempt, settings.worker_retry_base_seconds)
            next_job = job.model_copy(update={"attempt": job.attempt + 1})
            execute_at = time.time() + delay_seconds
            await schedule_retry_job(
                client=redis_client,
                retry_zset_name=settings.alert_retry_zset_name,
                serialized_job=next_job.model_dump_json(),
                execute_at_epoch=execute_at,
            )
            logger.warning(
                "Scheduled retry %s/%s for alert %s in %.1fs (%s)",
                next_job.attempt,
                settings.worker_max_retries,
                job.alert_id,
                delay_seconds,
                exc,
            )
            return AlertStatus.RECEIVED

        error_detail = f"{type(exc).__name__}: {exc}"
        await _transition_and_publish(
            session_factory=session_factory,
            redis_client=redis_client,
            job=job,
            target_status=AlertStatus.FAILED_DLQ,
            reason="Worker exhausted max retries",
            metadata={"attempts": job.attempt, "error": error_detail},
        )
        dlq_envelope = json.dumps(
            {
                "job": job.model_dump(mode="json"),
                "error": error_detail,
                "failed_at": datetime.now(UTC).isoformat(),
            }
        )
        await push_to_dlq(redis_client, settings.alert_dlq_name, dlq_envelope)
        logger.error("Moved alert %s to DLQ after %s retries: %s", job.alert_id, job.attempt, exc)
        return AlertStatus.FAILED_DLQ


async def run_worker_loop(
    settings: Settings,
    stop_event: asyncio.Event | None = None,
    pipeline_step: PipelineStep | None = None,
) -> None:
    """Continuously drain due retries and FIFO queue jobs until stop_event is set."""
    signal_stop = stop_event or asyncio.Event()
    redis_client = create_redis_client(
        redis_url=settings.redis_url,
        timeout_seconds=settings.redis_timeout_seconds,
    )
    db_engine = create_db_engine(
        database_url=settings.database_url,
        timeout_seconds=settings.database_timeout_seconds,
    )
    await init_db(db_engine)
    session_factory = create_session_factory(db_engine)

    try:
        while not signal_stop.is_set():
            await claim_due_retries(
                client=redis_client,
                retry_zset_name=settings.alert_retry_zset_name,
                queue_name=settings.alert_queue_name,
                now_epoch=time.time(),
            )
            raw_job = await pop_alert_job(
                client=redis_client,
                queue_name=settings.alert_queue_name,
                timeout_seconds=settings.worker_poll_timeout_seconds,
            )
            if raw_job is None:
                continue
            await process_single_job(
                raw_job=raw_job,
                redis_client=redis_client,
                session_factory=session_factory,
                settings=settings,
                pipeline_step=pipeline_step,
            )
    finally:
        await redis_client.aclose()
        await db_engine.dispose()


def main() -> None:
    """CLI entrypoint to run the FleetPulse alert worker as a standalone process."""
    settings = get_settings()
    logging.basicConfig(level=settings.app_log_level)
    stop_event = asyncio.Event()

    def _handle_stop(*_: object) -> None:
        stop_event.set()

    signal.signal(signal.SIGINT, _handle_stop)
    signal.signal(signal.SIGTERM, _handle_stop)
    asyncio.run(run_worker_loop(settings=settings, stop_event=stop_event))


if __name__ == "__main__":
    main()
