"""SSE endpoint for the coach chat — POST transcript in, event stream out."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.session import async_session_factory, get_session
from app.models.riot_account import RiotAccount
from app.schemas.chat import ChatRequest
from app.services.chat.loop import run_chat_turn
from app.services.llm_client import OpenAIClient
from app.services.riot_accounts import resolve_riot_account_identifier

router = APIRouter(tags=["chat"])
logger = get_logger("league_api.chat")


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


async def _chat_event_stream(
    account: RiotAccount,
    payload: ChatRequest,
    client: OpenAIClient,
) -> AsyncIterator[str]:
    """Wrap the chat loop into SSE frames with a fail-soft error event.

    Opens its own DB session — the request-scoped session may be torn
    down before a StreamingResponse body finishes iterating.
    """
    try:
        async with async_session_factory() as session:
            async for event in run_chat_turn(
                session,
                account,
                payload.messages,
                client=client,
                champion_focus=payload.champion_focus,
            ):
                yield _sse(event.event, event.data)
    except asyncio.CancelledError:
        logger.info("chat_stream_cancelled", extra={"riot_account_id": str(account.id)})
        raise
    except Exception:
        logger.exception("chat_stream_failed", extra={"riot_account_id": str(account.id)})
        yield _sse("error", {"detail": "chat_failed"})


@router.post("/riot-accounts/{riot_account_id}/chat/stream")
async def chat_stream(
    riot_account_id: str,
    payload: ChatRequest,
    session: AsyncSession = Depends(get_session),
) -> StreamingResponse:
    """Stream a coach chat turn for an account via Server-Sent Events.

    Events:
        token — answer text delta.
        tool_call / tool_result — tool activity for the UI.
        done — turn completed.
        error — turn failed (stream still returns 200; body carries the error).

    Args:
        riot_account_id: Riot account UUID or Riot ID.
        payload: Full client-held transcript plus optional champion focus.
        session: Async database session (account resolution only).

    Returns:
        StreamingResponse with text/event-stream media type.
    """
    account = await resolve_riot_account_identifier(session, riot_account_id)
    if account is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Riot account not found",
        )
    if payload.messages[-1].role != "user":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="last_message_must_be_user",
        )
    settings = get_settings()
    if not settings.openai_api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="chat_unavailable",
        )

    client = OpenAIClient(
        api_key=settings.openai_api_key,
        model=settings.llm_model_name,
    )
    logger.info(
        "chat_stream_start",
        extra={
            "riot_account_id": str(account.id),
            "message_count": len(payload.messages),
        },
    )
    return StreamingResponse(
        _chat_event_stream(account, payload, client),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
