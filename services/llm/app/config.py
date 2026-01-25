"""Configuration for the LLM worker service."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Centralized configuration for the LLM worker.

    Attributes:
        database_url: Async database connection string.
        redis_url: Redis connection string for ARQ queue.
        openai_api_key: API key for OpenAI requests.
        log_level: Logging verbosity for the worker.
        service_name: Name used in logs and tracing.
    """

    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/league_api"
    redis_url: str = "redis://localhost:6379/0"
    openai_api_key: str = "replace-me"
    log_level: str = "INFO"
    service_name: str = "league-llm"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    """Load and cache the worker settings.

    Returns:
        Cached Settings instance for the current process.
    """
    return Settings()
