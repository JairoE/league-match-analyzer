import logging
import sys
from typing import Any

from app.core.config import get_settings
from app.core.request_id import get_request_id


class RequestIdFilter(logging.Filter):
    """Inject request identifiers into log records."""

    def filter(self, record: logging.LogRecord) -> bool:
        """Attach the request id to the log record.

        Args:
            record: Log record for the current logging call.

        Returns:
            True to keep the record.
        """
        record.request_id = get_request_id()
        return True


class JsonFormatter(logging.Formatter):
    """Format log records into a JSON-like string payload."""

    def format(self, record: logging.LogRecord) -> str:
        """Format the log record for structured output.

        Args:
            record: Log record to be formatted.

        Returns:
            JSON-like string suitable for log ingestion.
        """
        message: dict[str, Any] = {
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", None),
        }
        reserved = {
            "name",
            "msg",
            "args",
            "levelname",
            "levelno",
            "pathname",
            "filename",
            "module",
            "exc_info",
            "exc_text",
            "stack_info",
            "lineno",
            "funcName",
            "created",
            "msecs",
            "relativeCreated",
            "thread",
            "threadName",
            "processName",
            "process",
            "request_id",
        }
        extras = {
            key: value
            for key, value in record.__dict__.items()
            if key not in reserved
        }
        if extras:
            message.update(extras)
        return str(message)


def setup_logging() -> None:
    """Configure structured logging for the service.

    Returns:
        None.
    """
    settings = get_settings()
    root_logger = logging.getLogger()
    root_logger.setLevel(settings.log_level.upper())
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    handler.addFilter(RequestIdFilter())
    root_logger.handlers = [handler]


def get_logger(name: str) -> logging.Logger:
    """Get a logger configured for the service.

    Args:
        name: Logger name to use.

    Returns:
        Logger instance configured with request id support.
    """
    return logging.getLogger(name)
