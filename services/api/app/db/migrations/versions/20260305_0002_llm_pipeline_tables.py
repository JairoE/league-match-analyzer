"""LLM data pipeline tables: state vectors, actions, analysis.

Revision ID: 20260305_0002
Revises: 20260212_0001
Create Date: 2026-03-05

Tables:
  - match_state_vector (per-minute game state feature snapshots)
  - match_action (item purchases + objective kills with pre/post state refs)
  - llm_analysis (persisted LLM recommendations with metadata)
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260305_0002"
down_revision = "20260212_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- match_state_vector ---
    op.create_table(
        "match_state_vector",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("match_id", sa.Uuid(), nullable=False),
        sa.Column("game_id", sa.String(), nullable=False),
        sa.Column("minute", sa.SmallInteger(), nullable=False),
        sa.Column("timestamp_ms", sa.BigInteger(), nullable=False),
        sa.Column("features", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.ForeignKeyConstraint(
            ["match_id"], ["match.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("match_id", "minute", name="uq_match_state_vector_match_minute"),
    )
    op.create_index(
        "ix_match_state_vector_match_id",
        "match_state_vector",
        ["match_id"],
    )
    op.create_index(
        "ix_match_state_vector_game_id",
        "match_state_vector",
        ["game_id"],
    )

    # --- match_action ---
    op.create_table(
        "match_action",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("match_id", sa.Uuid(), nullable=False),
        sa.Column("game_id", sa.String(), nullable=False),
        sa.Column("action_type", sa.String(), nullable=False),
        sa.Column("timestamp_ms", sa.BigInteger(), nullable=False),
        sa.Column("participant_id", sa.SmallInteger(), nullable=False),
        sa.Column("team_id", sa.SmallInteger(), nullable=False),
        sa.Column("action_detail", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("pre_state_minute", sa.SmallInteger(), nullable=False),
        sa.Column("post_state_minute", sa.SmallInteger(), nullable=True),
        sa.Column("was_undone", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("delta_w", sa.Float(), nullable=True),
        sa.Column("pre_win_prob", sa.Float(), nullable=True),
        sa.Column("post_win_prob", sa.Float(), nullable=True),
        sa.ForeignKeyConstraint(
            ["match_id"], ["match.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_match_action_match_id",
        "match_action",
        ["match_id"],
    )
    op.create_index(
        "ix_match_action_game_id",
        "match_action",
        ["game_id"],
    )
    op.create_index(
        "ix_match_action_action_type",
        "match_action",
        ["action_type"],
    )

    # --- llm_analysis ---
    op.create_table(
        "llm_analysis",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("riot_account_id", sa.Uuid(), nullable=False),
        sa.Column("champion_name", sa.String(), nullable=False),
        sa.Column("rank_tier", sa.String(), nullable=True),
        sa.Column(
            "match_ids",
            postgresql.ARRAY(sa.String()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("schema_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("input_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("output_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("recommendations", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("model_name", sa.String(), nullable=True),
        sa.Column("token_count_input", sa.Integer(), nullable=True),
        sa.Column("token_count_output", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["riot_account_id"], ["riot_account.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_llm_analysis_riot_account_id",
        "llm_analysis",
        ["riot_account_id"],
    )
    op.create_index(
        "ix_llm_analysis_champion_name",
        "llm_analysis",
        ["champion_name"],
    )


def downgrade() -> None:
    op.drop_table("llm_analysis")
    op.drop_table("match_action")
    op.drop_table("match_state_vector")
