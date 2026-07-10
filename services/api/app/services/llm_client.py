"""LLM client – OpenAI implementation (completions, embeddings, chat streaming)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any, Literal

from openai import AsyncOpenAI

from app.core.logging import get_logger

logger = get_logger("league_api.services.llm_client")


@dataclass
class LLMResponse:
    """Structured response from an LLM provider.

    Attributes:
        content: Raw text content returned by the model.
        model_name: Model identifier used for the completion.
        token_count_input: Number of input (prompt) tokens.
        token_count_output: Number of output (completion) tokens.
    """

    content: str
    model_name: str
    token_count_input: int
    token_count_output: int


@dataclass
class ChatStreamChunk:
    """One unit of a streamed chat completion.

    Attributes:
        kind: "token" for content deltas, "tool_calls" for the aggregated
            tool calls of a round, "finish" for the terminal chunk.
        text: Content delta (token chunks only).
        tool_calls: Aggregated calls [{id, name, arguments}] (tool_calls only).
        finish_reason: OpenAI finish reason (finish chunks only).
    """

    kind: Literal["token", "tool_calls", "finish"]
    text: str = ""
    tool_calls: list[dict[str, Any]] | None = None
    finish_reason: str | None = None


def accumulate_tool_call_delta(state: dict[int, dict[str, Any]], delta: Any) -> None:
    """Merge one streamed tool-call delta into the per-index accumulation state.

    OpenAI streams tool calls in fragments: the id and function name arrive
    once per index, while the JSON arguments string arrives concatenated
    across many chunks.

    Args:
        state: Mutable mapping of tool-call index → {id, name, arguments}.
        delta: A single streamed tool-call delta object.
    """
    index = getattr(delta, "index", 0) or 0
    entry = state.setdefault(index, {"id": "", "name": "", "arguments": ""})
    if getattr(delta, "id", None):
        entry["id"] = delta.id
    function = getattr(delta, "function", None)
    if function is not None:
        if getattr(function, "name", None):
            entry["name"] = function.name
        if getattr(function, "arguments", None):
            entry["arguments"] += function.arguments


class OpenAIClient:
    """OpenAI chat-completions client.

    Uses JSON mode to force structured output from the model.

    Args:
        api_key: OpenAI API key.
        model: Model identifier (default "gpt-4o-mini").
    """

    def __init__(self, api_key: str, model: str = "gpt-4o-mini") -> None:
        self._client = AsyncOpenAI(api_key=api_key)
        self._model = model

    async def complete(self, system_prompt: str, user_prompt: str) -> LLMResponse:
        """Call the OpenAI chat completions endpoint.

        Args:
            system_prompt: System message content.
            user_prompt: User message content.

        Returns:
            LLMResponse with parsed content and token counts.
        """
        logger.info(
            "llm_client_request_start",
            extra={"model": self._model},
        )

        response = await self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
            temperature=0.3,
            max_tokens=1024,
        )

        choice = response.choices[0]
        content = choice.message.content or ""
        usage = response.usage

        token_input = usage.prompt_tokens if usage else 0
        token_output = usage.completion_tokens if usage else 0

        logger.info(
            "llm_client_request_done",
            extra={
                "model": self._model,
                "token_input": token_input,
                "token_output": token_output,
            },
        )

        return LLMResponse(
            content=content,
            model_name=response.model,
            token_count_input=token_input,
            token_count_output=token_output,
        )

    async def stream_chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | None = None,
        max_tokens: int = 700,
        temperature: float = 0.4,
    ) -> AsyncIterator[ChatStreamChunk]:
        """Stream a chat completion, surfacing tokens and aggregated tool calls.

        Content deltas are yielded immediately as "token" chunks. Tool-call
        deltas are accumulated by index and yielded as a single "tool_calls"
        chunk once the stream ends, followed by a terminal "finish" chunk.

        Args:
            messages: OpenAI-format message dicts (system/user/assistant/tool).
            tools: Optional OpenAI function specs to expose to the model.
            tool_choice: Optional tool-choice override (e.g. "none").
            max_tokens: Completion token budget.
            temperature: Sampling temperature.

        Yields:
            ChatStreamChunk items in stream order.
        """
        logger.info(
            "llm_client_stream_start",
            extra={"model": self._model, "tool_count": len(tools or [])},
        )
        kwargs: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }
        if tools:
            kwargs["tools"] = tools
        if tool_choice is not None:
            kwargs["tool_choice"] = tool_choice

        stream = await self._client.chat.completions.create(**kwargs)

        pending_tool_calls: dict[int, dict[str, Any]] = {}
        finish_reason: str | None = None
        async for chunk in stream:
            if not chunk.choices:
                continue
            choice = chunk.choices[0]
            delta = choice.delta
            if delta is not None and delta.content:
                yield ChatStreamChunk(kind="token", text=delta.content)
            if delta is not None and delta.tool_calls:
                for tool_call in delta.tool_calls:
                    accumulate_tool_call_delta(pending_tool_calls, tool_call)
            if choice.finish_reason:
                finish_reason = choice.finish_reason

        if pending_tool_calls:
            calls = [pending_tool_calls[i] for i in sorted(pending_tool_calls)]
            yield ChatStreamChunk(kind="tool_calls", tool_calls=calls)

        logger.info(
            "llm_client_stream_done",
            extra={"model": self._model, "finish_reason": finish_reason},
        )
        yield ChatStreamChunk(kind="finish", finish_reason=finish_reason)

    async def embed(self, text: str, model: str = "text-embedding-3-small") -> list[float]:
        """Generate a dense embedding vector for the given text.

        Args:
            text: Input text to embed.
            model: OpenAI embedding model identifier.

        Returns:
            List of floats representing the embedding vector.
        """
        logger.info("llm_client_embed_start", extra={"model": model})
        response = await self._client.embeddings.create(model=model, input=text)
        embedding = response.data[0].embedding
        logger.info(
            "llm_client_embed_done",
            extra={"model": model, "dims": len(embedding)},
        )
        return embedding
