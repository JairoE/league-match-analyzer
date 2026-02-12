from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.core.logging import get_logger
from app.models.user import User

logger = get_logger("league_api.services.users")


def parse_user_uuid(identifier: str) -> UUID | None:
    """Parse a user identifier into a UUID when possible.

    Args:
        identifier: User ID supplied in a route path or payload.

    Returns:
        Parsed UUID if valid, otherwise None.
    """
    try:
        return UUID(identifier)
    except (TypeError, ValueError):
        return None


async def get_user_by_id(session: AsyncSession, user_id: UUID) -> User | None:
    """Fetch a user by UUID.

    Args:
        session: Async database session for queries.
        user_id: UUID for the user record.

    Returns:
        User instance if found.
    """
    logger.info("get_user_by_id_start", extra={"user_id": str(user_id)})
    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    logger.info("get_user_by_id_done", extra={"user_id": str(user_id), "found": bool(user)})
    return user


async def get_user_by_email(session: AsyncSession, email: str) -> User | None:
    """Fetch a user by email.

    Args:
        session: Async database session for queries.
        email: Email address to match.

    Returns:
        User instance if found.
    """
    logger.info("get_user_by_email_start", extra={"email": email})
    result = await session.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    logger.info("get_user_by_email_done", extra={"email": email, "found": bool(user)})
    return user
