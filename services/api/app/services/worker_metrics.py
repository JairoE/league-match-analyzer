from __future__ import annotations

from app.core.logging import get_logger
from app.services.cache import get_redis

logger = get_logger("league_api.services.worker_metrics")

WORKER_METRICS_KEY = "metrics:worker:arq"


def _build_metric_field(metric: str, tags: dict[str, str] | None = None) -> str:
    """Build a stable Redis hash field name for a metric series.

    Args:
        metric: Metric name (e.g., jobs.fetch_user_matches.failed).
        tags: Optional tags to attach to the metric series.

    Returns:
        Canonical metric field key.
    """
    if not tags:
        return metric

    ordered = sorted((str(k), str(v)) for k, v in tags.items())
    encoded = ",".join(f"{k}={v}" for k, v in ordered)
    return f"{metric}|{encoded}"


async def increment_metric(
    metric: str,
    amount: int = 1,
    tags: dict[str, str] | None = None,
) -> None:
    """Increment a worker metric counter in Redis.

    Retrieves: Existing counter from Redis hash.
    Transforms: Applies atomic increment via HINCRBY.
    Why: Centralizes worker failure/retry visibility across processes.

    Args:
        metric: Metric name.
        amount: Increment amount.
        tags: Optional labels for dimensioned counters.
    """
    field = _build_metric_field(metric, tags)
    redis = get_redis()
    await redis.hincrby(WORKER_METRICS_KEY, field, amount)


async def increment_metric_safe(
    metric: str,
    amount: int = 1,
    tags: dict[str, str] | None = None,
) -> None:
    """Increment a metric and swallow errors to avoid job disruption.

    Args:
        metric: Metric name.
        amount: Increment amount.
        tags: Optional labels for dimensioned counters.
    """
    try:
        await increment_metric(metric, amount=amount, tags=tags)
    except Exception as exc:
        logger.warning(
            "worker_metric_increment_failed",
            extra={
                "metric": metric,
                "amount": amount,
                "tags": tags or {},
                "error": str(exc),
            },
        )


async def get_worker_metrics_snapshot() -> dict[str, int]:
    """Read all worker metrics from Redis.

    Returns:
        Mapping of metric series key to integer count.
    """
    redis = get_redis()
    raw = await redis.hgetall(WORKER_METRICS_KEY)
    metrics: dict[str, int] = {}
    for key, value in raw.items():
        try:
            metrics[str(key)] = int(value)
        except (TypeError, ValueError):
            logger.warning(
                "worker_metric_parse_error",
                extra={"field": str(key), "value": str(value)},
            )
    return metrics
