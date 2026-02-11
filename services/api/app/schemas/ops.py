from pydantic import BaseModel, Field


class WorkerMetricsSnapshot(BaseModel):
    """Snapshot of ARQ worker counters stored in Redis."""

    metrics: dict[str, int] = Field(
        default_factory=dict,
        description="Counter map keyed by metric name with optional encoded tags.",
    )
