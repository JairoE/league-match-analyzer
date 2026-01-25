from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Centralized configuration for the FastAPI service.

    Attributes:
        database_url: Async database connection string.
        redis_url: Redis connection string for cache and queues.
        riot_api_key: Riot API key for outbound requests.
        log_level: Logging verbosity for the service.
        service_name: Name used in logs and tracing.
        sql_echo: Enables SQL echo for debugging.
        cors_allow_origins: Comma-separated list of allowed origins.
        cors_allow_methods: Comma-separated list of allowed HTTP methods.
        cors_allow_headers: Comma-separated list of allowed headers.
        cors_allow_credentials: Whether to allow credentials for CORS.
    """

    database_url: str = "postgresql+asyncpg://league:league@localhost:5432/league"
    redis_url: str = "redis://localhost:6379/0"
    riot_api_key: str = "replace-me"
    log_level: str = "INFO"
    service_name: str = "league-api"
    sql_echo: bool = False
    cors_allow_origins: str = "http://localhost:3000"
    cors_allow_methods: str = "*"
    cors_allow_headers: str = "*"
    cors_allow_credentials: bool = True

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    """Load and cache the application settings.

    Returns:
        Cached Settings instance for the current process.
    """

    return Settings()
