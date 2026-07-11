"""Tests for the coach chat agentic loop."""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest

from app.schemas.chat import ChatMessage
from app.services.chat import loop as chat_loop
from app.services.chat.loop import ChatEvent, run_chat_turn
from app.services.llm_client import ChatStreamChunk

# ── Fakes ─────────────────────────────────────────────────────────────


class _ScriptedClient:
    """stream_chat returns the next scripted chunk list on each call."""

    def __init__(self, scripts: list[list[ChatStreamChunk]]) -> None:
        self._scripts = list(scripts)
        self.calls: list[dict[str, Any]] = []

    async def stream_chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | None = None,
        max_tokens: int = 700,
        temperature: float = 0.4,
    ):
        self.calls.append(
            {
                "messages": [dict(m) for m in messages],
                "tools": tools,
                "tool_choice": tool_choice,
            }
        )
        script = self._scripts.pop(0) if self._scripts else [
            ChatStreamChunk(kind="finish", finish_reason="stop")
        ]
        for chunk in script:
            yield chunk


def _account() -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        riot_id="TestUser#NA1",
        puuid="puuid-1",
        rank_tier="GOLD",
        summoner_level=100,
    )


def _tool_call_chunk(name: str, arguments: str = "{}", call_id: str = "call_1"):
    return ChatStreamChunk(
        kind="tool_calls",
        tool_calls=[{"id": call_id, "name": name, "arguments": arguments}],
    )


def _tokens(*texts: str) -> list[ChatStreamChunk]:
    return [
        *[ChatStreamChunk(kind="token", text=t) for t in texts],
        ChatStreamChunk(kind="finish", finish_reason="stop"),
    ]


async def _collect(
    client: _ScriptedClient,
    messages: list[ChatMessage] | None = None,
    monkeypatch: pytest.MonkeyPatch | None = None,
    profile_result: dict[str, Any] | None = None,
) -> list[ChatEvent]:
    if monkeypatch is not None:
        registry = dict(chat_loop.CHAT_TOOLS)

        async def _profile(session: object, account: object, args: object) -> dict:
            if isinstance(profile_result, Exception):
                raise profile_result
            return profile_result if profile_result is not None else {"rank_tier": "GOLD"}

        original = registry["get_player_profile"]
        registry["get_player_profile"] = SimpleNamespace(
            name=original.name,
            label=original.label,
            args_model=original.args_model,
            executor=_profile,
        )
        monkeypatch.setattr(chat_loop, "CHAT_TOOLS", registry)

    events = []
    async for event in run_chat_turn(
        session=SimpleNamespace(),  # type: ignore[arg-type]
        riot_account=_account(),  # type: ignore[arg-type]
        messages=messages or [ChatMessage(role="user", content="How am I doing?")],
        client=client,  # type: ignore[arg-type]
    ):
        events.append(event)
    return events


# ── Tests ─────────────────────────────────────────────────────────────


async def test_plain_answer_streams_tokens_then_done() -> None:
    client = _ScriptedClient([_tokens("You're ", "improving.")])

    events = await _collect(client)

    assert [e.event for e in events] == ["token", "token", "done"]
    assert events[-1].data == {"finish_reason": "stop", "rounds": 0}
    # System prompt first, then the user message
    first_call = client.calls[0]
    assert first_call["messages"][0]["role"] == "system"
    assert "AI coach" in first_call["messages"][0]["content"]
    assert first_call["tools"] is not None
    assert first_call["tool_choice"] is None


async def test_tool_round_then_answer_event_sequence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _ScriptedClient(
        [
            [
                _tool_call_chunk("get_player_profile"),
                ChatStreamChunk(kind="finish", finish_reason="tool_calls"),
            ],
            _tokens("Answer."),
        ]
    )

    events = await _collect(client, monkeypatch=monkeypatch)

    assert [e.event for e in events] == ["tool_call", "tool_result", "token", "done"]
    assert events[0].data["label"] == "Looking up the player profile…"
    assert events[1].data == {"name": "get_player_profile", "ok": True}
    assert events[-1].data["rounds"] == 1

    # Second LLM call sees the assistant tool_calls message + tool result
    second_messages = client.calls[1]["messages"]
    assert second_messages[-2]["role"] == "assistant"
    assert second_messages[-2]["tool_calls"][0]["function"]["name"] == "get_player_profile"
    assert second_messages[-1]["role"] == "tool"
    assert json.loads(second_messages[-1]["content"]) == {"rank_tier": "GOLD"}


async def test_max_rounds_forces_text_answer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tool_round = [
        _tool_call_chunk("get_player_profile"),
        ChatStreamChunk(kind="finish", finish_reason="tool_calls"),
    ]
    client = _ScriptedClient([tool_round, tool_round, tool_round, _tokens("Final.")])

    events = await _collect(client, monkeypatch=monkeypatch)

    assert events[-1].event == "done"
    assert events[-1].data["rounds"] == 3
    # 4th call is the forced-text round — tools must still be sent
    # (OpenAI rejects tool_choice="none" without tools).
    final_call = client.calls[3]
    assert final_call["tools"] is not None
    assert final_call["tool_choice"] == "none"


async def test_tool_exception_yields_not_ok_and_continues(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _ScriptedClient(
        [
            [
                _tool_call_chunk("get_player_profile"),
                ChatStreamChunk(kind="finish", finish_reason="tool_calls"),
            ],
            _tokens("Sorry, data lookup failed."),
        ]
    )

    events = await _collect(
        client, monkeypatch=monkeypatch, profile_result=RuntimeError("boom")
    )

    assert [e.event for e in events] == ["tool_call", "tool_result", "token", "done"]
    assert events[1].data["ok"] is False
    tool_message = client.calls[1]["messages"][-1]
    assert json.loads(tool_message["content"]) == {"error": "tool_failed"}


async def test_unknown_tool_yields_not_ok() -> None:
    client = _ScriptedClient(
        [
            [
                _tool_call_chunk("not_a_tool"),
                ChatStreamChunk(kind="finish", finish_reason="tool_calls"),
            ],
            _tokens("Hmm."),
        ]
    )

    events = await _collect(client)

    assert events[1].data == {"name": "not_a_tool", "ok": False}


async def test_excess_tool_calls_answered_but_not_executed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = [
        {"id": f"call_{i}", "name": "get_player_profile", "arguments": "{}"}
        for i in range(3)
    ]
    client = _ScriptedClient(
        [
            [
                ChatStreamChunk(kind="tool_calls", tool_calls=calls),
                ChatStreamChunk(kind="finish", finish_reason="tool_calls"),
            ],
            _tokens("Done."),
        ]
    )

    events = await _collect(client, monkeypatch=monkeypatch)

    # Only 2 executed (2 tool_call + 2 tool_result events)
    assert [e.event for e in events[:4]] == [
        "tool_call",
        "tool_result",
        "tool_call",
        "tool_result",
    ]
    # ...but all 3 call ids receive a tool message (OpenAI requirement)
    tool_messages = [
        m for m in client.calls[1]["messages"] if m["role"] == "tool"
    ]
    assert len(tool_messages) == 3
    assert json.loads(tool_messages[2]["content"]) == {"error": "too_many_tool_calls"}


async def test_message_window_trims_transcript() -> None:
    client = _ScriptedClient([_tokens("ok")])
    messages = [
        ChatMessage(role="user" if i % 2 == 0 else "assistant", content=f"m{i}")
        for i in range(20)
    ]

    await _collect(client, messages=messages)

    sent = client.calls[0]["messages"]
    # 1 system + last 12 transcript messages
    assert len(sent) == 13
    assert sent[1]["content"] == "m8"
    assert sent[-1]["content"] == "m19"
