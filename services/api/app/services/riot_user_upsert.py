from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.core.logging import get_logger
from app.models.user import User

logger = get_logger("league_api.services.riot_user_upsert")


async def upsert_user_from_riot(
    session: AsyncSession,
    riot_id: str,
    puuid: str,
    summoner_info: dict[str, Any],
    email: str | None = None,
) -> User:
    """Upsert a user from Riot payloads.

    Retrieves: Existing user record by PUUID or Riot ID.
    Transforms: Normalizes summoner name and maps Riot fields into user columns.
    Why: Keeps user identity consistent across sync calls and request flows.

    Args:
        session: Async database session for queries.
        riot_id: Riot ID in gameName#tagLine format.
        puuid: Riot PUUID identifier.
        summoner_info: Riot summoner payload from the API.
        email: Optional email to store for auth flows.

    Returns:
        Stored user record after upsert.
    """
    logger.info(
        "riot_user_upsert_start",
        extra={"riot_id": riot_id, "has_email": bool(email), "has_summoner": bool(summoner_info)},
    )
    summoner_name = str(summoner_info.get("name") or riot_id.split("#", 1)[0])
    profile_icon_id = summoner_info.get("profileIconId")
    summoner_level = summoner_info.get("summonerLevel")

    result = await session.execute(select(User).where(User.puuid == puuid))
    user = result.scalar_one_or_none()
    if not user:
        result = await session.execute(select(User).where(User.riot_id == riot_id))
        user = result.scalar_one_or_none()

    created = False
    if not user:
        user = User(
            summoner_name=summoner_name,
            riot_id=riot_id,
            puuid=puuid,
            profile_icon_id=profile_icon_id,
            summoner_level=summoner_level,
            email=email,
        )
        session.add(user)
        created = True
    else:
        user.summoner_name = summoner_name
        user.riot_id = riot_id
        user.puuid = puuid
        user.profile_icon_id = profile_icon_id
        user.summoner_level = summoner_level
        if email is not None:
            user.email = email

    await session.commit()
    await session.refresh(user)
    logger.info(
        "riot_user_upsert_done",
        extra={"user_id": str(user.id), "user_created": created, "has_email": bool(user.email)},
    )
    return user
