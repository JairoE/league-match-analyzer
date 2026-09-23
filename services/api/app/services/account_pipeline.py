"""One-shot, idempotent ingest → extract → score → analyze pipeline for one account.

Backs ``make up RIOT_ID=...`` / ``make pipeline``. The ARQ worker remains the
only executor: this module finds gaps in the DB, enqueues the missing work with
the same deterministic ``_job_id``s the API and worker use (so anything already
queued or running is deduped by ARQ), and polls the DB until the work drains.
Work that a background run already finished is excluded by the gap queries.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any, Protocol
from uuid import UUID

from arq.constants import default_queue_name
from arq.jobs import ResultNotFound
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.db.session import async_session_factory
from app.models.riot_account import RiotAccount
from app.services.analysis_champions import AnalyzableChampion, list_analyzable_champions
from app.services.arq_pool import get_arq_pool
from app.services.enqueue_match_details import enqueue_missing_detail_jobs
from app.services.enqueue_timeline_extraction import enqueue_missing_extraction_jobs
from app.services.llm_analyses import ANALYSIS_CACHE_HOURS, analysis_job_id, latest_analysis
from app.services.riot_account_upsert import find_or_create_riot_account
from app.services.riot_accounts import get_riot_account_by_riot_id
from app.services.riot_api_client import RiotApiClient, RiotRequestError
from app.services.riot_id_parser import parse_riot_id
from app.services.riot_sync import fetch_match_list_for_riot_account

logger = get_logger("league_api.services.account_pipeline")

# Manual scoring namespace (matches scripts/score_actions_for_match.py), kept
# apart from the worker's score-actions:auto:* ids so a recent no-model
# auto-skip does not dedupe a deliberate re-score.
SCORE_JOB_ID_PREFIX = "score-actions:v0:"
POLL_INTERVAL_S = 3.0
STALL_SECONDS = 120.0
DEFAULT_TIMEOUT_S = 900.0
DEFAULT_MATCH_COUNT = 20

Emit = Callable[[str], None]
SessionFactory = Callable[[], Any]


class PipelineConfigError(RuntimeError):
    """Raised when required configuration for the pipeline is missing."""


class _EnqueuePool(Protocol):
    async def enqueue_job(self, function_name: str, *args: object, **kwargs: object) -> Any: ...


@dataclass(frozen=True)
class PipelineCounts:
    """Per-stage progress for an account's linked match history."""

    linked: int
    with_details: int
    extracted: int
    scored: int


@dataclass
class ChampionOutcome:
    """Result of the LLM analysis stage for one champion."""

    champion_id: int
    champion_name: str
    status: str
    analysis_id: str | None = None
    token_input: int = 0
    token_output: int = 0
    detail: str = ""


@dataclass
class PipelineReport:
    """Everything the CLI needs to print a run summary."""

    riot_id: str
    riot_account_id: str | None = None
    account_created: bool = False
    fetched_match_ids: int = 0
    enqueued_details: int = 0
    enqueued_extraction: int = 0
    enqueued_scoring: int = 0
    counts_before: PipelineCounts | None = None
    counts_after: PipelineCounts | None = None
    drain_outcome: str = "not_run"
    champions: list[ChampionOutcome] = field(default_factory=list)
    llm_skipped_reason: str | None = None
    missing_embeddings: int = 0
    warnings: list[str] = field(default_factory=list)


def check_preflight(settings: Settings) -> list[str]:
    """Validate configuration the pipeline depends on.

    Args:
        settings: Loaded application settings.

    Returns:
        Non-fatal warnings to surface to the operator.

    Raises:
        PipelineConfigError: When the Riot API key is missing.
    """
    if not settings.riot_api_key or settings.riot_api_key == "replace-me":
        raise PipelineConfigError("RIOT_API_KEY is not set in services/api/.env")
    warnings: list[str] = []
    if not settings.win_prob_model_path:
        warnings.append(
            "WIN_PROB_MODEL_PATH is empty: score_actions_job will skip, so no champion "
            "becomes eligible for AI Coach analysis."
        )
    if not settings.openai_api_key:
        warnings.append("OPENAI_API_KEY is empty: the LLM analysis stage will be skipped.")
    for warning in warnings:
        logger.warning("account_pipeline_preflight_warning", extra={"warning": warning})
    return warnings


async def resolve_or_create_account(
    session: AsyncSession,
    riot_id: str,
    *,
    create: bool = True,
) -> tuple[RiotAccount | None, bool]:
    """Find the account by canonical Riot ID, creating it from Riot if missing.

    Args:
        session: Async database session.
        riot_id: Riot ID in ``gameName#tagLine`` form.
        create: When False, never call Riot or write (dry runs).

    Returns:
        Tuple of (account or None when missing and not created, was_created).
    """
    parsed = parse_riot_id(riot_id)
    account = await get_riot_account_by_riot_id(session, parsed.canonical)
    if account is not None or not create:
        return account, False

    logger.info("account_pipeline_create_account", extra={"riot_id": parsed.canonical})
    async with RiotApiClient() as client:
        account_info = await client.fetch_account_by_riot_id(parsed.game_name, parsed.tag_line)
        summoner_info = await client.fetch_summoner_by_puuid(account_info["puuid"])
    account = await find_or_create_riot_account(
        session,
        riot_id=parsed.canonical,
        puuid=account_info["puuid"],
        summoner_info=summoner_info,
    )
    await session.commit()
    await session.refresh(account)
    return account, True


async def list_account_match_ids(session: AsyncSession, riot_account_id: UUID) -> list[str]:
    """List every Riot match id linked to an account.

    Args:
        session: Async database session.
        riot_account_id: Account UUID.

    Returns:
        Riot match ids (``game_id``) across the account's full linked history.
    """
    result = await session.execute(
        text("""
            SELECT m.game_id
            FROM riot_account_match ram
            JOIN match m ON m.id = ram.match_id
            WHERE ram.riot_account_id = :riot_account_id
        """),
        {"riot_account_id": str(riot_account_id)},
    )
    return [row[0] for row in result.fetchall()]


async def find_unscored_match_ids(session: AsyncSession, riot_account_id: UUID) -> list[str]:
    """List linked matches that have extracted actions but none scored.

    Args:
        session: Async database session.
        riot_account_id: Account UUID.

    Returns:
        Riot match ids that need ``score_actions_job``.
    """
    result = await session.execute(
        text("""
            SELECT m.game_id
            FROM riot_account_match ram
            JOIN match m ON m.id = ram.match_id
            WHERE ram.riot_account_id = :riot_account_id
              AND EXISTS (SELECT 1 FROM match_action ma WHERE ma.match_id = m.id)
              AND NOT EXISTS (
                SELECT 1 FROM match_action ma
                WHERE ma.match_id = m.id AND ma.delta_w IS NOT NULL
              )
        """),
        {"riot_account_id": str(riot_account_id)},
    )
    return [row[0] for row in result.fetchall()]


async def get_pipeline_counts(session: AsyncSession, riot_account_id: UUID) -> PipelineCounts:
    """Count how far each linked match has progressed through the pipeline.

    Args:
        session: Async database session.
        riot_account_id: Account UUID.

    Returns:
        Linked / with-details / extracted / scored match counts.
    """
    result = await session.execute(
        text("""
            SELECT
              COUNT(*)::int AS linked,
              COUNT(*) FILTER (
                WHERE m.game_info IS NOT NULL AND m.game_info::text <> 'null'
              )::int AS with_details,
              COUNT(*) FILTER (
                WHERE EXISTS (SELECT 1 FROM match_state_vector sv WHERE sv.match_id = m.id)
              )::int AS extracted,
              COUNT(*) FILTER (
                WHERE EXISTS (
                  SELECT 1 FROM match_action ma
                  WHERE ma.match_id = m.id AND ma.delta_w IS NOT NULL
                )
              )::int AS scored
            FROM riot_account_match ram
            JOIN match m ON m.id = ram.match_id
            WHERE ram.riot_account_id = :riot_account_id
        """),
        {"riot_account_id": str(riot_account_id)},
    )
    row = result.mappings().one()
    return PipelineCounts(
        linked=row["linked"],
        with_details=row["with_details"],
        extracted=row["extracted"],
        scored=row["scored"],
    )


async def count_missing_embeddings(session: AsyncSession, riot_account_id: UUID) -> int:
    """Count the account's analyses that have no RAG embedding yet.

    Args:
        session: Async database session.
        riot_account_id: Account UUID.

    Returns:
        Number of ``llm_analysis`` rows with a NULL embedding.
    """
    result = await session.execute(
        text("""
            SELECT COUNT(*)::int FROM llm_analysis
            WHERE riot_account_id = :riot_account_id AND embedding IS NULL
        """),
        {"riot_account_id": str(riot_account_id)},
    )
    return int(result.scalar_one())


async def enqueue_scoring_jobs(pool: _EnqueuePool, match_ids: list[str]) -> int:
    """Enqueue ``score_actions_job`` for each match with the manual job id.

    Args:
        pool: ARQ-compatible pool.
        match_ids: Riot match ids to score.

    Returns:
        Number of jobs actually enqueued (ARQ dedupe rejections excluded).
    """
    enqueued = 0
    for match_id in match_ids:
        job = await pool.enqueue_job(
            "score_actions_job",
            match_id,
            _job_id=f"{SCORE_JOB_ID_PREFIX}{match_id}",
        )
        if job is not None:
            enqueued += 1
    return enqueued


async def wait_for_drain(
    read_counts: Callable[[], Awaitable[PipelineCounts]],
    read_queue_depth: Callable[[], Awaitable[int]],
    *,
    timeout_s: float = DEFAULT_TIMEOUT_S,
    poll_interval_s: float = POLL_INTERVAL_S,
    stall_s: float = STALL_SECONDS,
    on_progress: Callable[[PipelineCounts, int], None] | None = None,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> tuple[PipelineCounts, str]:
    """Poll until the worker has finished the enqueued ingest/extract/score work.

    Exit conditions, checked in order on every poll:

    - ``complete``: every linked match has scored actions.
    - ``settled``: the ARQ queue was empty on two consecutive polls. Chained
      jobs enqueue their successor before finishing, so an empty queue means
      no pipeline work is pending (some matches legitimately never score).
    - ``stalled``: counts unchanged for ``stall_s`` while the queue is busy —
      usually the worker is not running or is serving other accounts.
    - ``timeout``: ``timeout_s`` elapsed.

    Args:
        read_counts: Returns current per-stage counts.
        read_queue_depth: Returns the number of queued + in-progress ARQ jobs.
        timeout_s: Hard upper bound on waiting.
        poll_interval_s: Delay between polls.
        stall_s: No-progress window before giving up.
        on_progress: Optional callback for each poll.
        clock: Monotonic clock (injectable for tests).
        sleep: Sleep function (injectable for tests).

    Returns:
        Tuple of (last observed counts, outcome string).
    """
    start = clock()
    last_counts: PipelineCounts | None = None
    last_change = start
    empty_streak = 0
    while True:
        counts = await read_counts()
        depth = await read_queue_depth()
        now = clock()
        if on_progress is not None:
            on_progress(counts, depth)
        if counts.scored >= counts.linked:
            return counts, "complete"
        if counts != last_counts:
            last_counts = counts
            last_change = now
        empty_streak = empty_streak + 1 if depth == 0 else 0
        if empty_streak >= 2:
            return counts, "settled"
        if now - last_change >= stall_s:
            return counts, "stalled"
        if now - start >= timeout_s:
            return counts, "timeout"
        await sleep(poll_interval_s)


def _outcome_from_result(champion: AnalyzableChampion, result: dict[str, Any]) -> ChampionOutcome:
    return ChampionOutcome(
        champion_id=champion.champion_id,
        champion_name=champion.champion_name,
        status=str(result.get("status", "unknown")),
        analysis_id=result.get("analysis_id"),
        token_input=int(result.get("token_input") or 0),
        token_output=int(result.get("token_output") or 0),
        detail=str(result.get("reason", "")),
    )


async def _poll_for_new_analysis(
    session_factory: SessionFactory,
    riot_account_id: UUID,
    champion: AnalyzableChampion,
    since: datetime,
    timeout_s: float,
    poll_interval_s: float,
) -> ChampionOutcome:
    """Wait for a row written by a job this run could not observe directly."""
    deadline = time.monotonic() + timeout_s
    while True:
        async with session_factory() as session:
            row = await latest_analysis(
                session, riot_account_id, champion.champion_name, since=since
            )
        if row is not None:
            return ChampionOutcome(
                champion_id=champion.champion_id,
                champion_name=champion.champion_name,
                status="ok",
                analysis_id=str(row.id),
                token_input=row.token_count_input or 0,
                token_output=row.token_count_output or 0,
            )
        if time.monotonic() >= deadline:
            return ChampionOutcome(
                champion_id=champion.champion_id,
                champion_name=champion.champion_name,
                status="timeout",
            )
        await asyncio.sleep(poll_interval_s)


async def analyze_champion(
    session_factory: SessionFactory,
    pool: _EnqueuePool,
    riot_account_id: UUID,
    champion: AnalyzableChampion,
    *,
    timeout_s: float = DEFAULT_TIMEOUT_S,
    poll_interval_s: float = POLL_INTERVAL_S,
    dry_run: bool = False,
    now: datetime | None = None,
) -> ChampionOutcome:
    """Run (or skip) the AI Coach analysis for one champion via the worker.

    Skips when an analysis exists within ``ANALYSIS_CACHE_HOURS`` — the same
    rule the analysis endpoint uses — otherwise enqueues ``llm_analysis_job``
    with the endpoint's deterministic job id and waits for its result.

    Args:
        session_factory: Async session factory.
        pool: ARQ-compatible pool.
        riot_account_id: Account UUID.
        champion: Eligible champion to analyze.
        timeout_s: Max wait for the job result.
        poll_interval_s: DB poll delay when the job result is unobservable.
        dry_run: Report what would run without enqueueing.
        now: Current time (injectable for tests).

    Returns:
        Outcome for this champion.
    """
    current = now or datetime.now(UTC)
    cutoff = current - timedelta(hours=ANALYSIS_CACHE_HOURS)
    async with session_factory() as session:
        existing = await latest_analysis(
            session, riot_account_id, champion.champion_name, since=cutoff
        )
    if existing is not None:
        return ChampionOutcome(
            champion_id=champion.champion_id,
            champion_name=champion.champion_name,
            status="cached",
            analysis_id=str(existing.id),
        )
    if dry_run:
        return ChampionOutcome(
            champion_id=champion.champion_id,
            champion_name=champion.champion_name,
            status="would_run",
        )

    job = await pool.enqueue_job(
        "llm_analysis_job",
        str(riot_account_id),
        str(champion.champion_id),
        None,
        # Local date, matching the analysis endpoint, so a UI click and this
        # run share one id and dedupe against each other.
        _job_id=analysis_job_id(riot_account_id, champion.champion_id, date.today()),
    )
    logger.info(
        "account_pipeline_analysis_enqueued",
        extra={
            "riot_account_id": str(riot_account_id),
            "champion_name": champion.champion_name,
            "deduped": job is None,
        },
    )
    if job is not None:
        try:
            result = await job.result(timeout=timeout_s)
        except TimeoutError:
            return ChampionOutcome(
                champion_id=champion.champion_id,
                champion_name=champion.champion_name,
                status="timeout",
            )
        except ResultNotFound:
            result = None
        except Exception as exc:
            return ChampionOutcome(
                champion_id=champion.champion_id,
                champion_name=champion.champion_name,
                status="error",
                detail=str(exc),
            )
        if isinstance(result, dict):
            return _outcome_from_result(champion, result)

    # Deduped against an in-flight job (e.g. a UI click) or the result expired
    # before we read it: fall back to watching for the persisted row.
    return await _poll_for_new_analysis(
        session_factory, riot_account_id, champion, cutoff, timeout_s, poll_interval_s
    )


async def run_account_pipeline(
    riot_id: str,
    *,
    count: int = DEFAULT_MATCH_COUNT,
    timeout_s: float = DEFAULT_TIMEOUT_S,
    skip_llm: bool = False,
    dry_run: bool = False,
    emit: Emit = lambda message: None,
    session_factory: SessionFactory = async_session_factory,
) -> PipelineReport:
    """Bring one account fully up to date: ingest → extract → score → analyze.

    Args:
        riot_id: Riot ID in ``gameName#tagLine`` form.
        count: Number of latest match ids to fetch from Riot.
        timeout_s: Upper bound for each waiting stage.
        skip_llm: Skip the LLM analysis stage.
        dry_run: Report gaps and planned work without calling Riot or enqueueing.
        emit: Callback for human-readable progress lines.
        session_factory: Async session factory.

    Returns:
        Report describing what was found, enqueued, and produced.

    Raises:
        PipelineConfigError: When required configuration is missing.
    """
    report = PipelineReport(riot_id=riot_id)
    settings = get_settings()
    report.warnings = check_preflight(settings)
    for warning in report.warnings:
        emit(f"WARN {warning}")
    logger.info(
        "account_pipeline_start",
        extra={"riot_id": riot_id, "count": count, "dry_run": dry_run, "skip_llm": skip_llm},
    )

    async with session_factory() as session:
        account, created = await resolve_or_create_account(session, riot_id, create=not dry_run)
        if account is None:
            emit(f"Account {riot_id} is not in the DB yet; a real run would create it.")
            return report
        account_id: UUID = account.id  # type: ignore[assignment]
        report.riot_account_id = str(account_id)
        report.account_created = created
        emit(f"Account {account.riot_id} ({account_id}){' created' if created else ''}")

        if not dry_run:
            try:
                fetched = await fetch_match_list_for_riot_account(
                    session, str(account_id), start=0, count=count
                )
                report.fetched_match_ids = len(fetched[0]) if fetched else 0
                emit(f"Fetched {report.fetched_match_ids} latest match ids from Riot")
            except RiotRequestError as exc:
                if exc.status != 429:
                    raise
                report.warnings.append("Riot rate limited the match-id fetch; using DB state.")
                emit("WARN Riot rate limited the match-id fetch; continuing with DB state")

        match_ids = await list_account_match_ids(session, account_id)
        unscored = await find_unscored_match_ids(session, account_id)
        report.counts_before = await get_pipeline_counts(session, account_id)

    before = report.counts_before
    emit(
        f"History: {before.linked} linked, {before.linked - before.with_details} need details, "
        f"{before.with_details - before.extracted} need extraction, "
        f"{len(unscored)} need scoring"
    )

    pool = await get_arq_pool()
    if not dry_run:
        report.enqueued_details = await enqueue_missing_detail_jobs(match_ids, pool=pool)
        report.enqueued_extraction = await enqueue_missing_extraction_jobs(match_ids, pool=pool)
        report.enqueued_scoring = await enqueue_scoring_jobs(pool, unscored)
        emit(
            f"Enqueued: {report.enqueued_details} detail, {report.enqueued_extraction} "
            f"extraction, {report.enqueued_scoring} scoring (already-queued work is deduped)"
        )

        async def _read_counts() -> PipelineCounts:
            async with session_factory() as poll_session:
                return await get_pipeline_counts(poll_session, account_id)

        async def _read_queue_depth() -> int:
            return int(await pool.zcard(default_queue_name))

        last_line: list[str] = [""]

        def _on_progress(counts: PipelineCounts, depth: int) -> None:
            line = (
                f"Progress: details {counts.with_details}/{counts.linked}, "
                f"extracted {counts.extracted}, scored {counts.scored}, queue {depth}"
            )
            if line != last_line[0]:
                last_line[0] = line
                emit(line)

        report.counts_after, report.drain_outcome = await wait_for_drain(
            _read_counts,
            _read_queue_depth,
            timeout_s=timeout_s,
            on_progress=_on_progress,
        )
        emit(f"Match processing {report.drain_outcome}")
        if report.drain_outcome == "stalled":
            report.warnings.append(
                "No progress while the ARQ queue stayed busy; is the worker running?"
            )

    if skip_llm:
        report.llm_skipped_reason = "--skip-llm"
    elif not settings.openai_api_key:
        report.llm_skipped_reason = "OPENAI_API_KEY not set"
    else:
        async with session_factory() as session:
            champions = await list_analyzable_champions(session, account_id)
        emit(f"AI Coach: {len(champions)} eligible champion(s)")
        report.champions = list(
            await asyncio.gather(
                *(
                    analyze_champion(
                        session_factory,
                        pool,
                        account_id,
                        champion,
                        timeout_s=timeout_s,
                        dry_run=dry_run,
                    )
                    for champion in champions
                )
            )
        )

    async with session_factory() as session:
        report.missing_embeddings = await count_missing_embeddings(session, account_id)
        if not dry_run:
            # The worker may have caught up during the LLM stage (e.g. after a
            # stall), so report final counts rather than the drain snapshot.
            report.counts_after = await get_pipeline_counts(session, account_id)

    logger.info(
        "account_pipeline_done",
        extra={
            "riot_account_id": report.riot_account_id,
            "drain_outcome": report.drain_outcome,
            "champions": len(report.champions),
        },
    )
    return report
