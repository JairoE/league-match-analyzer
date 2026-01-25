"""Structured logging for the LLM worker."""

import logging
import sys
from typing import Any

from app.config import get_settings


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
    """Configure structured logging for the worker.

    Returns:
        None.
    """
    settings = get_settings()
    root_logger = logging.getLogger()
    root_logger.setLevel(settings.log_level.upper())
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root_logger.handlers = [handler]


def get_logger(name: str) -> logging.Logger:
    """Get a logger configured for the worker.

    Args:
        name: Logger name to use.

    Returns:
        Logger instance.
    """
    return logging.getLogger(name)
