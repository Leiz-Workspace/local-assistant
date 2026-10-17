"""
Local Assistant — FastAPI Entry Point.

Responsibilities:
    - Initialize the FastAPI application.
    - Register API routers.
    - Expose OpenAPI documentation.

Runtime presets are handled by the chat router
and the model gateway, not directly in main.py.
"""

from fastapi import FastAPI

from apps.api.routes.health import router as health_router
from apps.api.routes.chat import router as chat_router


app = FastAPI(
    title="Local Assistant",
    version="0.1.0",
    description="Local-first Personal AI Backend",
    docs_url="/docs",
    redoc_url=None,
)

# Health endpoints.
app.include_router(
    health_router,
    prefix="/api/v1",
)

# Chat endpoints, including runtime presets.
app.include_router(
    chat_router,
    prefix="/api/v1",
)
