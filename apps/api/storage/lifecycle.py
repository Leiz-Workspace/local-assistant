"""Own optional persistent-chat database resources for each FastAPI process."""

import asyncio
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI

from apps.api.services.conversations import ConversationService
from src.infrastructure.database.connection import (
    create_database_engine,
    create_session_factory,
)
from src.infrastructure.database.pool_telemetry import PoolTelemetry

logger = logging.getLogger(__name__)


@asynccontextmanager
async def conversation_lifespan(app: FastAPI):
    """Create one pool per process and dispose it without logging credentials."""
    engine = None
    telemetry = None
    sampler = None
    app.state.pool_telemetry = None
    app.state.conversation_service = None
    try:
        if os.environ.get("DATABASE_URL"):
            try:
                engine = create_database_engine()
                app.state.conversation_service = ConversationService(
                    create_session_factory(engine)
                )
                telemetry = PoolTelemetry(engine)
                app.state.pool_telemetry = telemetry
                sampler = asyncio.create_task(telemetry.sample())
                logger.info("conversation_storage_initialized")
            except Exception:
                logger.error("conversation_storage_initialization_failed")
                raise RuntimeError(
                    "Conversation storage initialization failed; verify runtime configuration."
                ) from None
        else:
            logger.warning("conversation_storage_disabled reason=missing_database_url")
        yield
    finally:
        app.state.conversation_service = None
        if sampler is not None:
            sampler.cancel()
            await asyncio.gather(sampler, return_exceptions=True)
        if telemetry is not None:
            telemetry.close()
        app.state.pool_telemetry = None
        if engine is not None:
            await engine.dispose()
            logger.info("conversation_storage_disposed")
