"""Tests for the coach chat SSE router."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.api.routers import chat
from app.schemas.chat import ChatMessage, ChatRequest
from app.services.chat.loop import ChatEvent

# ── Fakes ─────────────────────────────────────────────────────────────


class _FakeSessionFactory:
    def __call__(self) -> _FakeSessionFactory:
        return self

    async def __aenter__(self) -> SimpleNamespace:
        return SimpleNamespace()

    async def __aexit__(self, *args: object) -> bool:
        return False


def _account() -> SimpleNamespace:
    return SimpleNamespace(id=uuid4(), riot_id="TestUser#NA1", rank_tier="GOLD")


def _request(*contents: tuple[str, str]) -> ChatRequest:
    return ChatRequest(
        messages=[ChatMessage(role=r, content=c) for r, c in contents]  # type: ignore[arg-type]
    )


def _patch_common(
    monkeypatch: pytest.MonkeyPatch,
    account: SimpleNamespace | None,
    events: list[ChatEvent] | None = None,
    raise_after: int | None = None,
) -> None:
    async def _resolve(session: object, identifier: str) -> SimpleNamespace | None:
        return account

    async def _fake_turn(*args: object, **kwargs: object):
        for index, event in enumerate(events or []):
            if raise_after is not None and index >= raise_after:
                raise RuntimeError("boom")
            yield event
        if raise_after is not None and raise_after >= len(events or []):
            raise RuntimeError("boom")

    monkeypatch.setattr(chat, "resolve_riot_account_identifier", _resolve)
    monkeypatch.setattr(chat, "run_chat_turn", _fake_turn)
    monkeypatch.setattr(chat, "async_session_factory", _FakeSessionFactory())
    monkeypatch.setattr(
        chat,
        "get_settings",
        lambda: SimpleNamespace(openai_api_key="test-key", llm_model_name="gpt-4o-mini"),
    )


async def _collect_body(response: Any) -> str:
    chunks = []
    async for chunk in response.body_iterator:
        chunks.append(chunk if isinstance(chunk, str) else chunk.decode())
    return "".join(chunks)


# ── Tests ─────────────────────────────────────────────────────────────


async def test_chat_stream_emits_sse_frames(monkeypatch: pytest.MonkeyPatch) -> None:
    events = [
        ChatEvent("tool_call", {"name": "get_player_profile", "label": "Looking…"}),
        ChatEvent("tool_result", {"name": "get_player_profile", "ok": True}),
        ChatEvent("token", {"text": "Hi"}),
        ChatEvent("done", {"finish_reason": "stop", "rounds": 1}),
    ]
    _patch_common(monkeypatch, _account(), events=events)

    response = await chat.chat_stream(
        riot_account_id="TestUser#NA1",
        payload=_request(("user", "How am I doing?")),
        session=SimpleNamespace(),  # type: ignore[arg-type]
    )

    assert response.media_type == "text/event-stream"
    assert response.headers["x-accel-buffering"] == "no"
    body = await _collect_body(response)
    assert 'event: tool_call\ndata: {"name": "get_player_profile"' in body
    assert 'event: token\ndata: {"text": "Hi"}' in body
    assert body.rstrip().endswith('event: done\ndata: {"finish_reason": "stop", "rounds": 1}')


async def test_chat_stream_unknown_account_404(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_common(monkeypatch, None)

    with pytest.raises(HTTPException) as exc_info:
        await chat.chat_stream(
            riot_account_id="missing#NA1",
            payload=_request(("user", "hello")),
            session=SimpleNamespace(),  # type: ignore[arg-type]
        )

    assert exc_info.value.status_code == 404


async def test_chat_stream_last_message_must_be_user(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_common(monkeypatch, _account())

    with pytest.raises(HTTPException) as exc_info:
        await chat.chat_stream(
            riot_account_id="TestUser#NA1",
            payload=_request(("user", "hi"), ("assistant", "hello!")),
            session=SimpleNamespace(),  # type: ignore[arg-type]
        )

    assert exc_info.value.status_code == 422
    assert exc_info.value.detail == "last_message_must_be_user"


async def test_chat_stream_no_api_key_503(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_common(monkeypatch, _account())
    monkeypatch.setattr(
        chat,
        "get_settings",
        lambda: SimpleNamespace(openai_api_key="", llm_model_name="gpt-4o-mini"),
    )

    with pytest.raises(HTTPException) as exc_info:
        await chat.chat_stream(
            riot_account_id="TestUser#NA1",
            payload=_request(("user", "hi")),
            session=SimpleNamespace(),  # type: ignore[arg-type]
        )

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == "chat_unavailable"


def test_chat_request_rejects_oversized_champion_focus() -> None:
    with pytest.raises(ValidationError):
        ChatRequest(
            messages=[ChatMessage(role="user", content="hi")],
            champion_focus="x" * 65,
        )


async def test_chat_stream_busy_returns_429_and_recovers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events = [ChatEvent("done", {"finish_reason": "stop", "rounds": 0})]
    _patch_common(monkeypatch, _account(), events=events)
    monkeypatch.setattr(chat, "_chat_semaphore", asyncio.Semaphore(1))

    first = await chat.chat_stream(
        riot_account_id="TestUser#NA1",
        payload=_request(("user", "hi")),
        session=SimpleNamespace(),  # type: ignore[arg-type]
    )

    # Slot is held until the first stream is consumed
    with pytest.raises(HTTPException) as exc_info:
        await chat.chat_stream(
            riot_account_id="TestUser#NA1",
            payload=_request(("user", "hi")),
            session=SimpleNamespace(),  # type: ignore[arg-type]
        )
    assert exc_info.value.status_code == 429
    assert exc_info.value.detail == "chat_busy"

    # Draining the first stream releases the slot
    await _collect_body(first)
    second = await chat.chat_stream(
        riot_account_id="TestUser#NA1",
        payload=_request(("user", "hi")),
        session=SimpleNamespace(),  # type: ignore[arg-type]
    )
    body = await _collect_body(second)
    assert "event: done" in body


async def test_chat_stream_generator_failure_emits_error_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events = [ChatEvent("token", {"text": "partial"})]
    _patch_common(monkeypatch, _account(), events=events, raise_after=1)

    response = await chat.chat_stream(
        riot_account_id="TestUser#NA1",
        payload=_request(("user", "hi")),
        session=SimpleNamespace(),  # type: ignore[arg-type]
    )
    body = await _collect_body(response)

    assert 'event: token\ndata: {"text": "partial"}' in body
    assert body.rstrip().endswith('event: error\ndata: {"detail": "chat_failed"}')
