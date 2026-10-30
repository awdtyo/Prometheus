"""FastAPI application factory and entry point.

The app factory accepts explicit settings so tests can use an isolated SQLite
database. Run with ``uvicorn backend.main:app --reload`` from the repository root.
"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse

from backend.api.router import api_router
from backend.db.database import init_db
from backend.errors import install_exception_handlers
from backend.logging_config import configure_logging
from backend.middleware import RequestContextMiddleware
from backend.services.factory import build_investigation_service
from backend.settings import Settings, get_settings
from backend.version import get_core_version

logger = logging.getLogger("backend.main")


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the FastAPI application.

    Passing explicit settings keeps tests isolated from the developer's ``.env``.
    """
    resolved = settings or get_settings()
    configure_logging(resolved)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        init_db(resolved.database_path)
        app.state.investigation_service = build_investigation_service(resolved)
        logger.info(
            "Application started",
            extra={
                "event": "startup",
                "environment": resolved.environment,
                "database_path": str(resolved.database_path),
                "mock_services": resolved.use_mock_services,
            },
        )
        try:
            yield
        finally:
            logger.info("Application stopped", extra={"event": "shutdown"})

    app = FastAPI(
        title=resolved.app_name,
        version=get_core_version(),
        description="HTTP surface for Mission Autopsy incident reconstruction.",
        lifespan=lifespan,
    )
    app.state.settings = resolved
    app.add_middleware(
        CORSMiddleware,
        allow_origins=resolved.cors_origin_list,
        allow_credentials="*" not in resolved.cors_origin_list,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID"],
    )
    app.add_middleware(RequestContextMiddleware)
    install_exception_handlers(app)
    app.include_router(api_router, prefix=resolved.api_prefix)

    @app.get("/", include_in_schema=False)
    def docs_redirect() -> RedirectResponse:
        return RedirectResponse(url="/docs")

    return app


app = create_app()
