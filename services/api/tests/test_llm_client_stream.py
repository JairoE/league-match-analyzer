"""Tests for OpenAIClient.stream_chat and tool-call delta accumulation."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from app.services.llm_client import (
    ChatStreamChunk,
    OpenAIClient,
    accumulate_tool_call_delta,
)

# ── Fakes ─────────────────────────────────────────────────────────────


def _chunk(
    content: str | None = None,
    tool_calls: list[Any] | None = None,
    finish_reason: str | None = None,
) -> SimpleNamespace:
    delta = SimpleNamespace(content=content, tool_calls=tool_calls)
    choice = SimpleNamespace(delta=delta, finish_reason=finish_reason)
    return SimpleNamespace(choices=[choice])


def _tool_delta(
    index: int,
    call_id: str | None = None,
    name: str | None = None,
    arguments: str | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        index=index,
        id=call_id,
        function=SimpleNamespace(name=name, arguments=arguments),
    )


class _FakeStream:
    def __init__(self, chunks: list[SimpleNamespace]) -> None:
        self._chunks = chunks

    def __aiter__(self) -> _FakeStream:
        self._iter = iter(self._chunks)
        return self

    async def __anext__(self) -> SimpleNamespace:
        try:
            return next(self._iter)
        except StopIteration as exc:
            raise StopAsyncIteration from exc


def _client_with_stream(chunks: list[SimpleNamespace]) -> tuple[OpenAIClient, dict]:
    client = OpenAIClient(api_key="test-key")
    captured: dict[str, Any] = {}

    async def _create(**kwargs: Any) -> _FakeStream:
        captured.update(kwargs)
        return _FakeStream(chunks)

    client._client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=_create))
    )
    return client, captured


async def _collect(client: OpenAIClient, **kwargs: Any) -> list[ChatStreamChunk]:
    return [
        chunk
        async for chunk in client.stream_chat(
            messages=[{"role": "user", "content": "hi"}], **kwargs
        )
    ]


# ── accumulate_tool_call_delta ────────────────────────────────────────


def test_accumulate_merges_chunked_arguments() -> None:
    state: dict[int, dict[str, Any]] = {}
    accumulate_tool_call_delta(state, _tool_delta(0, "call_1", "get_stats", '{"champ'))
    accumulate_tool_call_delta(state, _tool_delta(0, None, None, 'ion": "Jhin"}'))

    assert state == {
        0: {"id": "call_1", "name": "get_stats", "arguments": '{"champion": "Jhin"}'}
    }


def test_accumulate_tracks_parallel_calls_by_index() -> None:
    state: dict[int, dict[str, Any]] = {}
    accumulate_tool_call_delta(state, _tool_delta(0, "call_a", "tool_a", "{}"))
    accumulate_tool_call_delta(state, _tool_delta(1, "call_b", "tool_b", '{"x'))
    accumulate_tool_call_delta(state, _tool_delta(1, None, None, '": 1}'))

    assert state[0]["name"] == "tool_a"
    assert state[1] == {"id": "call_b", "name": "tool_b", "arguments": '{"x": 1}'}


def test_accumulate_handles_missing_function() -> None:
    state: dict[int, dict[str, Any]] = {}
    accumulate_tool_call_delta(
        state, SimpleNamespace(index=0, id="call_1", function=None)
    )

    assert state[0]["id"] == "call_1"
    assert state[0]["arguments"] == ""


# ── stream_chat ───────────────────────────────────────────────────────


async def test_stream_chat_yields_tokens_then_finish() -> None:
    client, captured = _client_with_stream(
        [
            _chunk(content="Hel"),
            _chunk(content="lo"),
            _chunk(finish_reason="stop"),
        ]
    )

    chunks = await _collect(client)

    assert [c.kind for c in chunks] == ["token", "token", "finish"]
    assert "".join(c.text for c in chunks if c.kind == "token") == "Hello"
    assert chunks[-1].finish_reason == "stop"
    assert captured["stream"] is True
    assert "tools" not in captured


async def test_stream_chat_aggregates_tool_calls() -> None:
    client, captured = _client_with_stream(
        [
            _chunk(tool_calls=[_tool_delta(0, "call_1", "get_stats", '{"a"')]),
            _chunk(tool_calls=[_tool_delta(0, None, None, ": 1}")]),
            _chunk(finish_reason="tool_calls"),
        ]
    )
    tools = [{"type": "function", "function": {"name": "get_stats"}}]

    chunks = await _collect(client, tools=tools)

    assert [c.kind for c in chunks] == ["tool_calls", "finish"]
    assert chunks[0].tool_calls == [
        {"id": "call_1", "name": "get_stats", "arguments": '{"a": 1}'}
    ]
    assert chunks[-1].finish_reason == "tool_calls"
    assert captured["tools"] == tools


async def test_stream_chat_mixed_content_and_parallel_tools() -> None:
    client, _ = _client_with_stream(
        [
            _chunk(content="Checking"),
            _chunk(
                tool_calls=[
                    _tool_delta(0, "call_a", "tool_a", "{}"),
                    _tool_delta(1, "call_b", "tool_b", "{}"),
                ]
            ),
            _chunk(finish_reason="tool_calls"),
        ]
    )

    chunks = await _collect(client)

    assert [c.kind for c in chunks] == ["token", "tool_calls", "finish"]
    assert [c["name"] for c in chunks[1].tool_calls or []] == ["tool_a", "tool_b"]


async def test_stream_chat_passes_tool_choice() -> None:
    client, captured = _client_with_stream([_chunk(finish_reason="stop")])

    await _collect(client, tool_choice="none")

    assert captured["tool_choice"] == "none"
