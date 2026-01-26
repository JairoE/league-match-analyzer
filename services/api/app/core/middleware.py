import time
from uuid import uuid4

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.logging import get_logger
from app.core.request_id import set_request_id


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Add request IDs and log request lifecycle events."""

    async def dispatch(self, request: Request, call_next) -> Response:
        """Attach request id, log timing, and return the response.

        Args:
            request: Incoming request object.
            call_next: Next middleware or route handler.

        Returns:
            The response from downstream handlers.
        """
        request_id = request.headers.get("x-request-id") or str(uuid4())
        set_request_id(request_id)
        logger = get_logger("league_api.request")
        started_at = time.monotonic()
        logger.info(
            "request_started",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
            },
        )
        response = await call_next(request)
        duration_ms = int((time.monotonic() - started_at) * 1000)
        response.headers["x-request-id"] = request_id
        response.headers["x-response-time-ms"] = str(duration_ms)
        logger.info(
            "request_completed",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": duration_ms,
            },
        )
        return response
