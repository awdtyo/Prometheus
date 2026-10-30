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

from autopsy import __version__
from backend.api.router import api_router
from backend.db.database import init_db
from backend.settings import Settings, get_settings

logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the FastAPI application.

    Passing explicit settings keeps tests isolated from the developer's ``.env``.
    """
    resolved = settings or get_settings()
    logging.basicConfig(
        level=resolved.log_level.upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        init_db(resolved.database_path)
        logger.info("SQLite ready at %s", resolved.database_path)
        yield

    app = FastAPI(
        title=resolved.app_name,
        version=__version__,
        description="HTTP surface for Mission Autopsy incident reconstruction.",
        lifespan=lifespan,
    )
    app.state.settings = resolved
    app.add_middleware(
        CORSMiddleware,
        allow_origins=resolved.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(api_router, prefix="/api")

    @app.get("/", include_in_schema=False)
    def docs_redirect() -> RedirectResponse:
        return RedirectResponse(url="/docs")

    return app


app = create_app()
