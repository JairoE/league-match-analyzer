from fastapi import APIRouter, status

from app.schemas.ops import WorkerMetricsSnapshot
from app.services.worker_metrics import get_worker_metrics_snapshot

router = APIRouter(prefix="/ops", tags=["ops"])


@router.get(
    "/worker-metrics",
    response_model=WorkerMetricsSnapshot,
    status_code=status.HTTP_200_OK,
)
async def worker_metrics() -> WorkerMetricsSnapshot:
    """Return ARQ worker failure/retry counters from Redis."""
    metrics = await get_worker_metrics_snapshot()
    return WorkerMetricsSnapshot(metrics=metrics)
