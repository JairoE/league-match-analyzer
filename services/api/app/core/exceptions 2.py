from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.core.logging import get_logger
from app.services.riot_api_client import RiotRequestError

logger = get_logger("league_api.exceptions")


def _map_riot_status(status: int | None) -> int:
    if status is None:
        return 502
    if status in {400, 401, 403, 404, 429}:
        return status
    if status >= 500:
        return 502
    return 502


def register_exception_handlers(app: FastAPI) -> None:
    """Register API exception handlers.

    Args:
        app: FastAPI application instance.

    Returns:
        None.
    """

    @app.exception_handler(RiotRequestError)
    async def riot_request_error_handler(request: Request, exc: RiotRequestError) -> JSONResponse:
        mapped_status = _map_riot_status(exc.status)
        logger.info(
            "riot_request_error_handled",
            extra={
                "path": request.url.path,
                "method": request.method,
                "riot_status": exc.status,
                "mapped_status": mapped_status,
                "error_message": exc.message,
            },
        )
        return JSONResponse(
            status_code=mapped_status,
            content={
                "detail": exc.message,
                "riot_status": exc.status,
            },
        )
