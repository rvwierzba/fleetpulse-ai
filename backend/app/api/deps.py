"""Shared FastAPI dependency providers decoupled from app.main."""

from collections.abc import AsyncIterator

from fastapi import Request
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession


def get_redis(request: Request) -> Redis:
    """Provide the shared async Redis client stored in app state."""
    return request.app.state.redis


def get_db_engine(request: Request) -> AsyncEngine:
    """Provide the shared async SQLAlchemy engine stored in app state."""
    return request.app.state.db_engine


async def get_db_session(request: Request) -> AsyncIterator[AsyncSession]:
    """Yield a scoped async SQLAlchemy session for the current request."""
    session_factory = request.app.state.session_factory
    async with session_factory() as session:
        yield session
