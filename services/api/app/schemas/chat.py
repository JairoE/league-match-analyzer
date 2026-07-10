"""Pydantic schemas for the coach chat endpoint."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    """One transcript message from the stateless client."""

    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=4000)


class ChatRequest(BaseModel):
    """Request body for a chat turn — the client sends the full transcript."""

    messages: list[ChatMessage] = Field(min_length=1, max_length=20)
    champion_focus: str | None = None
