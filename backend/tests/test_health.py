"""Tests for FastAPI health endpoint and Redis connectivity helpers."""

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from redis.exceptions import ConnectionError as RedisConnectionError

from app.api.deps import get_db_engine, get_redis
from app.infra.redis_client import enqueue_alert, ping_redis, queue_length
from app.main import app


def _make_fake_engine(healthy: bool = True) -> MagicMock:
    """Build a mock AsyncEngine whose connect() succeeds or raises."""
    conn = AsyncMock()
    if not healthy:
        from sqlalchemy.exc import OperationalError

        conn.execute.side_effect = OperationalError("SELECT 1", {}, Exception("down"))
    cm = AsyncMock()
    cm.__aenter__.return_value = conn
    cm.__aexit__.return_value = False
    engine = MagicMock()
    engine.connect.return_value = cm
    return engine


@pytest.mark.asyncio
async def test_health_returns_ok_when_redis_and_postgres_are_reachable() -> None:
    fake_redis = AsyncMock()
    fake_redis.ping.return_value = True
    fake_redis.llen.return_value = 3
    fake_engine = _make_fake_engine(healthy=True)

    app.dependency_overrides[get_redis] = lambda: fake_redis
    app.dependency_overrides[get_db_engine] = lambda: fake_engine

    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/health")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "fleetpulse-api",
        "redis": "connected",
        "postgres": "connected",
        "queue_depth": 3,
    }


@pytest.mark.asyncio
async def test_health_returns_503_when_redis_is_unreachable() -> None:
    fake_redis = AsyncMock()
    fake_redis.ping.side_effect = RedisConnectionError("connection refused")
    fake_engine = _make_fake_engine(healthy=True)

    app.dependency_overrides[get_redis] = lambda: fake_redis
    app.dependency_overrides[get_db_engine] = lambda: fake_engine

    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/health")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503
    assert response.json() == {
        "status": "degraded",
        "service": "fleetpulse-api",
        "redis": "unreachable",
        "postgres": "connected",
    }


@pytest.mark.asyncio
async def test_redis_helpers_handle_errors_and_queue_operations() -> None:
    fake_redis = AsyncMock()
    fake_redis.ping.side_effect = RedisConnectionError("timeout")
    assert await ping_redis(fake_redis) is False

    fake_redis.rpush.return_value = 1
    fake_redis.llen.return_value = 1
    assert await enqueue_alert(fake_redis, "fleetpulse:alerts:queue", '{"id":"1"}') == 1
    assert await queue_length(fake_redis, "fleetpulse:alerts:queue") == 1
