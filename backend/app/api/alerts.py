"""Non-blocking alert ingestion, detail query, and live SSE streaming endpoints."""

from collections.abc import AsyncIterator
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.router import get_hybrid_ai_router
from app.api.deps import get_db_session, get_redis
from app.domain.enums import AlertStatus, DeviceType, SLATier, Subsystem, get_sla_targets
from app.domain.schemas import (
    AlertAcceptedResponse,
    AlertCreateRequest,
    AlertDetailResponse,
    AlertJobMessage,
    AlertStreamEvent,
    ResolveAlertRequest,
    SystemMetricsResponse,
)
from app.infra.config import Settings, get_settings
from app.infra.database import (
    AlertEventRecord,
    AlertRecord,
    create_alert_with_received_event,
    get_alert_with_events,
    get_system_metrics_summary,
    list_recent_alerts,
    to_stream_event,
    transition_alert_state,
)
from app.infra.redis_client import (
    check_rate_limit,
    enqueue_alert,
    get_idempotent_response,
    publish_alert_event,
    queue_length,
    store_idempotent_response,
    stream_channel_name,
)

router = APIRouter(prefix="/v1/alerts", tags=["alerts"])

TERMINAL_STREAM_STATUSES = frozenset(
    {
        AlertStatus.IGNORED_DUPLICATE,
        AlertStatus.RESOLVED,
        AlertStatus.FAILED_DLQ,
    }
)


def _build_accepted_response(
    alert: AlertRecord,
    deduplicated_request: bool,
) -> AlertAcceptedResponse:
    """Map an AlertRecord into the 202 Accepted API contract."""
    first_response_hours, resolution_hours = get_sla_targets(SLATier(alert.sla_tier))
    return AlertAcceptedResponse(
        alert_id=alert.id,
        status=AlertStatus(alert.current_status),
        idempotency_key=alert.idempotency_key,
        sla_first_response_hours=first_response_hours,
        sla_resolution_hours=resolution_hours,
        created_at=alert.created_at,
        deduplicated_request=deduplicated_request,
    )


def _format_sse_frame(event: AlertStreamEvent) -> str:
    """Format an AlertStreamEvent as a Server-Sent Events wire frame."""
    return f"id: {event.event_id}\nevent: alert_status\ndata: {event.model_dump_json()}\n\n"


@router.post(
    "",
    response_model=AlertAcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def ingest_alert(
    payload: AlertCreateRequest,
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=1, max_length=128),
    redis_client: Redis = Depends(get_redis),  # noqa: B008
    db_session: AsyncSession = Depends(get_db_session),  # noqa: B008
    settings: Settings = Depends(get_settings),  # noqa: B008
) -> AlertAcceptedResponse:
    """Validate, rate-limit, persist RECEIVED state, enqueue job, and return 202."""
    normalized_key = idempotency_key.strip()
    if not normalized_key:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Idempotency-Key header must not be blank.",
        )

    allowed, retry_after = await check_rate_limit(
        client=redis_client,
        source_id=payload.source_id,
        limit_per_minute=settings.rate_limit_per_minute,
    )
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded for source_id.",
            headers={"Retry-After": str(retry_after)},
        )

    cached_json = await get_idempotent_response(redis_client, normalized_key)
    if cached_json is not None:
        cached_response = AlertAcceptedResponse.model_validate_json(cached_json)
        return cached_response.model_copy(update={"deduplicated_request": True})

    alert, initial_event, already_existed = await create_alert_with_received_event(
        session=db_session,
        payload=payload,
        idempotency_key=normalized_key,
    )
    response = _build_accepted_response(alert, deduplicated_request=already_existed)

    canonical_response = response.model_copy(update={"deduplicated_request": False})
    await store_idempotent_response(
        client=redis_client,
        idempotency_key=normalized_key,
        serialized_response=canonical_response.model_dump_json(),
        ttl_seconds=settings.idempotency_ttl_seconds,
    )

    if not already_existed:
        if initial_event is not None:
            stream_event = to_stream_event(initial_event)
            await publish_alert_event(redis_client, alert.id, stream_event.model_dump_json())

        job = AlertJobMessage(
            alert_id=alert.id,
            device_id=payload.device_id,
            device_type=payload.device_type,
            subsystem=payload.subsystem,
            error_code=payload.error_code,
            sla_tier=payload.sla_tier,
            enqueued_at=alert.created_at,
        )
        await enqueue_alert(redis_client, settings.alert_queue_name, job.model_dump_json())

    return response


def _map_alert_detail(
    alert: AlertRecord,
    events: list[AlertEventRecord],
) -> AlertDetailResponse:
    """Map an AlertRecord and its event records to AlertDetailResponse."""
    return AlertDetailResponse(
        alert_id=alert.id,
        device_id=alert.device_id,
        device_type=DeviceType(alert.device_type),
        subsystem=Subsystem(alert.subsystem),
        error_code=alert.error_code,
        sla_tier=SLATier(alert.sla_tier),
        current_status=AlertStatus(alert.current_status),
        rma_risk_score=alert.rma_risk_score,
        sla_breach_risk=alert.sla_breach_risk,
        predicted_subsystem=(
            Subsystem(alert.predicted_subsystem)
            if alert.predicted_subsystem
            else None
        ),
        shap_factors=alert.shap_factors,
        rag_context=alert.rag_context,
        matched_runbook_id=alert.matched_runbook_id,
        matched_bulletin_id=alert.matched_bulletin_id,
        semantic_cache_hit=alert.semantic_cache_hit,
        agent_diagnosis=alert.agent_diagnosis,
        triage_action=alert.triage_action,
        agent_confidence=alert.agent_confidence,
        requires_human_approval=alert.requires_human_approval,
        created_at=alert.created_at,
        updated_at=alert.updated_at,
        events=[to_stream_event(event) for event in events],
    )


@router.get("", response_model=list[AlertDetailResponse])
async def list_alerts(
    limit: int = 50,
    offset: int = 0,
    status_filter: str | None = None,
    db_session: AsyncSession = Depends(get_db_session),  # noqa: B008
) -> list[AlertDetailResponse]:
    """Return paginated list of fleet alerts for dashboard."""
    records = await list_recent_alerts(
        session=db_session,
        limit=limit,
        offset=offset,
        status_filter=status_filter,
    )
    return [_map_alert_detail(a, ev) for a, ev in records]


@router.get("/metrics/summary", response_model=SystemMetricsResponse)
async def get_metrics_summary(
    db_session: AsyncSession = Depends(get_db_session),  # noqa: B008
    redis_client: Redis = Depends(get_redis),  # noqa: B008
    settings: Settings = Depends(get_settings),  # noqa: B008
) -> SystemMetricsResponse:
    """Consolidated system observability telemetry for frontend."""
    summary = await get_system_metrics_summary(db_session)
    router_inst = get_hybrid_ai_router()
    dlq_len = await queue_length(redis_client, settings.alert_dlq_name)

    return SystemMetricsResponse(
        total_alerts=summary["total_alerts"],
        alerts_by_status=summary["alerts_by_status"],
        high_rma_alerts=summary["high_rma_alerts"],
        pending_human_review=summary["pending_human_review"],
        dlq_count=dlq_len,
        circuit_breaker_state=router_inst.circuit_state.value,
        semantic_cache_hit_rate=summary["semantic_cache_hit_rate"],
        primary_model=router_inst.primary_model,
        fallback_model=router_inst.fallback_model,
    )


@router.post("/{alert_id}/resolve", response_model=AlertDetailResponse)
async def resolve_alert_by_operator(
    alert_id: UUID,
    payload: ResolveAlertRequest,
    db_session: AsyncSession = Depends(get_db_session),  # noqa: B008
    redis_client: Redis = Depends(get_redis),  # noqa: B008
) -> AlertDetailResponse:
    """Human-in-the-loop operator action resolving an alert."""
    found = await get_alert_with_events(db_session, alert_id)
    if found is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert not found.")

    alert, _ = found
    current_st = AlertStatus(alert.current_status)
    if current_st not in (
        AlertStatus.HUMAN_REVIEW,
        AlertStatus.AUTO_RECOMMENDED,
        AlertStatus.SCHEMA_VALIDATED,
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Alert in status {current_st.value} cannot be resolved directly.",
        )

    event = await transition_alert_state(
        session=db_session,
        alert_id=alert_id,
        target_status=AlertStatus.RESOLVED,
        reason=f"Operator {payload.operator_id} resolved: {payload.action_taken}",
        metadata={
            "operator_id": payload.operator_id,
            "action_taken": payload.action_taken,
            "resolution_note": payload.resolution_note,
        },
    )
    stream_event = to_stream_event(event)
    await publish_alert_event(redis_client, alert.id, stream_event.model_dump_json())

    updated = await get_alert_with_events(db_session, alert_id)
    assert updated is not None
    upd_alert, upd_events = updated
    return _map_alert_detail(upd_alert, upd_events)


@router.get("/{alert_id}", response_model=AlertDetailResponse)
async def get_alert_detail(
    alert_id: UUID,
    db_session: AsyncSession = Depends(get_db_session),  # noqa: B008
) -> AlertDetailResponse:
    """Return current alert status alongside its full audit event history."""
    found = await get_alert_with_events(db_session, alert_id)
    if found is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert not found.")

    alert, events = found
    return _map_alert_detail(alert, events)


@router.get("/{alert_id}/stream")
async def stream_alert_events(
    alert_id: UUID,
    request: Request,
    redis_client: Redis = Depends(get_redis),  # noqa: B008
    db_session: AsyncSession = Depends(get_db_session),  # noqa: B008
    settings: Settings = Depends(get_settings),  # noqa: B008
) -> StreamingResponse:
    """Stream alert state transitions in real time via Server-Sent Events (SSE)."""
    channel = stream_channel_name(alert_id)
    pubsub = redis_client.pubsub()
    # Subscribe before reading DB snapshot so transitions occurring mid-handshake are not missed.
    await pubsub.subscribe(channel)

    found = await get_alert_with_events(db_session, alert_id)
    if found is None:
        await pubsub.unsubscribe(channel)
        await pubsub.aclose()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert not found.")

    alert, historical_events = found

    async def event_generator() -> AsyncIterator[str]:
        seen_ids: set[UUID] = set()
        try:
            for record in historical_events:
                stream_event = to_stream_event(record)
                seen_ids.add(stream_event.event_id)
                yield _format_sse_frame(stream_event)
                if stream_event.to_status in TERMINAL_STREAM_STATUSES:
                    return

            if AlertStatus(alert.current_status) in TERMINAL_STREAM_STATUSES:
                return

            while not await request.is_disconnected():
                message = await pubsub.get_message(
                    ignore_subscribe_messages=True,
                    timeout=settings.sse_keepalive_seconds,
                )
                if message is None:
                    yield ": keepalive\n\n"
                    continue

                raw_data = message.get("data")
                if not isinstance(raw_data, str):
                    continue

                live_event = AlertStreamEvent.model_validate_json(raw_data)
                if live_event.event_id in seen_ids:
                    continue

                seen_ids.add(live_event.event_id)
                yield _format_sse_frame(live_event)
                if live_event.to_status in TERMINAL_STREAM_STATUSES:
                    return
        finally:
            await pubsub.unsubscribe(channel)
            await pubsub.aclose()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
