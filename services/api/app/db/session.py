from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel

from app.core.config import get_settings
from app.models import *  # noqa: F401, F403


settings = get_settings()
engine = create_async_engine(
    settings.database_url,
    echo=settings.sql_echo,
    pool_pre_ping=True,
)
AsyncSessionLocal = sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

# Alias used by background jobs (app.jobs.match_ingestion, app.jobs.scheduled)
async_session_factory = AsyncSessionLocal


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield an async SQLAlchemy session for request handling.

    Yields:
        AsyncSession instance for database operations.
    """
    async with AsyncSessionLocal() as session:
        yield session
