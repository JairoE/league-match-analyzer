"""Agentic chat loop — streams tokens while executing tool calls between rounds.

Each turn runs up to MAX_TOOL_ROUNDS rounds where the model may call tools;
the round after that forces a plain-text answer with tool_choice="none".
Tool failures become error results the model can read — they never crash
the stream.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any, Literal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.riot_account import RiotAccount
from app.schemas.chat import ChatMessage
from app.services.chat.prompts import build_chat_system_prompt
from app.services.chat.tools import CHAT_TOOLS, cap_tool_result, openai_tool_schemas
from app.services.llm_client import OpenAIClient

logger = get_logger("league_api.services.chat.loop")

MAX_TOOL_ROUNDS = 3
MAX_TOOL_CALLS_PER_ROUND = 2
MESSAGE_WINDOW = 12
CHAT_MAX_TOKENS = 700
CHAT_TEMPERATURE = 0.4


@dataclass
class ChatEvent:
    """One SSE-shaped event emitted by the chat loop."""

    event: Literal["token", "tool_call", "tool_result", "done", "error"]
    data: dict[str, Any]


async def _execute_tool_call(
    session: AsyncSession,
    riot_account: RiotAccount,
    call: dict[str, Any],
) -> tuple[dict[str, Any], bool]:
    """Run one aggregated tool call, converting every failure into a result.

    Args:
        session: Async database session.
        riot_account: Account the chat is about.
        call: Aggregated call {id, name, arguments}.

    Returns:
        (result payload, ok flag).
    """
    tool = CHAT_TOOLS.get(call.get("name", ""))
    if tool is None:
        return {"error": f"unknown tool '{call.get('name')}'"}, False
    try:
        args = tool.args_model.model_validate_json(call.get("arguments") or "{}")
        return await tool.executor(session, riot_account, args), True
    except Exception:
        logger.exception("chat_tool_failed", extra={"tool": call.get("name")})
        return {"error": "tool_failed"}, False


async def run_chat_turn(
    session: AsyncSession,
    riot_account: RiotAccount,
    messages: list[ChatMessage],
    *,
    client: OpenAIClient,
    champion_focus: str | None = None,
) -> AsyncIterator[ChatEvent]:
    """Run one chat turn: stream answer tokens, executing tools between rounds.

    Args:
        session: Async database session for tool executors.
        riot_account: Account the chat is about.
        messages: Client-held transcript (last message is the user's).
        client: LLM client (constructed by the router; injectable for tests).
        champion_focus: Optional champion hint for the system prompt.

    Yields:
        ChatEvent items: token / tool_call / tool_result, then done or error.
    """
    system_prompt = build_chat_system_prompt(riot_account, champion_focus)
    window = messages[-MESSAGE_WINDOW:]
    conversation: list[dict[str, Any]] = [
        {"role": "system", "content": system_prompt},
        *({"role": m.role, "content": m.content} for m in window),
    ]
    tools = openai_tool_schemas()

    tool_rounds = 0
    # MAX_TOOL_ROUNDS rounds with tools + one forced-text round.
    for round_index in range(MAX_TOOL_ROUNDS + 1):
        final_round = round_index >= MAX_TOOL_ROUNDS
        tool_calls: list[dict[str, Any]] | None = None
        finish_reason: str | None = None

        # tools must be sent even on the forced-text round — OpenAI rejects
        # tool_choice="none" when no tools are present in the request.
        stream = client.stream_chat(
            conversation,
            tools=tools,
            tool_choice="none" if final_round else None,
            max_tokens=CHAT_MAX_TOKENS,
            temperature=CHAT_TEMPERATURE,
        )
        async for chunk in stream:
            if chunk.kind == "token" and chunk.text:
                yield ChatEvent("token", {"text": chunk.text})
            elif chunk.kind == "tool_calls":
                tool_calls = chunk.tool_calls
            elif chunk.kind == "finish":
                finish_reason = chunk.finish_reason

        if not tool_calls:
            yield ChatEvent(
                "done",
                {"finish_reason": finish_reason or "stop", "rounds": tool_rounds},
            )
            return

        tool_rounds += 1
        conversation.append(
            {
                "role": "assistant",
                "tool_calls": [
                    {
                        "id": call.get("id") or f"call_{index}",
                        "type": "function",
                        "function": {
                            "name": call.get("name", ""),
                            "arguments": call.get("arguments") or "{}",
                        },
                    }
                    for index, call in enumerate(tool_calls)
                ],
            }
        )
        for index, call in enumerate(tool_calls):
            name = call.get("name", "")
            if index >= MAX_TOOL_CALLS_PER_ROUND:
                # Every tool_call id still needs a tool message.
                result: dict[str, Any] = {"error": "too_many_tool_calls"}
            else:
                tool = CHAT_TOOLS.get(name)
                yield ChatEvent(
                    "tool_call",
                    {"name": name, "label": tool.label if tool else name},
                )
                result, ok = await _execute_tool_call(session, riot_account, call)
                yield ChatEvent("tool_result", {"name": name, "ok": ok})
            conversation.append(
                {
                    "role": "tool",
                    "tool_call_id": call.get("id") or f"call_{index}",
                    "content": cap_tool_result(result),
                }
            )

    # Unreachable in practice: the final round cannot produce tool calls.
    yield ChatEvent("done", {"finish_reason": "max_rounds", "rounds": tool_rounds})
