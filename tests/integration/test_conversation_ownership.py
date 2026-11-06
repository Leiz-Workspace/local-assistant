"""Prove two-principal HTTP and manager isolation against the existing PostgreSQL schema."""

import asyncio
import logging
import os
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from apps.api.main import app
from src.application.ports.inference import CompletionResult
from src.application.services.conversation_manager import (
    ConversationError,
    ConversationManager,
)
from src.infrastructure.database.connection import (
    create_database_engine,
    create_session_factory,
)
from src.infrastructure.models.conversation_model import ConversationModel
from src.infrastructure.models.inference_run_model import InferenceRunModel
from src.infrastructure.models.message_model import MessageModel
from src.infrastructure.repositories.conversation_repository import (
    PostgresConversationRepository,
)

logger = logging.getLogger(__name__)


class OwnerInference:
    """Count legitimate generations without granting any principal inference-based access."""

    def __init__(self):
        """Initialize the invocation count used to detect unauthorized generation."""
        self.calls = 0

    async def complete(self, **parameters):
        """Return one verified final answer for an authorized request."""
        self.calls += 1
        return CompletionResult(
            content="OWNER-OK",
            model_id="qwen3.5-9b-core",
            preset_selected="fast",
            finish_reason="stop",
        )


async def cleanup(ids):
    """Delete only records created by this ownership acceptance test."""
    engine = create_database_engine()
    try:
        async with create_session_factory(engine)() as session, session.begin():
            for model in (InferenceRunModel, MessageModel):
                await session.execute(
                    delete(model).where(model.conversation_id.in_(ids))
                )
            await session.execute(
                delete(ConversationModel).where(ConversationModel.id.in_(ids))
            )
        logger.info("ownership_acceptance_cleanup conversations=%d", len(ids))
    finally:
        await engine.dispose()


async def create_legacy():
    """Create an unowned legacy record through the trusted maintenance interface."""
    engine = create_database_engine()
    try:
        async with create_session_factory(engine)() as session, session.begin():
            return (
                await PostgresConversationRepository(session).create(
                    title="Unowned legacy"
                )
            ).id
    finally:
        await engine.dispose()


def test_http_owner_isolation(auth_settings):
    """Reject every cross-owner operation, guessed UUID and replay while preserving own access."""
    if not os.environ.get("DATABASE_URL"):
        pytest.skip("DATABASE_URL not configured")
    ids = []
    inference = OwnerInference()
    headers_a, headers_b = auth_settings["headers"]
    try:
        ids.append(asyncio.run(create_legacy()))
        with TestClient(app, client=("127.0.0.1", 43000)) as client:
            app.state.conversation_service.manager.inference = inference
            for headers in (headers_a, headers_b):
                response = client.post(
                    "/api/v1/conversations",
                    json={"preset_default": "fast"},
                    headers=headers,
                )
                assert response.status_code == 201
                ids.append(UUID(response.json()["id"]))
            root = "/api/v1/conversations/" + str(ids[1])
            assert client.get("/api/v1/conversations").status_code == 401
            assert client.get("/api/v1/conversations", headers=headers_b).json()[0][
                "id"
            ] == str(ids[2])
            assert (
                len(client.get("/api/v1/conversations", headers=headers_b).json()) == 1
            )
            for method, suffix, body in [
                ("GET", "", None),
                ("GET", "/messages", None),
                ("PATCH", "", {"title": "Unauthorized"}),
                (
                    "POST",
                    "/messages",
                    {"content": "Secret?", "request_key": "shared-key"},
                ),
                ("POST", "/archive", None),
                ("DELETE", "", None),
            ]:
                assert (
                    client.request(
                        method, root + suffix, json=body, headers=headers_b
                    ).status_code
                    == 404
                )
            assert inference.calls == 0
            for headers in (headers_a, headers_b):
                assert (
                    client.get(
                        "/api/v1/conversations/" + str(ids[0]), headers=headers
                    ).status_code
                    == 404
                )
            payload = {
                "content": "Hello",
                "preset": "fast",
                "request_key": "shared-key",
                "max_tokens": 512,
            }
            response = client.post(root + "/messages", json=payload, headers=headers_a)
            assert response.status_code == 200
            assert response.json()["cached"] is False
            assert (
                client.post(root + "/messages", json=payload, headers=headers_a).json()[
                    "cached"
                ]
                is True
            )
            assert (
                client.post(
                    root + "/messages",
                    json=payload,
                    headers={
                        **headers_b,
                        "X-User-ID": str(auth_settings["principals"][0]),
                    },
                ).status_code
                == 404
            )
            assert inference.calls == 1
            assert (
                client.patch(
                    root,
                    json={"owner_id": str(auth_settings["principals"][1])},
                    headers=headers_a,
                ).status_code
                == 422
            )
            assert len(client.get(root + "/messages", headers=headers_a).json()) == 2
            assert client.post(root + "/archive", headers=headers_a).status_code == 200
            assert client.get(root, headers=headers_b).status_code == 404
            assert client.delete(root, headers=headers_a).status_code == 204
            assert client.get(root, headers=headers_a).status_code == 404
    finally:
        if ids:
            asyncio.run(cleanup(ids))


@pytest.mark.asyncio
async def test_manager_fences_cross_owner_reservation(auth_settings):
    """Enforce ownership at the row lock even if a caller bypasses the HTTP service read."""
    if not os.environ.get("DATABASE_URL"):
        pytest.skip("DATABASE_URL not configured")
    engine = create_database_engine()
    factory = create_session_factory(engine)
    identifier = None
    try:
        async with factory() as session, session.begin():
            identifier = (
                await PostgresConversationRepository(session).create(
                    owner_id=auth_settings["principals"][0]
                )
            ).id
        inference = OwnerInference()
        manager = ConversationManager(
            session_factory=factory,
            inference=inference,
            principal_id=auth_settings["principals"][1],
        )
        with pytest.raises(ConversationError) as error:
            await manager.send_message(
                conversation_id=identifier,
                content="Guess",
                profile="core",
                preset="fast",
                model_id="qwen3.5-9b-core",
            )
        assert error.value.status_code == 404 and inference.calls == 0
        async with factory() as session:
            assert (
                await session.scalar(
                    select(MessageModel.id).where(
                        MessageModel.conversation_id == identifier
                    )
                )
                is None
            )
    finally:
        if identifier is not None:
            await cleanup([identifier])
        await engine.dispose()
