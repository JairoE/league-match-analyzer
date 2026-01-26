from sqlalchemy import text
from sqlmodel import SQLModel

from app.core.logging import get_logger
from app.db.session import engine


logger = get_logger("league_api.db")


async def init_db() -> None:
    """Initialize database extensions and create tables.

    Returns:
        None.
    """
    logger.info("init_db_started")
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(SQLModel.metadata.create_all)
    logger.info("init_db_completed")
