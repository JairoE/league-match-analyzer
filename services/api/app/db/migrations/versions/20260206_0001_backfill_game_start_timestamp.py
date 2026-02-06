"""Backfill game_start_timestamp from game_info JSONB.

Revision ID: 20260206_0001
Revises: 20260205_0001
Create Date: 2026-02-06 00:01:00.000000
"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "20260206_0001"
down_revision = "20260205_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Extract game_start_timestamp from cached game_info JSONB for all existing rows."""
    op.execute("""
        UPDATE match
        SET game_start_timestamp = (game_info -> 'info' ->> 'gameStartTimestamp')::bigint
        WHERE game_info IS NOT NULL
          AND game_start_timestamp IS NULL
          AND game_info -> 'info' ->> 'gameStartTimestamp' IS NOT NULL
    """)


def downgrade() -> None:
    """Clear backfilled timestamps (DDL column retained by prior migration)."""
    op.execute("""
        UPDATE match
        SET game_start_timestamp = NULL
        WHERE game_start_timestamp IS NOT NULL
    """)
