from functools import lru_cache
from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Centralized configuration for the FastAPI service.

    Attributes:
        environment: Runtime environment (development, staging, production).
        database_url: Async database connection string.
        redis_url: Redis connection string for cache and queues.
        riot_api_key: Riot API key for outbound requests.
        riot_api_timeout_seconds: Timeout for Riot API calls.
        log_level: Logging verbosity for the service.
        service_name: Name used in logs and tracing.
        sql_echo: Enables SQL echo for debugging.
        cors_allow_origins: Comma-separated list of allowed origins.
        cors_allow_methods: Comma-separated list of allowed HTTP methods.
        cors_allow_headers: Comma-separated list of allowed headers.
        cors_allow_credentials: Whether to allow credentials for CORS.
        arq_cron_run_at_startup: Whether ARQ cron jobs run immediately at worker
            startup. When None, derived from environment (True for development,
            False otherwise). Override via ARQ_CRON_RUN_AT_STARTUP env var.
    """

    environment: str = "development"
    database_url: str = "postgresql+asyncpg://league:league@localhost:5432/league"
    redis_url: str = "redis://localhost:6379/0"
    riot_api_key: str = "replace-me"
    riot_api_timeout_seconds: float = 10.0
    riot_default_platform: str = "NA1"
    log_level: str = "INFO"
    service_name: str = "league-api"
    sql_echo: bool = False
    cors_allow_origins: str = "http://localhost:3000"
    cors_allow_methods: str = "*"
    cors_allow_headers: str = "*"
    cors_allow_credentials: bool = True
    arq_cron_run_at_startup: bool | None = None

    _env_file = Path(__file__).resolve().parents[2] / ".env"

    @model_validator(mode="after")
    def _set_arq_cron_run_at_startup_from_environment(self: "Settings") -> "Settings":
        if self.arq_cron_run_at_startup is None:
            object.__setattr__(
                self,
                "arq_cron_run_at_startup",
                self.environment == "development",
            )
        return self

    model_config = SettingsConfigDict(env_file=_env_file, extra="ignore")


@lru_cache
def get_settings() -> Settings:
    """Load and cache the application settings.

    Returns:
        Cached Settings instance for the current process.
    """

    return Settings()
