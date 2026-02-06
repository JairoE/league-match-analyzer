"""Add game_start_timestamp to match table.

Revision ID: 20260205_0001
Revises: 20260125_0001
Create Date: 2026-02-05 00:01:00.000000
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20260205_0001"
down_revision = "20260125_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add game_start_timestamp column for indexed match ordering."""
    op.add_column(
        "match",
        sa.Column(
            "game_start_timestamp",
            sa.BigInteger(),
            nullable=True,
            comment="Game start timestamp in milliseconds from Riot API",
        ),
    )
    op.create_index(
        "ix_match_game_start_timestamp",
        "match",
        ["game_start_timestamp"],
        unique=False,
    )


def downgrade() -> None:
    """Remove game_start_timestamp column and index."""
    op.drop_index("ix_match_game_start_timestamp", table_name="match")
    op.drop_column("match", "game_start_timestamp")
