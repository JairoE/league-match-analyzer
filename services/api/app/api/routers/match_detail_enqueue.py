from collections.abc import Mapping
from typing import Any

from app.services.enqueue_match_details import enqueue_missing_detail_jobs


async def enqueue_details_background(
    *,
    logger: Any,
    match_ids: list[str],
    success_event: str,
    failure_event: str,
    context: Mapping[str, Any] | None = None,
) -> None:
    """Fire-and-forget wrapper for ``enqueue_missing_detail_jobs`` with shared logging."""
    extra = dict(context or {})
    logger.info(
        "enqueue_details_background_start",
        extra={**extra, "match_count": len(match_ids)},
    )
    try:
        enqueued = await enqueue_missing_detail_jobs(match_ids)
        if enqueued:
            logger.info(success_event, extra={**extra, "enqueued": enqueued})
    except Exception:
        logger.exception(failure_event, extra=extra)
