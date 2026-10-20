"""Own optional conversation, source, retrieval, grounded and memory resources with ordered joined shutdown."""

import asyncio
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI

from apps.api.services.conversations import ConversationService
from apps.api.storage.files import initialize_file_service
from apps.api.storage.grounded import initialize_grounded_service
from apps.api.storage.ingestion import initialize_ingestion_service
from apps.api.storage.memory import initialize_memory_service
from apps.api.storage.retrieval import initialize_retrieval_service
from apps.api.storage.workspace_diagnoses import initialize_workspace_diagnoses
from apps.api.storage.workspace_explanations import initialize_workspace_explanations
from apps.api.storage.workspaces import initialize_workspace_service
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
    app.state.file_service = None
    app.state.ingestion_service = None
    app.state.retrieval_service = None
    app.state.grounded_service = None
    app.state.memory_service = None
    app.state.workspace_service = None
    app.state.workspace_explanation_service = None
    app.state.workspace_diagnosis_service = None
    try:
        app.state.workspace_service = await initialize_workspace_service()
        app.state.workspace_explanation_service = (
            await initialize_workspace_explanations(app.state.workspace_service)
        )
        app.state.workspace_diagnosis_service = await initialize_workspace_diagnoses(
            app.state.workspace_service
        )
        if os.environ.get("DATABASE_URL"):
            try:
                engine = create_database_engine()
                app.state.conversation_service = ConversationService(
                    create_session_factory(engine)
                )
                app.state.file_service = await initialize_file_service(
                    create_session_factory(engine)
                )
                app.state.ingestion_service = await initialize_ingestion_service(
                    app.state.file_service
                )
                app.state.retrieval_service = await initialize_retrieval_service(
                    app.state.ingestion_service
                )
                app.state.grounded_service = await initialize_grounded_service(
                    app.state.retrieval_service
                )
                app.state.memory_service = await initialize_memory_service(
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
        if app.state.workspace_diagnosis_service is not None:
            await app.state.workspace_diagnosis_service.shutdown()
            app.state.workspace_diagnosis_service = None
        if app.state.workspace_explanation_service is not None:
            await app.state.workspace_explanation_service.shutdown()
            app.state.workspace_explanation_service = None
        if app.state.workspace_service is not None:
            await app.state.workspace_service.shutdown()
            app.state.workspace_service = None
        if app.state.memory_service is not None:
            await app.state.memory_service.shutdown()
            app.state.memory_service = None
        if app.state.grounded_service is not None:
            await app.state.grounded_service.shutdown()
            app.state.grounded_service = None
        if app.state.retrieval_service is not None:
            await app.state.retrieval_service.shutdown()
            app.state.retrieval_service = None
        if app.state.ingestion_service is not None:
            await app.state.ingestion_service.shutdown()
            app.state.ingestion_service = None
        if app.state.file_service is not None:
            await app.state.file_service.shutdown()
            app.state.file_service = None
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
