"""Verify default-off retrieval, strict authenticated request shape and delivery-lifetime cleanup."""

from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from apps.api.main import app
from apps.api.routes.retrieval import RetrievalResponse, SearchInput
from apps.api.storage.retrieval import initialize_retrieval_service
from src.application.services.file_storage_policy import StoragePolicyError


@pytest.mark.asyncio
async def test_retrieval_default_off_has_no_resource_dependency(monkeypatch):
    """Keep default startup free of collection/model/database work even when ingestion is absent."""
    monkeypatch.delenv("ASSISTANT_RETRIEVAL_ENABLED", raising=False)
    assert await initialize_retrieval_service(None) is None
    monkeypatch.setenv("ASSISTANT_RETRIEVAL_ENABLED", "1")
    with pytest.raises(RuntimeError):
        await initialize_retrieval_service(None)


def test_strict_search_shape_and_uuid_json():
    """Accept UUID JSON narrowing while rejecting arbitrary caller ACL fields or coercible limits."""
    identifier = uuid4()
    assert SearchInput.model_validate_json(
        '{"query":"q","file_ids":["' + str(identifier) + '"]}'
    ).file_ids == [identifier]
    assert SearchInput.model_validate(
        dict(query="q", file_ids=[str(identifier)])
    ).file_ids == [identifier]
    for data in [
        dict(query="q", owner_id=str(identifier)),
        dict(query="q", filter={}),
        dict(query="q", top_k=True),
        dict(query="q", top_k="2"),
    ]:
        with pytest.raises(ValueError):
            SearchInput.model_validate(data)


def test_default_off_auth_and_origin(auth_settings, monkeypatch):
    """Require real principal/local Origin rules and report disabled retrieval only to authenticated callers."""
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with TestClient(app, client=("127.0.0.1", 12345)) as client:
        assert (
            client.post("/api/v1/retrieval/search", json=dict(query="q")).status_code
            == 401
        )
        headers = auth_settings["headers"][0]
        assert (
            client.post(
                "/api/v1/retrieval/search", headers=headers, json=dict(query="q")
            ).status_code
            == 503
        )
        assert (
            client.post(
                "/api/v1/retrieval/search",
                headers=dict(headers, Origin="https://foreign.invalid"),
                json=dict(query="q"),
            ).status_code
            == 403
        )


@pytest.mark.parametrize("failure", ["fence", "send", "cancel", "success"])
@pytest.mark.asyncio
async def test_response_retains_and_always_closes_context(failure):
    """Recheck before headers and release the source context on failed, cancelled or complete delivery."""
    import asyncio

    events = []

    class Context:
        """Record release of the source-owning operation after response send attempts."""

        async def __aexit__(self, *args):
            """Mark resource release without modifying test exceptions."""
            events.append("closed")

    async def validate(owner, retained):
        """Fence invalid generations before a single private response header is sent."""
        events.append("validated")
        if failure == "fence":
            raise StoragePolicyError("retrieval_source_changed", 409)

    async def send(message):
        """Inspect response ordering and inject transport interruption only after authorization."""
        assert events[0] == "validated" and "closed" not in events
        events.append(message)
        if failure == "send":
            raise OSError("transport")
        if failure == "cancel":
            raise asyncio.CancelledError()

    response = RetrievalResponse(
        Context(),
        SimpleNamespace(validate=validate),
        uuid4(),
        dict(hits=["private-marker"]),
        [],
    )
    if failure in {"send", "cancel"}:
        with pytest.raises((OSError, asyncio.CancelledError)):
            await response({"type": "http"}, None, send)
    else:
        await response({"type": "http"}, None, send)
    assert events[-1] == "closed"
    if failure == "fence":
        assert events[1]["status"] == 409
        assert b"private-marker" not in events[2]["body"]


@pytest.mark.asyncio
async def test_enabled_missing_collection_and_owned_startup(monkeypatch):
    """Validate an existing owned collection without ensuring or mutating its schema at retrieval startup."""
    monkeypatch.setenv("ASSISTANT_RETRIEVAL_ENABLED", "1")

    async def absent():
        """Represent a missing collection without performing a remote operation."""
        return None

    with pytest.raises(RuntimeError):
        await initialize_retrieval_service(
            SimpleNamespace(closing=False, vectors=SimpleNamespace(owned=absent))
        )
    from apps.api.storage import retrieval

    marker = object()

    async def owned():
        """Acknowledge existing ownership without invoking collection creation."""
        return {}

    def construct(ingestion):
        """Record construction only after verified existing collection ownership."""
        return marker

    monkeypatch.setattr(retrieval, "RetrievalService", construct)
    assert (
        await initialize_retrieval_service(
            SimpleNamespace(closing=False, vectors=SimpleNamespace(owned=owned))
        )
        is marker
    )
