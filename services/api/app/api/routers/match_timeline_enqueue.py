"""Background task wrapper for enqueueing timeline pre-fetch jobs.

Follows the same fire-and-forget pattern as ``match_detail_enqueue.py``.
"""

from collections.abc import Mapping
from typing import Any

from app.services.enqueue_match_timelines import enqueue_missing_timeline_jobs


async def enqueue_timelines_background(
    *,
    logger: Any,
    match_ids: list[str],
    success_event: str,
    failure_event: str,
    context: Mapping[str, Any] | None = None,
) -> None:
    """Fire-and-forget wrapper for ``enqueue_missing_timeline_jobs``."""
    extra = dict(context or {})
    logger.info(
        "enqueue_timelines_background_start",
        extra={**extra, "match_count": len(match_ids)},
    )
    try:
        enqueued = await enqueue_missing_timeline_jobs(match_ids)
        if enqueued:
            logger.info(success_event, extra={**extra, "enqueued": enqueued})
    except Exception:
        logger.exception(failure_event, extra=extra)
