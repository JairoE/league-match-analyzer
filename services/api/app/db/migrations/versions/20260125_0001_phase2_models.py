"""Create core Phase 2 models.

Revision ID: 20260125_0001
Revises:
Create Date: 2026-01-25 00:01:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "20260125_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Apply the Phase 2 schema changes."""
    op.create_table(
        "user",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("summoner_name", sa.String(), nullable=False),
        sa.Column("riot_id", sa.String(), nullable=False),
        sa.Column("puuid", sa.String(), nullable=False),
        sa.Column("profile_icon_id", sa.Integer(), nullable=True),
        sa.Column("summoner_level", sa.Integer(), nullable=True),
        sa.Column("email", sa.String(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_user_riot_id", "user", ["riot_id"], unique=True)
    op.create_index("ix_user_puuid", "user", ["puuid"], unique=True)

    op.create_table(
        "match",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("game_id", sa.String(), nullable=False),
        sa.Column("game_info", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_match_game_id", "match", ["game_id"], unique=True)

    op.create_table(
        "champion",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("champ_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("nickname", sa.String(), nullable=False),
        sa.Column("image_url", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_champion_champ_id", "champion", ["champ_id"], unique=True)

    op.create_table(
        "user_match",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("match_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(["match_id"], ["match.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "match_id", name="uq_user_match_pair"),
    )
    op.create_index("ix_user_match_user_id", "user_match", ["user_id"], unique=False)
    op.create_index("ix_user_match_match_id", "user_match", ["match_id"], unique=False)


def downgrade() -> None:
    """Revert the Phase 2 schema changes."""
    op.drop_index("ix_user_match_match_id", table_name="user_match")
    op.drop_index("ix_user_match_user_id", table_name="user_match")
    op.drop_table("user_match")
    op.drop_index("ix_champion_champ_id", table_name="champion")
    op.drop_table("champion")
    op.drop_index("ix_match_game_id", table_name="match")
    op.drop_table("match")
    op.drop_index("ix_user_puuid", table_name="user")
    op.drop_index("ix_user_riot_id", table_name="user")
    op.drop_table("user")
