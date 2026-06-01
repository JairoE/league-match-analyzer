"""Tests for OpenAI LLM client."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.llm_client import OpenAIClient


class TestOpenAIClientComplete:
    async def test_passes_prompts_and_extracts_tokens(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Verify system/user prompts are passed to the API and token counts extracted."""
        mock_response = SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content='{"recommendations": []}')
                )
            ],
            usage=SimpleNamespace(prompt_tokens=150, completion_tokens=75),
            model="gpt-4o-mini-2024-07-18",
        )

        mock_create = AsyncMock(return_value=mock_response)
        mock_completions = MagicMock()
        mock_completions.create = mock_create

        mock_chat = MagicMock()
        mock_chat.completions = mock_completions

        client = OpenAIClient(api_key="test-key", model="gpt-4o-mini")
        # Patch the internal client's chat attribute
        monkeypatch.setattr(client._client, "chat", mock_chat)

        result = await client.complete("system prompt", "user prompt")

        # Verify prompts were passed
        call_kwargs = mock_create.call_args
        messages = call_kwargs.kwargs["messages"]
        assert messages[0] == {"role": "system", "content": "system prompt"}
        assert messages[1] == {"role": "user", "content": "user prompt"}

        # Verify response mapping
        assert result.content == '{"recommendations": []}'
        assert result.model_name == "gpt-4o-mini-2024-07-18"
        assert result.token_count_input == 150
        assert result.token_count_output == 75

    async def test_handles_none_usage(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Token counts should be 0 when usage is None."""
        mock_response = SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content='{}')
                )
            ],
            usage=None,
            model="gpt-4o-mini",
        )

        mock_create = AsyncMock(return_value=mock_response)
        mock_completions = MagicMock()
        mock_completions.create = mock_create
        mock_chat = MagicMock()
        mock_chat.completions = mock_completions

        client = OpenAIClient(api_key="test-key")
        monkeypatch.setattr(client._client, "chat", mock_chat)

        result = await client.complete("sys", "usr")
        assert result.token_count_input == 0
        assert result.token_count_output == 0

    async def test_handles_empty_content(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Empty content from model should be returned as empty string."""
        mock_response = SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content=None)
                )
            ],
            usage=SimpleNamespace(prompt_tokens=10, completion_tokens=0),
            model="gpt-4o-mini",
        )

        mock_create = AsyncMock(return_value=mock_response)
        mock_completions = MagicMock()
        mock_completions.create = mock_create
        mock_chat = MagicMock()
        mock_chat.completions = mock_completions

        client = OpenAIClient(api_key="test-key")
        monkeypatch.setattr(client._client, "chat", mock_chat)

        result = await client.complete("sys", "usr")
        assert result.content == ""

    async def test_json_mode_enabled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Verify response_format is set to json_object."""
        mock_response = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content='{}'))],
            usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5),
            model="gpt-4o-mini",
        )

        mock_create = AsyncMock(return_value=mock_response)
        mock_completions = MagicMock()
        mock_completions.create = mock_create
        mock_chat = MagicMock()
        mock_chat.completions = mock_completions

        client = OpenAIClient(api_key="test-key")
        monkeypatch.setattr(client._client, "chat", mock_chat)

        await client.complete("sys", "usr")

        call_kwargs = mock_create.call_args.kwargs
        assert call_kwargs["response_format"] == {"type": "json_object"}


class TestOpenAIClientEmbed:
    async def test_returns_float_list(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """embed() should return the embedding vector from the API response."""
        fake_vector = [0.1, 0.2, 0.3]
        mock_response = SimpleNamespace(
            data=[SimpleNamespace(embedding=fake_vector)]
        )

        mock_create = AsyncMock(return_value=mock_response)
        mock_embeddings = MagicMock()
        mock_embeddings.create = mock_create

        client = OpenAIClient(api_key="test-key")
        monkeypatch.setattr(client._client, "embeddings", mock_embeddings)

        result = await client.embed("Yasuo GOLD | gaps: Kraken Slayer gap=+0.0200")
        assert result == fake_vector

    async def test_passes_model_to_api(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """embed() should pass the specified model identifier to the API."""
        mock_response = SimpleNamespace(
            data=[SimpleNamespace(embedding=[0.0] * 5)]
        )

        mock_create = AsyncMock(return_value=mock_response)
        mock_embeddings = MagicMock()
        mock_embeddings.create = mock_create

        client = OpenAIClient(api_key="test-key")
        monkeypatch.setattr(client._client, "embeddings", mock_embeddings)

        await client.embed("some text", model="text-embedding-3-small")

        call_kwargs = mock_create.call_args.kwargs
        assert call_kwargs["model"] == "text-embedding-3-small"
        assert call_kwargs["input"] == "some text"

    async def test_default_model_is_text_embedding_3_small(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Default embedding model should be text-embedding-3-small."""
        mock_response = SimpleNamespace(
            data=[SimpleNamespace(embedding=[0.0])]
        )

        mock_create = AsyncMock(return_value=mock_response)
        mock_embeddings = MagicMock()
        mock_embeddings.create = mock_create

        client = OpenAIClient(api_key="test-key")
        monkeypatch.setattr(client._client, "embeddings", mock_embeddings)

        await client.embed("test")

        call_kwargs = mock_create.call_args.kwargs
        assert call_kwargs["model"] == "text-embedding-3-small"
