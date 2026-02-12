from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.core.logging import get_logger
from app.models.riot_account import RiotAccount
from app.models.user import User
from app.models.user_riot_account import UserRiotAccount

logger = get_logger("league_api.services.riot_account_upsert")


async def upsert_riot_account(
    session: AsyncSession,
    riot_id: str,
    puuid: str,
    summoner_info: dict[str, Any],
) -> RiotAccount:
    """Upsert a riot account from Riot API payloads.

    Retrieves: Existing riot account by PUUID or Riot ID.
    Transforms: Normalizes summoner name and maps Riot fields.
    Why: Keeps Riot identity consistent across sync calls.

    Args:
        session: Async database session for queries.
        riot_id: Riot ID in gameName#tagLine format.
        puuid: Riot PUUID identifier.
        summoner_info: Riot summoner payload from the API.

    Returns:
        Stored riot account record after upsert.
    """
    logger.info(
        "riot_account_upsert_start",
        extra={"riot_id": riot_id, "has_summoner": bool(summoner_info)},
    )
    summoner_name = str(summoner_info.get("name") or riot_id.split("#", 1)[0])
    profile_icon_id = summoner_info.get("profileIconId")
    summoner_level = summoner_info.get("summonerLevel")

    result = await session.execute(select(RiotAccount).where(RiotAccount.puuid == puuid))
    account = result.scalar_one_or_none()
    if not account:
        result = await session.execute(select(RiotAccount).where(RiotAccount.riot_id == riot_id))
        account = result.scalar_one_or_none()

    created = False
    if not account:
        account = RiotAccount(
            summoner_name=summoner_name,
            riot_id=riot_id,
            puuid=puuid,
            profile_icon_id=profile_icon_id,
            summoner_level=summoner_level,
        )
        session.add(account)
        created = True
    else:
        account.summoner_name = summoner_name
        account.riot_id = riot_id
        account.puuid = puuid
        account.profile_icon_id = profile_icon_id
        account.summoner_level = summoner_level

    await session.flush()
    logger.info(
        "riot_account_upsert_done",
        extra={"riot_account_id": str(account.id), "was_created": created},
    )
    return account


async def find_or_create_riot_account(
    session: AsyncSession,
    riot_id: str,
    puuid: str,
    summoner_info: dict[str, Any] | None = None,
) -> RiotAccount:
    """Find an existing riot account or create a minimal one.

    Args:
        session: Async database session for queries.
        riot_id: Riot ID in gameName#tagLine format.
        puuid: Riot PUUID identifier.
        summoner_info: Optional summoner payload for richer data.

    Returns:
        Stored riot account record.
    """
    return await upsert_riot_account(session, riot_id, puuid, summoner_info or {})


async def ensure_user_riot_account_link(
    session: AsyncSession,
    user_id: UUID,
    riot_account_id: UUID,
) -> UserRiotAccount:
    """Ensure a user ↔ riot_account link exists.

    Args:
        session: Async database session for queries.
        user_id: UUID of the app user.
        riot_account_id: UUID of the riot account.

    Returns:
        The existing or newly created link record.
    """
    result = await session.execute(
        select(UserRiotAccount).where(
            UserRiotAccount.user_id == user_id,
            UserRiotAccount.riot_account_id == riot_account_id,
        )
    )
    link = result.scalar_one_or_none()
    if link:
        return link

    link = UserRiotAccount(user_id=user_id, riot_account_id=riot_account_id)
    session.add(link)
    await session.flush()
    logger.info(
        "user_riot_account_link_created",
        extra={"user_id": str(user_id), "riot_account_id": str(riot_account_id)},
    )
    return link


async def upsert_user_and_riot_account(
    session: AsyncSession,
    email: str,
    riot_id: str,
    puuid: str,
    summoner_info: dict[str, Any],
) -> tuple[User, RiotAccount]:
    """Upsert user + riot account + link for sign-up/sign-in flows.

    Creates or finds the app user by email, upserts the riot account,
    and ensures the link between them exists.

    Args:
        session: Async database session for queries.
        email: User email address.
        riot_id: Riot ID in gameName#tagLine format.
        puuid: Riot PUUID identifier.
        summoner_info: Riot summoner payload from the API.

    Returns:
        Tuple of (User, RiotAccount) after upsert.
    """
    # Find or create user by email
    result = await session.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if not user:
        user = User(email=email)
        session.add(user)
        await session.flush()
        logger.info("user_created", extra={"user_id": str(user.id), "email": email})

    # Upsert riot account
    riot_account = await upsert_riot_account(session, riot_id, puuid, summoner_info)

    # Ensure link
    await ensure_user_riot_account_link(session, user.id, riot_account.id)

    await session.commit()
    await session.refresh(user)
    await session.refresh(riot_account)

    logger.info(
        "upsert_user_and_riot_account_done",
        extra={
            "user_id": str(user.id),
            "riot_account_id": str(riot_account.id),
            "riot_id": riot_id,
        },
    )
    return user, riot_account
