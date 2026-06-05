from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import uuid4

from sqlalchemy import or_
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.logging import get_logger
from app.models.match import Match
from app.models.riot_account import RiotAccount
from app.models.riot_account_match import RiotAccountMatch
from app.models.user import User
from app.models.user_riot_account import UserRiotAccount
from app.services.riot_id_parser import parse_riot_id

logger = get_logger("league_api.services.demo_seed")

# Fixture directory shipped with the repo (same data the test suite uses).
_FIXTURE_DIR = (
    Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "riot"
)

# Stable PUUID so the demo account is deterministic across restarts.
_DEMO_PUUID = "DEMO-PUUID-imaqtpie-00000000-0000-0000-0000-000000000000"


def _load_fixture(filename: str) -> Any:
    """Read a JSON fixture file from the test-fixtures directory.

    Args:
        filename: Basename of the fixture inside ``tests/fixtures/riot/``.

    Returns:
        Parsed JSON value.
    """
    path = _FIXTURE_DIR / filename
    return json.loads(path.read_text(encoding="utf-8"))


def _build_demo_match_payload(
    base_payload: dict[str, Any],
    game_id: str,
    demo_riot_id: str,
) -> dict[str, Any]:
    """Clone a real match payload and stamp it with the demo identity.

    Replaces participant 0's identifiers with the demo summoner so the
    frontend highlights the correct row.  Everything else (champions,
    items, stats) is left untouched — it's real data, just re-labelled.

    Args:
        base_payload: Original Riot match JSON.
        game_id: Riot-style game ID to inject (e.g. ``NA1_DEMO_001``).
        demo_riot_id: Canonical Riot ID for the demo account.

    Returns:
        A *new* dict (original is not mutated).
    """
    import copy

    payload = copy.deepcopy(base_payload)
    parsed = parse_riot_id(demo_riot_id)

    # Stamp metadata
    metadata = payload.setdefault("metadata", {})
    metadata["matchId"] = game_id
    if metadata.get("participants"):
        metadata["participants"][0] = _DEMO_PUUID

    # Stamp first participant with demo identity
    participants = payload.get("info", {}).get("participants", [])
    if participants:
        p = participants[0]
        p["puuid"] = _DEMO_PUUID
        p["riotIdGameName"] = parsed.game_name
        p["riotIdTagline"] = parsed.tag_line
        p["summonerName"] = parsed.game_name

    return payload


async def seed_demo_data(session: AsyncSession) -> None:
    """Insert demo user, riot account, and matches when DEMO_MODE is enabled.

    Safe to call on every startup — uses INSERT … ON CONFLICT DO NOTHING
    so repeated runs are no-ops once the data exists.

    Args:
        session: Async database session.
    """
    settings = get_settings()
    if not settings.demo_mode:
        return

    email = settings.demo_email
    riot_id = settings.demo_riot_id

    logger.info("demo_seed_start", extra={"email": email, "riot_id": riot_id})

    # --- 1. Upsert User ---
    user_id = uuid4()
    await session.execute(
        pg_insert(User)
        .values(id=user_id, email=email)
        .on_conflict_do_nothing(index_elements=["email"])
    )
    await session.flush()
    from sqlmodel import select

    row = await session.execute(select(User).where(User.email == email))
    user = row.scalar_one()
    logger.info("demo_seed_user", extra={"user_id": str(user.id)})

    # --- 2. Upsert RiotAccount ---
    parsed = parse_riot_id(riot_id)
    ra_id = uuid4()
    await session.execute(
        pg_insert(RiotAccount)
        .values(
            id=ra_id,
            riot_id=parsed.canonical,
            puuid=_DEMO_PUUID,
            summoner_name=parsed.game_name,
            profile_icon_id=29,
            summoner_level=500,
        )
        .on_conflict_do_nothing(index_elements=["riot_id"])
    )
    await session.flush()
    row = await session.execute(
        select(RiotAccount).where(
            or_(
                RiotAccount.riot_id == parsed.canonical,
                RiotAccount.puuid == _DEMO_PUUID,
            )
        )
    )
    riot_account = row.scalar_one()
    logger.info("demo_seed_riot_account", extra={"riot_account_id": str(riot_account.id)})

    # --- 3. Link User ↔ RiotAccount ---
    await session.execute(
        pg_insert(UserRiotAccount)
        .values(id=uuid4(), user_id=user.id, riot_account_id=riot_account.id)
        .on_conflict_do_nothing(constraint="uq_user_riot_account")
    )

    # --- 4. Seed matches from the fixture file ---
    base_payload = _load_fixture("match_detail.na1_5506397559.json")
    match_ids_fixture: list[str] = _load_fixture(
        "match_ids."
        "j_02mjdd6hthpvyrrnmo-o4gznoou7xil1lqkqklrsvphegg7zgqmp-"
        "oe3ccqpdw62s0_0ckkmhdgw.json"
    )

    # Generate one demo match per fixture ID (re-label each with demo identity).
    demo_game_ids: list[str] = []
    for idx, original_id in enumerate(match_ids_fixture):
        demo_gid = f"NA1_DEMO_{idx + 1:03d}"
        demo_game_ids.append(demo_gid)

        payload = _build_demo_match_payload(base_payload, demo_gid, riot_id)
        # Offset timestamps so matches sort in reverse-chronological order.
        base_ts: int = base_payload.get("info", {}).get("gameStartTimestamp", 0)
        offset_ts = base_ts - (idx * 3600_000)  # space 1 hour apart
        if payload.get("info"):
            payload["info"]["gameStartTimestamp"] = offset_ts

        await session.execute(
            pg_insert(Match)
            .values(
                id=uuid4(),
                game_id=demo_gid,
                game_start_timestamp=offset_ts,
                game_info=payload,
            )
            .on_conflict_do_nothing(index_elements=["game_id"])
        )

    await session.flush()

    # Fetch match UUIDs for linking
    from sqlmodel import select as sm_select

    result = await session.execute(
        sm_select(Match.id, Match.game_id).where(Match.game_id.in_(demo_game_ids))
    )
    match_map = {r.game_id: r.id for r in result.fetchall()}

    link_rows = [
        {"id": uuid4(), "riot_account_id": riot_account.id, "match_id": mid}
        for mid in match_map.values()
    ]
    if link_rows:
        await session.execute(
            pg_insert(RiotAccountMatch)
            .values(link_rows)
            .on_conflict_do_nothing(constraint="uq_riot_account_match")
        )

    await session.commit()
    logger.info(
        "demo_seed_done",
        extra={
            "user_id": str(user.id),
            "riot_account_id": str(riot_account.id),
            "matches_seeded": len(demo_game_ids),
        },
    )
