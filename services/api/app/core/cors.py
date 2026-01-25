from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import Settings
from app.core.logging import get_logger


def _split_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def add_cors_middleware(app: FastAPI, settings: Settings) -> None:
    """Attach CORS middleware based on runtime settings.

    Retrieves allowed origins, methods, and headers from settings, normalizes
    them into lists, and logs the resolved configuration so preflight behavior
    is observable during development and testing.

    Args:
        app: FastAPI application instance.
        settings: Runtime settings with CORS configuration values.

    Returns:
        None.
    """
    logger = get_logger("league_api.cors")
    allowed_origins = _split_csv(settings.cors_allow_origins)
    allowed_methods = _split_csv(settings.cors_allow_methods)
    allowed_headers = _split_csv(settings.cors_allow_headers)
    allow_credentials = settings.cors_allow_credentials

    logger.info(
        "cors_configured",
        extra={
            "allow_origins": allowed_origins,
            "allow_methods": allowed_methods,
            "allow_headers": allowed_headers,
            "allow_credentials": allow_credentials,
        },
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_methods=allowed_methods,
        allow_headers=allowed_headers,
        allow_credentials=allow_credentials,
    )
