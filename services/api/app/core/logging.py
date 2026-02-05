import json
import logging
import sys
from typing import Any

from app.core.config import get_settings
from app.core.request_id import get_request_id

# Fields reserved by Python's logging module - excluded from extras
RESERVED_LOG_FIELDS = {
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
    "message",
    "taskName",
}

# Fields containing long identifiers that should be truncated in dev mode
TRUNCATE_FIELDS = {"user_id", "puuid", "request_id", "match_id", "game_id"}


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
    """Format log records into valid JSON for production log ingestion."""

    def format(self, record: logging.LogRecord) -> str:
        """Format the log record as valid JSON.

        Args:
            record: Log record to be formatted.

        Returns:
            JSON string suitable for log aggregation systems.
        """
        payload: dict[str, Any] = {
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", None),
        }
        extras = {
            key: value
            for key, value in record.__dict__.items()
            if key not in RESERVED_LOG_FIELDS and not key.startswith("_")
        }
        if extras:
            payload.update(extras)
        return json.dumps(payload, default=str)


class DevFormatter(logging.Formatter):
    """Human-readable colored output for local development."""

    COLORS = {
        "DEBUG": "\033[36m",     # cyan
        "INFO": "\033[32m",      # green
        "WARNING": "\033[33m",   # yellow
        "ERROR": "\033[31m",     # red
        "CRITICAL": "\033[35m",  # magenta
    }
    RESET = "\033[0m"
    DIM = "\033[2m"

    def format(self, record: logging.LogRecord) -> str:
        """Format the log record for human readability.

        Args:
            record: Log record to be formatted.

        Returns:
            Colored, condensed string for terminal output.
        """
        color = self.COLORS.get(record.levelname, "")
        req_id = getattr(record, "request_id", "") or ""
        req_id_short = req_id[:8] if req_id else "--------"

        # Extract logger short name (last component)
        logger_short = record.name.split(".")[-1][:15]

        # Collect extras and shorten long values
        extras = {
            key: self._shorten(key, value)
            for key, value in record.__dict__.items()
            if key not in RESERVED_LOG_FIELDS and not key.startswith("_")
        }
        extra_str = " ".join(f"{k}={v}" for k, v in extras.items()) if extras else ""

        msg = record.getMessage()
        
        # Format: [req_id] LEVEL logger_name message key=value ...
        return (
            f"{self.DIM}[{req_id_short}]{self.RESET} "
            f"{color}{record.levelname:5}{self.RESET} "
            f"{logger_short:15} "
            f"{msg}"
            f"{(' ' + extra_str) if extra_str else ''}"
        )

    def _shorten(self, key: str, value: Any) -> str:
        """Truncate long identifiers and URLs for readability.

        Args:
            key: Field name being formatted.
            value: Field value to potentially truncate.

        Returns:
            Shortened string representation.
        """
        if not isinstance(value, str):
            return str(value)
        
        # Truncate UUIDs and PUUIDs
        if key in TRUNCATE_FIELDS and len(value) > 12:
            return value[:8] + "..."
        
        # Truncate long URLs
        if key == "url" and len(value) > 50:
            return value[:45] + "..."
        
        return value


def setup_logging() -> None:
    """Configure structured logging for the service.

    Uses DevFormatter for local development (colored, truncated).
    Uses JsonFormatter for staging/production (valid JSON).

    Returns:
        None.
    """
    settings = get_settings()
    root_logger = logging.getLogger()
    root_logger.setLevel(settings.log_level.upper())
    
    handler = logging.StreamHandler(sys.stdout)
    handler.addFilter(RequestIdFilter())
    
    # Use human-readable format locally, JSON in production
    if settings.environment == "development":
        handler.setFormatter(DevFormatter())
    else:
        handler.setFormatter(JsonFormatter())
    
    root_logger.handlers = [handler]


def get_logger(name: str) -> logging.Logger:
    """Get a logger configured for the service.

    Args:
        name: Logger name to use.

    Returns:
        Logger instance configured with request id support.
    """
    return logging.getLogger(name)
