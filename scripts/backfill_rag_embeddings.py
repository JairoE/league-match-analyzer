"""Backfill embedding vectors for existing LLMAnalysis records.

One-time script that generates embeddings for all llm_analysis rows
where embedding IS NULL. Run after the RAG migration has been applied.

Usage:
    python scripts/backfill_rag_embeddings.py [--batch-size N] [--dry-run]

Make target:
    make backfill-rag-embeddings
    make backfill-rag-embeddings DRY_RUN=1
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

# Allow running from the project root
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "services" / "api"))

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parents[1] / "services" / "api" / ".env")
except ImportError:
    pass

import dataclasses  # noqa: E402 — after sys.path insert

from sqlalchemy import select, update  # noqa: E402
from sqlmodel import col  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.core.logging import get_logger  # noqa: E402
from app.db.session import async_session_factory  # noqa: E402
from app.models.llm_analysis import LLMAnalysis  # noqa: E402
from app.services.llm_client import OpenAIClient  # noqa: E402
from app.services.rag_retrieval import build_embedding_text  # noqa: E402

logger = get_logger("scripts.backfill_rag_embeddings")


async def backfill(batch_size: int = 50, dry_run: bool = False) -> None:
    """Generate and store embeddings for LLMAnalysis rows missing them.

    Args:
        batch_size: Number of rows to process per batch.
        dry_run: When True, print what would happen without writing to DB.
    """
    settings = get_settings()

    if not settings.openai_api_key:
        print("ERROR: OPENAI_API_KEY is not set — cannot generate embeddings.")
        sys.exit(1)

    if not settings.rag_enabled:
        print("WARNING: RAG is disabled (RAG_ENABLED=false) — proceeding anyway.")

    embed_client = OpenAIClient(
        api_key=settings.openai_api_key,
        model=settings.llm_model_name,
    )

    async with async_session_factory() as session:
        result = await session.execute(
            select(LLMAnalysis).where(LLMAnalysis.embedding.is_(None))
        )
        rows: list[LLMAnalysis] = list(result.scalars().all())

    total = len(rows)
    print(f"Found {total} LLMAnalysis rows with null embeddings.")

    if total == 0:
        print("Nothing to backfill.")
        return

    if dry_run:
        print(f"[DRY RUN] Would generate embeddings for {total} rows.")
        for row in rows[:5]:
            embed_text = build_embedding_text(
                row.champion_name, row.rank_tier, row.input_payload
            )
            print(f"  {row.id}: {embed_text[:120]}")
        if total > 5:
            print(f"  ... and {total - 5} more")
        return

    processed = 0
    errors = 0

    for i in range(0, total, batch_size):
        batch = rows[i : i + batch_size]
        print(f"Processing batch {i // batch_size + 1} ({len(batch)} rows)...")

        async with async_session_factory() as session:
            for row in batch:
                try:
                    embed_text = build_embedding_text(
                        row.champion_name, row.rank_tier, row.input_payload
                    )
                    embedding = await embed_client.embed(
                        embed_text, model=settings.rag_embedding_model
                    )
                    await session.execute(
                        update(LLMAnalysis)
                        .where(LLMAnalysis.id == row.id)
                        .values(embedding=embedding)
                    )
                    processed += 1
                except Exception as exc:
                    logger.warning(
                        "backfill_embed_failed",
                        extra={"analysis_id": str(row.id), "error": str(exc)},
                    )
                    errors += 1

            await session.commit()

        print(f"  Batch done. Total processed: {processed}, errors: {errors}")

    print(f"\nBackfill complete: {processed} embeddings generated, {errors} errors.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill RAG embeddings for LLMAnalysis rows.")
    parser.add_argument("--batch-size", type=int, default=50)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    asyncio.run(backfill(batch_size=args.batch_size, dry_run=args.dry_run))


if __name__ == "__main__":
    main()
