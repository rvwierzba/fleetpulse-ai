"""Application configuration loaded from environment variables and root .env."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_ENV_FILE = Path(__file__).resolve().parents[3] / ".env"


class Settings(BaseSettings):
    """Typed runtime configuration for FleetPulse AI services."""

    model_config = SettingsConfigDict(
        env_file=ROOT_ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "FleetPulse AI API"
    app_env: str = "development"
    app_log_level: str = "INFO"

    database_url: str = (
        "postgresql+asyncpg://fleetpulse:fleetpulse_dev_pass@localhost:5432/fleetpulse"
    )
    database_timeout_seconds: float = 5.0

    redis_url: str = "redis://localhost:6379/0"
    redis_timeout_seconds: float = 5.0
    alert_queue_name: str = "fleetpulse:alerts:queue"
    alert_retry_zset_name: str = "fleetpulse:alerts:retry"
    alert_dlq_name: str = "fleetpulse:alerts:dlq"
    alert_dedup_window_seconds: int = 300
    idempotency_ttl_seconds: int = 86400
    rate_limit_per_minute: int = 120
    worker_max_retries: int = 3
    worker_retry_base_seconds: float = 2.0
    worker_poll_timeout_seconds: float = 2.0
    sse_keepalive_seconds: float = 15.0


@lru_cache
def get_settings() -> Settings:
    """Return cached Settings instance so env files are parsed only once."""
    return Settings()
