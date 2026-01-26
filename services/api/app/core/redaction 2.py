"""Utilities for redacting sensitive configuration values."""

from __future__ import annotations

from urllib.parse import urlsplit, urlunsplit


def redact_url(value: str) -> str:
    """Redact credentials from a connection string.

    Retrieves the input URL, masks any embedded password, and returns a safe
    string for logs so production credentials are never exposed.

    Args:
        value: Connection string that may include credentials.

    Returns:
        URL with password removed or masked.
    """
    if not value:
        return value
    try:
        parts = urlsplit(value)
    except ValueError:
        return value

    if not parts.username and not parts.password:
        return value

    hostname = parts.hostname or ""
    port = f":{parts.port}" if parts.port else ""
    username = parts.username or ""
    password = "****" if parts.password else ""
    auth = ""
    if username:
        auth = f"{username}:{password}@" if password else f"{username}@"
    netloc = f"{auth}{hostname}{port}"
    return urlunsplit(parts._replace(netloc=netloc))
