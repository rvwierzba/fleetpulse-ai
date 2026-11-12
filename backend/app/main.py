"""FastAPI application entrypoint for FleetPulse AI."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, status
from fastapi.responses import JSONResponse
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine

from app.api.alerts import router as alerts_router
from app.api.deps import get_db_engine, get_redis
from app.infra.config import Settings, get_settings
from app.infra.database import create_db_engine, create_session_factory, init_db, ping_db
from app.infra.redis_client import create_redis_client, ping_redis, queue_length


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Manage startup and graceful shutdown of shared Redis and PostgreSQL clients."""
    settings = get_settings()
    redis_client = create_redis_client(
        redis_url=settings.redis_url,
        timeout_seconds=settings.redis_timeout_seconds,
    )
    db_engine = create_db_engine(
        database_url=settings.database_url,
        timeout_seconds=settings.database_timeout_seconds,
    )
    await init_db(db_engine)

    app.state.redis = redis_client
    app.state.db_engine = db_engine
    app.state.session_factory = create_session_factory(db_engine)
    try:
        yield
    finally:
        await redis_client.aclose()
        await db_engine.dispose()


app = FastAPI(
    title="FleetPulse AI API",
    version="0.1.0",
    lifespan=lifespan,
)
app.include_router(alerts_router)


@app.get("/health", tags=["health"])
async def health_check(
    redis_client: Redis = Depends(get_redis),  # noqa: B008
    db_engine: AsyncEngine = Depends(get_db_engine),  # noqa: B008
    settings: Settings = Depends(get_settings),  # noqa: B008
) -> JSONResponse:
    """Verify API availability and live connectivity with Redis and PostgreSQL."""
    redis_ok = await ping_redis(redis_client)
    db_ok = await ping_db(db_engine)

    if not redis_ok or not db_ok:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "status": "degraded",
                "service": "fleetpulse-api",
                "redis": "connected" if redis_ok else "unreachable",
                "postgres": "connected" if db_ok else "unreachable",
            },
        )

    depth = await queue_length(redis_client, settings.alert_queue_name)
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "status": "ok",
            "service": "fleetpulse-api",
            "redis": "connected",
            "postgres": "connected",
            "queue_depth": depth,
        },
    )
