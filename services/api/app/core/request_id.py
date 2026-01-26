from contextvars import ContextVar


_request_id: ContextVar[str | None] = ContextVar("request_id", default=None)


def set_request_id(request_id: str | None) -> None:
    """Set the request identifier for the current context.

    Args:
        request_id: Identifier to store for the current request.

    Returns:
        None.
    """
    _request_id.set(request_id)


def get_request_id() -> str | None:
    """Get the request identifier from the current context.

    Returns:
        The request identifier if one is set.
    """
    return _request_id.get()
