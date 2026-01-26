from __future__ import annotations

from sqlmodel import Field, SQLModel


class ResetResult(SQLModel):
    """Response model for reset endpoints."""

    resource: str = Field(description="Resource name targeted by the reset call.")
    action: str = Field(description="Requested reset action such as clear or reseed.")
    status: str = Field(description="Current status for the reset request.")
    scheduled: bool = Field(description="Whether the reset work was scheduled in background.")
    message: str = Field(description="Human-readable description of the reset result.")
