"""RAG: add embedding vector column to llm_analysis.

Revision ID: 20260601_0004
Revises: 20260316_0003
Create Date: 2026-06-01

Changes:
  - Ensures pgvector extension is enabled
  - Adds nullable vector(1536) embedding column to llm_analysis
  - Creates HNSW cosine-distance index for sub-linear similarity search
"""

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

revision = "20260601_0004"
down_revision = "20260316_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.add_column(
        "llm_analysis",
        sa.Column("embedding", Vector(1536), nullable=True),
    )

    # HNSW index for sub-linear cosine-distance nearest-neighbor search.
    # m=16 / ef_construction=64 are pgvector defaults — good balance of
    # build time vs. recall at this corpus size.
    op.execute(
        "CREATE INDEX ix_llm_analysis_embedding_hnsw ON llm_analysis "
        "USING hnsw (embedding vector_cosine_ops) "
        "WITH (m = 16, ef_construction = 64)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_llm_analysis_embedding_hnsw")
    op.drop_column("llm_analysis", "embedding")
