import time
from uuid import uuid4

from fastapi import FastAPI, Request, Response

from app.api.routers import all_routers
from app.core.config import get_settings
from app.core.cors import add_cors_middleware
from app.core.logging import get_logger, setup_logging
from app.core.middleware import RequestLoggingMiddleware
from app.services.champion_seed import schedule_champion_seed_job


setup_logging()
logger = get_logger("league_api.main")
settings = get_settings()

app = FastAPI(title=settings.service_name)
add_cors_middleware(app, settings)
app.add_middleware(RequestLoggingMiddleware)

for router in all_routers:
    app.include_router(router)


@app.get("/health")
def health_check(request: Request, response: Response) -> dict[str, str]:
    """Return a lightweight health check response.

    Args:
        request: Incoming request object.
        response: Outgoing response object.

    Returns:
        A simple status payload to confirm the API is running.
    """
    request_id = request.headers.get("x-request-id") or str(uuid4())
    response.headers["x-request-id"] = request_id
    started_at = time.monotonic()
    logger.info(
        "health_check",
        extra={"request_id": request_id, "path": "/health"},
    )
    duration_ms = int((time.monotonic() - started_at) * 1000)
    response.headers["x-response-time-ms"] = str(duration_ms)
    return {"status": "ok"}


@app.on_event("startup")
async def on_startup() -> None:
    """Log service startup with runtime configuration details.

    Returns:
        None.
    """
    logger.info(
        "startup",
        extra={
            "service_name": settings.service_name,
            "log_level": settings.log_level,
            "database_url": settings.database_url,
            "redis_url": settings.redis_url,
        },
    )
    schedule_champion_seed_job(reason="startup", force_reset=False)


@app.on_event("shutdown")
async def on_shutdown() -> None:
    """Log service shutdown so it is visible in logs.

    Returns:
        None.
    """
    logger.info("shutdown")
