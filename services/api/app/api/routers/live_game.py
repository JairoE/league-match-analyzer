"""SSE endpoint for live game status polling."""

from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from app.core.logging import get_logger
from app.services.live_game import get_live_game
from app.services.riot_api_client import RiotRequestError

router = APIRouter(prefix="/live-game", tags=["live-game"])
logger = get_logger("league_api.live_game")

POLL_INTERVAL_SECONDS = 30
MAX_CONSECUTIVE_ERRORS = 3


@router.get("/{puuid}/stream")
async def live_game_stream(puuid: str, request: Request) -> StreamingResponse:
    """Stream live game status for a summoner via Server-Sent Events.

    Polls the Riot Spectator v5 API every 30 seconds and pushes events
    to the connected client. Stops after 3 consecutive errors.

    Events:
        live_game — summoner is in an active game (data contains game payload).
        not_in_game — summoner is not currently in a game.
        error — an error occurred while checking game status.

    Args:
        puuid: Riot PUUID of the summoner.
        request: FastAPI request (used for disconnect detection).

    Returns:
        StreamingResponse with text/event-stream media type.
    """
    logger.info("live_game_stream_start", extra={"puuid": puuid})

    async def event_generator():  # type: ignore[return]
        consecutive_errors = 0
        while True:
            if await request.is_disconnected():
                logger.info("live_game_stream_disconnected", extra={"puuid": puuid})
                break

            try:
                payload = await get_live_game(puuid)
                consecutive_errors = 0
            except RiotRequestError as exc:
                consecutive_errors += 1
                logger.warning(
                    "live_game_stream_error",
                    extra={
                        "puuid": puuid,
                        "status": exc.status,
                        "detail": exc.message,
                        "consecutive_errors": consecutive_errors,
                    },
                )
                yield f"event: error\ndata: {json.dumps({'status': exc.status, 'detail': exc.message})}\n\n"
                if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                    logger.warning(
                        "live_game_stream_max_errors",
                        extra={"puuid": puuid},
                    )
                    break
                await asyncio.sleep(POLL_INTERVAL_SECONDS)
                continue

            if payload is not None:
                yield f"event: live_game\ndata: {json.dumps(payload)}\n\n"
            else:
                yield "event: not_in_game\ndata: {}\n\n"

            await asyncio.sleep(POLL_INTERVAL_SECONDS)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
