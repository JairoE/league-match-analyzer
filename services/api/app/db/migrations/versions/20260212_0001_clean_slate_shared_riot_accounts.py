"""Clean slate: shared riot account model.

Revision ID: 20260212_0001
Revises:
Create Date: 2026-02-12

Tables:
  - user (app identity: id, email)
  - riot_account (riot identity: riot_id, puuid, summoner data)
  - user_riot_account (access mapping: user ↔ riot_account)
  - match (game records with JSONB payload)
  - riot_account_match (riot_account ↔ match link)
  - champion (static champion data)
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260212_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- user ---
    op.create_table(
        "user",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_user_id"), "user", ["id"])
    op.create_index(op.f("ix_user_email"), "user", ["email"], unique=True)

    # --- riot_account ---
    op.create_table(
        "riot_account",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("riot_id", sa.String(), nullable=False),
        sa.Column("puuid", sa.String(), nullable=False),
        sa.Column("summoner_name", sa.String(), nullable=True),
        sa.Column("profile_icon_id", sa.Integer(), nullable=True),
        sa.Column("summoner_level", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_riot_account_id"), "riot_account", ["id"])
    op.create_index(op.f("ix_riot_account_riot_id"), "riot_account", ["riot_id"], unique=True)
    op.create_index(op.f("ix_riot_account_puuid"), "riot_account", ["puuid"], unique=True)

    # --- user_riot_account ---
    op.create_table(
        "user_riot_account",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("riot_account_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"]),
        sa.ForeignKeyConstraint(["riot_account_id"], ["riot_account.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "riot_account_id", name="uq_user_riot_account"),
    )
    op.create_index(op.f("ix_user_riot_account_user_id"), "user_riot_account", ["user_id"])
    op.create_index(op.f("ix_user_riot_account_riot_account_id"), "user_riot_account", ["riot_account_id"])

    # --- match ---
    op.create_table(
        "match",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("game_id", sa.String(), nullable=False),
        sa.Column("game_start_timestamp", sa.BigInteger(), nullable=True),
        sa.Column("game_info", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_match_id"), "match", ["id"])
    op.create_index(op.f("ix_match_game_id"), "match", ["game_id"], unique=True)
    op.create_index(op.f("ix_match_game_start_timestamp"), "match", ["game_start_timestamp"])

    # --- riot_account_match ---
    op.create_table(
        "riot_account_match",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("riot_account_id", sa.Uuid(), nullable=False),
        sa.Column("match_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["riot_account_id"], ["riot_account.id"]),
        sa.ForeignKeyConstraint(["match_id"], ["match.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("riot_account_id", "match_id", name="uq_riot_account_match"),
    )
    op.create_index(op.f("ix_riot_account_match_riot_account_id"), "riot_account_match", ["riot_account_id"])
    op.create_index(op.f("ix_riot_account_match_match_id"), "riot_account_match", ["match_id"])

    # --- champion ---
    op.create_table(
        "champion",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("champ_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("nickname", sa.String(), nullable=False),
        sa.Column("image_url", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_champion_id"), "champion", ["id"])
    op.create_index(op.f("ix_champion_champ_id"), "champion", ["champ_id"], unique=True)


def downgrade() -> None:
    op.drop_table("riot_account_match")
    op.drop_table("user_riot_account")
    op.drop_table("riot_account")
    op.drop_table("match")
    op.drop_table("user")
    op.drop_table("champion")
