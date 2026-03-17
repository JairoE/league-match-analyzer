"""Add rank_tier column to riot_account.

Revision ID: 20260316_0003
Revises: 20260305_0002
Create Date: 2026-03-16
"""

import sqlalchemy as sa
from alembic import op

revision = "20260316_0003"
down_revision = "20260305_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("riot_account", sa.Column("rank_tier", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("riot_account", "rank_tier")
