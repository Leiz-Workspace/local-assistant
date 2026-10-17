"""Own optional persistent-chat database resources for each FastAPI process."""

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI

from apps.api.services.conversations import ConversationService
from src.infrastructure.database.connection import (
    create_database_engine,
    create_session_factory,
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def conversation_lifespan(app: FastAPI):
    """Create one pool per process and dispose it without logging credentials."""
    engine = None
    app.state.conversation_service = None
    try:
        if os.environ.get("DATABASE_URL"):
            try:
                engine = create_database_engine()
                app.state.conversation_service = ConversationService(
                    create_session_factory(engine)
                )
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
        if engine is not None:
            await engine.dispose()
            logger.info("conversation_storage_disposed")
