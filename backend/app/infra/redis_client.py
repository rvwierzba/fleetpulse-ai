"""Async Redis client, queue helpers, rate limiter, dedup lock, and Pub/Sub."""

from uuid import UUID

from redis.asyncio import Redis
from redis.exceptions import RedisError

RATE_LIMIT_PREFIX = "fleetpulse:ratelimit:"
IDEMPOTENCY_PREFIX = "fleetpulse:idempotency:"
DEDUP_PREFIX = "fleetpulse:dedup:"
STREAM_CHANNEL_PREFIX = "fleetpulse:alerts:stream:"


def create_redis_client(
    redis_url: str,
    timeout_seconds: float = 5.0,
) -> Redis:
    """Create an async Redis client with explicit connection and socket timeouts."""
    return Redis.from_url(
        redis_url,
        encoding="utf-8",
        decode_responses=True,
        socket_connect_timeout=timeout_seconds,
        socket_timeout=timeout_seconds,
    )


async def ping_redis(client: Redis) -> bool:
    """Return True if Redis responds to PING, False on connection or timeout errors."""
    try:
        return bool(await client.ping())
    except RedisError:
        return False


async def enqueue_alert(client: Redis, queue_name: str, serialized_job: str) -> int:
    """Push a serialized alert job to the tail of the FIFO Redis queue."""
    return int(await client.rpush(queue_name, serialized_job))


async def pop_alert_job(
    client: Redis,
    queue_name: str,
    timeout_seconds: float = 2.0,
) -> str | None:
    """Pop the oldest serialized job from the FIFO queue, blocking up to timeout."""
    result = await client.blpop([queue_name], timeout=max(int(timeout_seconds), 1))
    if result is None:
        return None
    _, serialized_job = result
    return str(serialized_job)


async def queue_length(client: Redis, queue_name: str) -> int:
    """Return current number of pending jobs in the specified Redis queue."""
    return int(await client.llen(queue_name))


async def check_rate_limit(
    client: Redis,
    source_id: str,
    limit_per_minute: int,
    window_seconds: int = 60,
) -> tuple[bool, int]:
    """Increment per-source fixed-window counter; return (allowed, retry_after_seconds)."""
    key = f"{RATE_LIMIT_PREFIX}{source_id}"
    count = int(await client.incr(key))
    if count == 1:
        await client.expire(key, window_seconds)

    if count <= limit_per_minute:
        return True, 0

    ttl = int(await client.ttl(key))
    if ttl < 0:
        await client.expire(key, window_seconds)
        ttl = window_seconds
    return False, max(ttl, 1)


async def get_idempotent_response(client: Redis, idempotency_key: str) -> str | None:
    """Fetch a previously cached serialized 202 response for this Idempotency-Key."""
    return await client.get(f"{IDEMPOTENCY_PREFIX}{idempotency_key}")


async def store_idempotent_response(
    client: Redis,
    idempotency_key: str,
    serialized_response: str,
    ttl_seconds: int,
) -> None:
    """Cache the serialized 202 response in Redis for duplicate request replays."""
    await client.set(f"{IDEMPOTENCY_PREFIX}{idempotency_key}", serialized_response, ex=ttl_seconds)


async def acquire_dedup_lock(
    client: Redis,
    device_id: str,
    error_code: str,
    window_seconds: int,
) -> bool:
    """Return True if this device_id + error_code is new inside the dedup window."""
    key = f"{DEDUP_PREFIX}{device_id}:{error_code}"
    acquired = await client.set(key, "1", nx=True, ex=window_seconds)
    return bool(acquired)


def stream_channel_name(alert_id: UUID | str) -> str:
    """Return the Redis Pub/Sub channel name for a specific alert's SSE stream."""
    return f"{STREAM_CHANNEL_PREFIX}{alert_id}"


async def publish_alert_event(client: Redis, alert_id: UUID | str, event_json: str) -> int:
    """Publish a serialized AlertStreamEvent to the alert's Pub/Sub channel."""
    return int(await client.publish(stream_channel_name(alert_id), event_json))


async def schedule_retry_job(
    client: Redis,
    retry_zset_name: str,
    serialized_job: str,
    execute_at_epoch: float,
) -> int:
    """Schedule a failed job for future retry in a Redis sorted set scored by epoch."""
    return int(await client.zadd(retry_zset_name, {serialized_job: execute_at_epoch}))


async def claim_due_retries(
    client: Redis,
    retry_zset_name: str,
    queue_name: str,
    now_epoch: float,
    batch_size: int = 20,
) -> int:
    """Move due retry jobs whose backoff elapsed back onto the main FIFO queue."""
    due_jobs = await client.zrangebyscore(
        retry_zset_name,
        min="-inf",
        max=now_epoch,
        start=0,
        num=batch_size,
    )
    moved = 0
    for serialized_job in due_jobs:
        removed = await client.zrem(retry_zset_name, serialized_job)
        if removed == 1:
            await enqueue_alert(client, queue_name, str(serialized_job))
            moved += 1
    return moved


async def push_to_dlq(client: Redis, dlq_name: str, serialized_payload: str) -> int:
    """Push an exhausted job envelope to the Dead Letter Queue."""
    return int(await client.rpush(dlq_name, serialized_payload))
