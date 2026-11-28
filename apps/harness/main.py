"""Compose the explicitly enabled product harness and pinned UI without modifying the default API."""

import logging
import os
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI, Request, HTTPException
from fastapi.exception_handlers import http_exception_handler
from fastapi.responses import JSONResponse

from apps.harness.inference import ProductInference
from apps.harness.generation import GenerationJobs
from apps.harness.routes import router, skill_error_reply
from apps.harness.service import HarnessError, ProductHarness
from src.application.services.skill_contract import SkillError
from src.application.services.context_reduction import ContextError
from src.infrastructure.harness_history import HarnessHistoryStore

LOGGER = logging.getLogger(__name__)
DOCS = frozenset({"openapi", "swagger_ui_html", "swagger_ui_redirect", "redoc_html"})


def compose(base, *, inference=None, asset_root=None, history_dir=None):
    """Own an opt-in coordinator and browser boundary around the unchanged base lifespan and routes."""
    from apps.harness.browser import register_browser

    @asynccontextmanager
    async def lifespan(app):
        """Close product tasks before the original workspace and database resources are released."""
        async with base.router.lifespan_context(app):
            history = (
                HarnessHistoryStore(history_dir) if history_dir is not None else None
            )
            product, jobs = None, None
            try:
                product = ProductHarness(
                    inference or ProductInference(),
                    getattr(app.state, "workspace_service", None),
                    history=history,
                )
                app.state.product_harness = product
                jobs = GenerationJobs(product.admission)
                app.state.generation_jobs = jobs
                yield
            finally:
                try:
                    if jobs is not None:
                        await jobs.close()
                    if product is not None:
                        await product.close()
                finally:
                    if history is not None:
                        history.close()

    app = FastAPI(
        title="Aevra",
        version="0.1.0",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
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
    app.include_router(router)

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, error):
        """Keep existing API errors and expose readable OpenAI-shaped errors for the upstream UI."""
        if request.url.path.startswith("/api/"):
            return await http_exception_handler(request, error)
        code = (
            error.detail.get("code", "request_denied")
            if isinstance(error.detail, dict)
            else "request_denied"
        )
        LOGGER.warning("product_browser_request_denied code=%s", code)
        return JSONResponse(
            {"error": {"message": code, "code": code, "type": "invalid_request_error"}},
            status_code=error.status_code,
        )

    if asset_root is None:
        register_browser(app)
    else:
        register_browser(app, asset_root=asset_root)

    @app.exception_handler(ContextError)
    @app.exception_handler(HarnessError)
    async def harness_error(request: Request, error):
        """Return finite safe operation errors without exposing inputs or internal exception strings."""
        LOGGER.warning("product_operation_denied code=%s", error.code)
        return JSONResponse({"detail": {"code": error.code}}, status_code=error.status)

    @app.exception_handler(SkillError)
    async def skill_error(request: Request, error):
        """Map skill registry rejections to bounded codes; a missing or expired review asks for a new review."""
        LOGGER.warning("product_skill_operation_denied code=%s", error.code)
        code, status = skill_error_reply(error)
        return JSONResponse({"detail": {"code": code}}, status_code=status)

    LOGGER.info("product_harness_composed")
    return app


def create_app():
    """Keep the exact default application unless an explicit product entrypoint flag is enabled."""
    from apps.api.main import app as base

    value = os.environ.get("ASSISTANT_HARNESS_ENABLED", "0")
    if value == "0":
        return base
    if value != "1" or not os.environ.get("ASSISTANT_AUTH_FILE"):
        raise RuntimeError("harness_requires_explicit_flag_and_auth_file")
    return compose(base, history_dir=os.environ.get("ASSISTANT_HARNESS_STATE_DIR"))
