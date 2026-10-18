"""
Local Assistant — FastAPI Entry Point.

Responsibilities:
    - Initialize the FastAPI application.
    - Register API routers.
    - Own optional conversation storage resources through application lifespan.
    - Expose OpenAPI documentation.

Runtime presets are handled by the chat router
and the model gateway, not directly in main.py.
"""

import logging

from fastapi import FastAPI

from apps.api.core.logging_config import configure_application_logging
from apps.api.routes.chat import router as chat_router
from apps.api.routes.conversations import router as conversation_router
from apps.api.routes.health import router as health_router
from apps.api.storage.lifecycle import conversation_lifespan

configure_application_logging()

app = FastAPI(
    lifespan=conversation_lifespan,
    title="Local Assistant",
    version="0.1.0",
    description="Local-first Personal AI Backend",
    docs_url="/docs",
    redoc_url=None,
)

app.include_router(
    health_router,
    prefix="/api/v1",
)

app.include_router(
    chat_router,
    prefix="/api/v1",
)

app.include_router(conversation_router, prefix="/api/v1")
logging.getLogger(__name__).info("api_routers_registered")
