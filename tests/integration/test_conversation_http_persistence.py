"""Check real PostgreSQL HTTP persistence across pool restart and opt-in model E2E."""

import asyncio
import logging
import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete

from apps.api.main import app
from src.application.ports.inference import CompletionResult
from src.infrastructure.database.connection import (
    create_database_engine,
    create_session_factory,
)
from src.infrastructure.models.conversation_model import ConversationModel
from src.infrastructure.models.inference_run_model import InferenceRunModel
from src.infrastructure.models.message_model import MessageModel

logger = logging.getLogger(__name__)


class RecordingInference:
    """Record multi-turn context while leaving persistence on real PostgreSQL."""

    def __init__(self):
        """Initialize inference call evidence for replay assertions."""
        self.contexts = []

    async def complete(self, *, messages, preset, **parameters):
        """Return a deterministic final answer without a model dependency."""
        self.contexts.append(messages)
        logger.info("integration_inference_called count=%d", len(self.contexts))
        return CompletionResult(
            content="PERSISTED-OK",
            model_id="qwen3.5-9b-core",
            preset_selected=preset,
            finish_reason="stop",
        )


async def cleanup_conversation(identifier):
    """Remove only this test's records in foreign-key order and release its pool."""
    engine = create_database_engine()
    try:
        async with create_session_factory(engine)() as session, session.begin():
            for model in (InferenceRunModel, MessageModel):
                await session.execute(
                    delete(model).where(model.conversation_id == identifier)
                )
            await session.execute(
                delete(ConversationModel).where(ConversationModel.id == identifier)
            )
        logger.info("integration_conversation_cleaned conversation_id=%s", identifier)
    finally:
        await engine.dispose()


@pytest.mark.parametrize(
    "live_model", [False, True], ids=["postgres-fake-inference", "postgres-live-model"]
)
def test_http_persistence_after_pool_restart(live_model):
    """Recreate API resources and prove history, replay and lifecycle through HTTP."""
    if not os.environ.get("DATABASE_URL"):
        pytest.skip(
            "DATABASE_URL not configured; real PostgreSQL acceptance not executed"
        )
    if live_model and os.environ.get("LOCAL_ASSISTANT_LIVE_E2E") != "1":
        pytest.skip(
            "Set LOCAL_ASSISTANT_LIVE_E2E=1 to explicitly invoke the running CORE model"
        )

    from uuid import UUID

    identifier = None
    inference = RecordingInference()
    body = {
        "content": "Reply with PERSISTED-OK.",
        "preset": "fast",
        "request_key": "first",
        "max_tokens": 512,
    }
    try:
        with TestClient(app, client=("127.0.0.1", 41000)) as client:
            if not live_model:
                app.state.conversation_service.manager.inference = inference
            created = client.post(
                "/api/v1/conversations",
                json={"title": "D15-T05 HTTP test", "preset_default": "fast"},
            )
            assert created.status_code == 201
            identifier = UUID(created.json()["id"])
            root = f"/api/v1/conversations/{identifier}"
            first = client.post(root + "/messages", json=body)
            assert first.status_code == 200
            assert first.json()["cached"] is False
            assert (
                client.post(
                    root + "/messages", json={**body, "content": "Different"}
                ).status_code
                == 409
            )
            second = client.post(
                root + "/messages",
                json={
                    **body,
                    "content": "Repeat the previous answer.",
                    "request_key": "second",
                },
            )
            assert second.status_code == 200
            if not live_model:
                assert len(inference.contexts) == 2
                assert [item["role"] for item in inference.contexts[1]] == [
                    "user",
                    "assistant",
                    "user",
                ]
            history = client.get(root + "/messages").json()
            assert [item["sequence"] for item in history] == [1, 2, 3, 4]
            assert "reasoning_content" not in str(history)
            assert client.patch(root, json={"title": "Updated"}).status_code == 200

        with TestClient(app, client=("127.0.0.1", 41001)) as client:
            if not live_model:
                app.state.conversation_service.manager.inference = inference
            assert client.get(root).json()["title"] == "Updated"
            assert client.get(root + "/messages").json() == history
            assert any(
                item["id"] == str(identifier)
                for item in client.get("/api/v1/conversations?limit=100").json()
            )
            replay = client.post(root + "/messages", json=body)
            assert replay.status_code == 200
            assert replay.json()["cached"] is True
            assert (
                replay.json()["assistant_message_id"]
                == first.json()["assistant_message_id"]
            )
            if not live_model:
                assert len(inference.contexts) == 2
            assert (
                len(client.get(root + "/messages?limit=2&after_sequence=2").json()) == 2
            )
            assert client.post(root + "/archive").status_code == 200
            assert client.get(root + "/messages").status_code == 200
            assert (
                client.post(
                    root + "/messages", json={**body, "request_key": "archived"}
                ).status_code
                == 404
            )
            assert client.delete(root).status_code == 204
            assert client.get(root).status_code == 404
            assert client.get(root + "/messages").status_code == 404
    finally:
        if identifier is not None:
            asyncio.run(cleanup_conversation(identifier))
