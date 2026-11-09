"""Compose the opt-in grounded extraction route into the original main API without changing it."""

import logging
import os
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI

LOGGER = logging.getLogger(__name__)
DOCS = frozenset({"openapi", "swagger_ui_html", "swagger_ui_redirect", "redoc_html"})
ENABLED = (
    "ASSISTANT_FILES_ENABLED",
    "ASSISTANT_INGESTION_ENABLED",
    "ASSISTANT_RETRIEVAL_ENABLED",
    "ASSISTANT_GROUNDED_ENABLED",
)
PRESENT = ("DATABASE_URL", "ASSISTANT_INGESTION_CONFIG_FILE", "ASSISTANT_AUTH_FILE")


def compose(base):
    """Build a new app from the original routes plus the extract route, requiring live grounded services."""
    from apps.api.routes.grounded_extract import router

    @asynccontextmanager
    async def lifespan(app):
        """Run the unchanged base lifespan and refuse startup without live linked retrieval/grounded services."""
        async with base.router.lifespan_context(app):
            retrieval = getattr(app.state, "retrieval_service", None)
            grounded = getattr(app.state, "grounded_service", None)
            if (
                retrieval is None
                or grounded is None
                or retrieval.closing
                or grounded.closing
                or grounded.retrieval is not retrieval
            ):
                raise RuntimeError("grounded_extract_requires_grounded_retrieval")
            yield

    app = FastAPI(
        title=base.title,
        version=base.version,
        description=base.description,
        docs_url=base.docs_url,
        redoc_url=base.redoc_url,
        lifespan=lifespan,
    )
    app.include_router(
        APIRouter(
            routes=[
                route
                for route in base.router.routes
                if getattr(route, "name", None) not in DOCS
            ]
        )
    )
    app.dependency_overrides.update(base.dependency_overrides)
    app.exception_handlers.update(base.exception_handlers)
    app.include_router(router, prefix="/api/v1")
    LOGGER.info("grounded_extract_composed")
    return app


def create_app():
    """Return the exact original main app unless the owner explicitly enables grounded extraction."""
    from apps.api.main import app as base

    value = os.environ.get("ASSISTANT_GROUNDED_EXTRACT_ENABLED", "0")
    if value == "0":
        LOGGER.info("grounded_extract_disabled")
        return base
    if value != "1":
        raise RuntimeError("grounded_extract_flag_invalid")
    if os.environ.get("ASSISTANT_VOICE_ENABLED", "0") != "0":
        raise RuntimeError("grounded_extract_voice_unsupported")
    if any(os.environ.get(name) != "1" for name in ENABLED) or not all(
        os.environ.get(name) for name in PRESENT
    ):
        raise RuntimeError("grounded_extract_prerequisites_required")
    return compose(base)
