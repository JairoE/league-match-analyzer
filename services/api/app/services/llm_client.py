"""LLM client – OpenAI implementation."""

from __future__ import annotations

from dataclasses import dataclass

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
