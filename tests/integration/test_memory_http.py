"""Verify real authenticated V005 memory management HTTP/TCP, two-owner privacy and transaction cancellation."""

import asyncio
import hashlib
import json
import logging
import os
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from test_memory_journal_postgres import memory_context as memory_context
from test_reranker_tcp_trial import localhost_server

from apps.api.main import app
from apps.api.services.memory import MemoryService
from src.infrastructure.database.connection import (
    create_database_engine,
    create_session_factory,
)

logger = logging.getLogger(__name__)


async def cleanup(owners):
    """Remove only fixture-owned memory/conversation rows after the API pool has joined and closed."""
    engine = create_database_engine()
    try:
        async with create_session_factory(engine)() as session, session.begin():
            for table in ("memories", "memory_consents", "memory_settings"):
                await session.execute(
                    text(
                        "DELETE FROM assistant."
                        + table
                        + " WHERE owner_id=ANY(:owners)"
                    ),
                    dict(owners=owners),
                )
            await session.execute(
                text(
                    "DELETE FROM assistant.conversations WHERE metadata->>'owner_id'=ANY(:owners)"
                ),
                dict(owners=[str(owner) for owner in owners]),
            )
    finally:
        await engine.dispose()
        logger.info("memory_http_owned_probes_cleaned")


@pytest.fixture
def memory_client(auth_settings, monkeypatch):
    """Enable only memory management in a real app lifecycle using the existing runtime database credential."""
    if not os.environ.get("DATABASE_URL"):
        pytest.skip("existing app DATABASE_URL required")
    monkeypatch.setenv("ASSISTANT_MEMORY_ENABLED", "1")
    for flag in (
        "ASSISTANT_FILES_ENABLED",
        "ASSISTANT_INGESTION_ENABLED",
        "ASSISTANT_RETRIEVAL_ENABLED",
        "ASSISTANT_GROUNDED_ENABLED",
    ):
        monkeypatch.setenv(flag, "0")
    try:
        with TestClient(app, client=("127.0.0.1", 43000)) as client:
            yield client, auth_settings
            assert not client.app.state.memory_service.operations
    finally:
        asyncio.run(cleanup(auth_settings["principals"]))


def enable_and_grant(client, headers, *, kind="preference"):
    """Explicitly enable one fixture principal and create a current bounded class receipt through HTTP."""
    response = client.put(
        "/api/v1/memory/settings",
        headers=headers,
        json=dict(expected_revision=0, enabled=True, extraction_enabled=False),
    )
    assert response.status_code == 200, response.text
    body = dict(kind=kind, expected_revision=1)
    if kind == "session":
        conversation = client.post(
            "/api/v1/conversations",
            headers=headers,
            json=dict(title="Memory scope", profile="core", preset_default="fast"),
        )
        assert conversation.status_code == 201, conversation.text
        body["scope_id"] = conversation.json()["id"]
    elif kind == "project":
        body["scope_id"] = str(uuid4())
    response = client.post("/api/v1/memory/consents", headers=headers, json=body)
    assert response.status_code == 201, response.text
    return response.json()


@pytest.mark.parametrize("kind", ["session", "episodic", "preference", "project"])
def test_actual_four_class_http_controls_and_disabled_inspection(memory_client, kind):
    """Run actual manual HTTP CRUD, version fencing and owner-disabled inspection/deletion without inference."""
    client, auth = memory_client
    headers = auth["headers"][0]
    settings = client.get("/api/v1/memory/settings", headers=headers)
    assert settings.status_code == 200 and settings.json()["revision"] == 0
    assert settings.json()["enabled"] is False
    assert (
        client.post(
            "/api/v1/memory/consents",
            headers=headers,
            json=dict(kind="preference", expected_revision=1),
        ).status_code
        == 403
    )
    receipt = enable_and_grant(client, headers, kind=kind)
    value = "Tôi thích a\u0301 và 𝄞."
    response = client.post(
        "/api/v1/memory/records",
        headers=headers,
        json=dict(consent_id=receipt["id"], text=value),
    )
    assert response.status_code == 201, response.text
    record = response.json()
    identifier = record["id"]
    assert record["kind"] == kind and record["content_trust"] == "untrusted"
    assert (
        record["provenance"]["content_sha256"]
        == hashlib.sha256(value.encode()).hexdigest()
    )
    assert response.headers["cache-control"] == "private, no-store"
    listed = client.get("/api/v1/memory/records", headers=headers).json()["records"]
    assert [item["id"] for item in listed] == [identifier] and "text" not in listed[0]
    response = client.patch(
        "/api/v1/memory/records/" + identifier,
        headers=headers,
        json=dict(expected_version=1, text="Edited literal."),
    )
    assert response.status_code == 200 and response.json()["version"] == 2
    assert (
        client.patch(
            "/api/v1/memory/records/" + identifier,
            headers=headers,
            json=dict(expected_version=1, text="stale"),
        ).status_code
        == 409
    )
    assert (
        client.put(
            "/api/v1/memory/settings",
            headers=headers,
            json=dict(expected_revision=1, enabled=False),
        ).status_code
        == 200
    )
    assert (
        client.get("/api/v1/memory/records/" + identifier, headers=headers).json()[
            "text"
        ]
        == "Edited literal."
    )
    assert (
        client.post(
            "/api/v1/memory/records",
            headers=headers,
            json=dict(consent_id=receipt["id"], text="disabled"),
        ).status_code
        == 403
    )
    assert (
        client.delete(
            "/api/v1/memory/records/" + identifier,
            headers=headers,
            params=dict(expected_version=2),
        ).status_code
        == 204
    )
    assert (
        client.get("/api/v1/memory/records/" + identifier, headers=headers).status_code
        == 404
    )


def test_actual_two_principal_http_receipt_record_and_scope_isolation(memory_client):
    """Hide every foreign ID and preserve independent owner settings instead of adopting another owner's record."""
    client, auth = memory_client
    own, foreign = auth["headers"]
    receipt = enable_and_grant(client, own)
    record = client.post(
        "/api/v1/memory/records",
        headers=own,
        json=dict(consent_id=receipt["id"], text="Owner-private fact."),
    ).json()
    enable_and_grant(client, foreign)
    path = "/api/v1/memory/records/" + record["id"]
    assert client.get(path, headers=foreign).status_code == 404
    assert (
        client.patch(
            path, headers=foreign, json=dict(expected_version=1, text="foreign")
        ).status_code
        == 404
    )
    assert (
        client.delete(
            path, headers=foreign, params=dict(expected_version=1)
        ).status_code
        == 404
    )
    assert (
        client.delete(
            "/api/v1/memory/consents/" + receipt["id"], headers=foreign
        ).status_code
        == 404
    )
    assert (
        client.post(
            "/api/v1/memory/records",
            headers=foreign,
            json=dict(consent_id=receipt["id"], text="foreign"),
        ).status_code
        == 404
    )
    assert client.get("/api/v1/memory/records", headers=foreign).json()["records"] == []
    assert client.get(path, headers=own).json()["text"] == "Owner-private fact."


def test_actual_revoke_and_reenable_do_not_restore_old_consent(memory_client):
    """Deny revoked/stale receipt capture while preserving explicit management controls and new grants."""
    client, auth = memory_client
    headers = auth["headers"][0]
    receipt = enable_and_grant(client, headers)
    path = "/api/v1/memory/consents/" + receipt["id"]
    first = client.delete(path, headers=headers)
    second = client.delete(path, headers=headers)
    assert (
        first.status_code == second.status_code == 200
        and first.json()["revoked_at"] == second.json()["revoked_at"]
    )
    assert (
        client.post(
            "/api/v1/memory/records",
            headers=headers,
            json=dict(consent_id=receipt["id"], text="revoked"),
        ).status_code
        == 409
    )
    for revision, enabled in ((1, False), (2, True)):
        assert (
            client.put(
                "/api/v1/memory/settings",
                headers=headers,
                json=dict(expected_revision=revision, enabled=enabled),
            ).status_code
            == 200
        )
    assert (
        client.post(
            "/api/v1/memory/consents",
            headers=headers,
            json=dict(kind="preference", expected_revision=1),
        ).status_code
        == 409
    )
    assert (
        client.post(
            "/api/v1/memory/consents",
            headers=headers,
            json=dict(kind="preference", expected_revision=3),
        ).status_code
        == 201
    )


@pytest.mark.parametrize("fault", ["bytes", "nul", "owner", "provenance"])
def test_actual_invalid_manual_capture_is_private_and_atomic(memory_client, fault):
    """Reject private content/schema violations without leaving a record or changing server-derived ownership."""
    client, auth = memory_client
    headers = auth["headers"][0]
    receipt = enable_and_grant(client, headers)
    body = dict(consent_id=receipt["id"], text="manual")
    if fault == "bytes":
        body["text"] = "ệ" * 1366
    elif fault == "nul":
        body["text"] = "x\0y"
    elif fault == "owner":
        body["owner_id"] = str(auth["principals"][1])
    else:
        body["provenance"] = {}
    response = client.post("/api/v1/memory/records", headers=headers, json=body)
    assert response.status_code == 422
    assert response.headers["cache-control"] == "private, no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.json()["detail"]["code"] in {
        "memory_input_invalid",
        "memory_record_invalid",
    }
    assert client.get("/api/v1/memory/records", headers=headers).json()["records"] == []


@pytest.mark.asyncio
async def test_actual_sql_cancel_rolls_back_before_shutdown(
    memory_context, monkeypatch
):
    """Cancel a real sleeping PostgreSQL operation and join rollback before the service/pool closes."""
    context = memory_context
    journal = context["journal"]
    owner = context["owners"][0]
    service = MemoryService(journal)
    entered = asyncio.Event()
    backend = []
    original = journal._now

    async def blocked(session):
        """Hold an actual database statement inside the configure transaction until cancellation."""
        backend.append(await session.scalar(text("SELECT pg_backend_pid()")))
        entered.set()
        await session.execute(text("SELECT pg_sleep(30)"))
        return await original(session)

    monkeypatch.setattr(journal, "_now", blocked)
    work = asyncio.create_task(
        service.run(
            owner,
            "configure",
            expected_revision=0,
            enabled=True,
            extraction_enabled=False,
        )
    )
    await asyncio.wait_for(entered.wait(), 5)

    async def require_actual_sleep():
        """Observe the owned backend in PostgreSQL PgSleep before requesting cancellation."""
        while True:
            async with context["sessions"]() as session:
                waiting = await session.scalar(
                    text("SELECT wait_event FROM pg_stat_activity WHERE pid=:pid"),
                    dict(pid=backend[0]),
                )
            if waiting == "PgSleep":
                return
            await asyncio.sleep(0.01)

    await asyncio.wait_for(require_actual_sleep(), 5)
    await asyncio.wait_for(service.shutdown(), 5)
    with pytest.raises(asyncio.CancelledError):
        await work
    assert not service.operations and (await journal.settings(owner))["revision"] == 0
    assert context["sessions"].kw["bind"].pool.checkedout() == 0


def test_actual_loopback_tcp_management_and_joined_resources(memory_client):
    """Deliver authenticated manual memory controls over real loopback Uvicorn without a model call."""
    client, auth = memory_client
    headers = auth["headers"][0]
    with (
        localhost_server(client) as base_url,
        httpx.Client(
            base_url=base_url, trust_env=False, timeout=10, follow_redirects=False
        ) as wire,
    ):
        response = wire.get("/api/v1/memory/settings", headers=headers)
        assert response.status_code == 200 and response.json()["enabled"] is False
        assert wire.get("/api/v1/memory/settings").status_code == 401
        assert (
            wire.get(
                "/api/v1/memory/settings",
                headers={**headers, "Origin": "http://foreign.invalid"},
            ).status_code
            == 403
        )
        assert (
            wire.put(
                "/api/v1/memory/settings",
                headers=headers,
                json=dict(expected_revision=0, enabled=True),
            ).status_code
            == 200
        )
        receipt = wire.post(
            "/api/v1/memory/consents",
            headers=headers,
            json=dict(kind="preference", expected_revision=1),
        )
        assert receipt.status_code == 201
        result = wire.post(
            "/api/v1/memory/records",
            headers=headers,
            json=dict(
                consent_id=receipt.json()["id"], text="TCP-owned manual preference."
            ),
        )
        assert (
            result.status_code == 201
            and result.headers["cache-control"] == "private, no-store"
        )
        assert result.json()["method"] == "manual" and result.json()["model_id"] is None
    assert not client.app.state.memory_service.operations
    report = dict(
        description="Actual V005/runtime app owner-memory manual management over ephemeral loopback Uvicorn/TCP; no inference or production enablement.",
        actual_tcp=True,
        manual_record=result.json(),
        temporary_server_joined=True,
        owned_operations_joined=True,
        independent_human_or_model_quality_claim=False,
    )
    path = Path("data/backups/d30-t02-memory-tcp.json")
    path.touch(mode=0o600, exist_ok=True)
    path.chmod(0o600)
    path.write_text(json.dumps(report, indent=2) + "\n")
    logger.info("memory_management_tcp_verified")
