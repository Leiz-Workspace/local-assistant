"""Audit actual source deletion/edit propagation into retained memory/export using declared controlled inference."""

import logging
from uuid import UUID

import pytest
from sqlalchemy import text
from test_memory_extraction_live import ControlledCore, http_receipt, http_source
from test_memory_http import memory_client as memory_client

logger = logging.getLogger(__name__)


def captured_source(client, headers):
    """Persist an actual owned source and capture a literal fixture quote without claiming real model quality."""
    receipt = http_receipt(client, headers)
    identity = http_source(client, headers, "Private source fact Cedar port 7443.")
    client.app.state.memory_service.extractor.inference = ControlledCore(blocking=False)
    response = client.post(
        "/api/v1/memory/extractions",
        headers=headers,
        json=dict(consent_id=receipt["id"], **identity),
    )
    assert response.status_code == 200, response.text
    return receipt, identity, response.json()["record"]


@pytest.mark.parametrize("disabled", [False, True])
@pytest.mark.parametrize(
    "change", ["conversation_delete", "message_edit", "message_delete"]
)
def test_source_change_removes_derived_memory_from_owner_export(
    memory_client, change, disabled
):
    """Require source mutation and dependent-memory removal to commit together rather than exporting stale private facts."""
    client, auth = memory_client
    headers = auth["headers"][0]
    receipt, identity, record = captured_source(client, headers)
    manual = client.post(
        "/api/v1/memory/records",
        headers=headers,
        json=dict(consent_id=receipt["id"], text="Independent manual preference"),
    )
    assert manual.status_code == 201
    if disabled:
        assert (
            client.put(
                "/api/v1/memory/settings",
                headers=headers,
                json=dict(expected_revision=1, enabled=False, extraction_enabled=False),
            ).status_code
            == 200
        )
    if change == "conversation_delete":
        response = client.delete(
            "/api/v1/conversations/" + identity["conversation_id"], headers=headers
        )
        assert response.status_code == 204, response.text
    else:

        async def mutate_source():
            """Mutate only the exact random probe message on the actual app pool and event loop."""
            async with (
                client.app.state.conversation_service.session_factory() as session,
                session.begin(),
            ):
                statement = (
                    "UPDATE assistant.messages SET content='corrected private source' WHERE id=:id"
                    if change == "message_edit"
                    else "DELETE FROM assistant.messages WHERE id=:id"
                )
                await session.execute(
                    text(statement), dict(id=UUID(identity["message_id"]))
                )

        client.portal.call(mutate_source)
    response = client.get("/api/v1/memory/export", headers=headers)
    assert response.status_code == 200
    ids = [row["id"] for row in response.json()["records"]]
    assert record["id"] not in ids and manual.json()["id"] in ids
    assert (
        client.get(
            "/api/v1/memory/records/" + record["id"], headers=headers
        ).status_code
        == 404
    )
    assert record["text"] not in response.text
    logger.info("memory_actual_source_privacy_verified change=%s", change)


def test_actual_foreign_source_and_manual_session_boundaries(memory_client):
    """Remove deleted conversation derivations/session scope while retaining another principal and manual preference."""
    client, auth = memory_client
    headers, foreign = auth["headers"]
    receipt, identity, record = captured_source(client, headers)
    other_receipt, other_identity, other_record = captured_source(client, foreign)
    manual = client.post(
        "/api/v1/memory/records",
        headers=headers,
        json=dict(consent_id=receipt["id"], text="Independent manual preference"),
    )
    session = client.post(
        "/api/v1/memory/consents",
        headers=headers,
        json=dict(
            kind="session",
            scope_id=identity["conversation_id"],
            expected_revision=1,
            seconds=300,
        ),
    )
    assert session.status_code == 201
    scoped = client.post(
        "/api/v1/memory/records",
        headers=headers,
        json=dict(consent_id=session.json()["id"], text="Session-only private fact"),
    )
    assert scoped.status_code == 201 and manual.status_code == 201
    assert (
        client.delete(
            "/api/v1/conversations/" + identity["conversation_id"], headers=foreign
        ).status_code
        == 404
    )
    assert (
        client.get(
            "/api/v1/memory/records/" + record["id"], headers=headers
        ).status_code
        == 200
    )
    assert (
        client.delete(
            "/api/v1/conversations/" + identity["conversation_id"], headers=headers
        ).status_code
        == 204
    )
    exported = client.get("/api/v1/memory/export", headers=headers).json()
    assert [row["id"] for row in exported["records"]] == [manual.json()["id"]]
    assert session.json()["id"] not in [row["id"] for row in exported["consents"]]
    assert (
        client.get(
            "/api/v1/memory/records/" + other_record["id"], headers=foreign
        ).status_code
        == 200
    )
    logger.info("memory_actual_foreign_manual_session_boundaries_verified")


def test_actual_source_transaction_rollback_restores_memory(memory_client):
    """Keep the source and extracted memory together when a real app-role source transaction rolls back."""
    client, auth = memory_client
    headers = auth["headers"][0]
    receipt, identity, record = captured_source(client, headers)

    async def rollback_source():
        """Observe the actual trigger deletion inside the transaction and then deliberately abort the owned probe."""
        async with (
            client.app.state.conversation_service.session_factory() as session,
            session.begin(),
        ):
            await session.execute(
                text(
                    "UPDATE assistant.messages SET content='uncommitted change' WHERE id=:id"
                ),
                dict(id=UUID(identity["message_id"])),
            )
            assert (
                await session.scalar(
                    text("SELECT count(*) FROM assistant.memories WHERE id=:id"),
                    dict(id=UUID(record["id"])),
                )
                == 0
            )
            raise RuntimeError("owned source rollback probe")

    with pytest.raises(RuntimeError, match="owned source rollback probe"):
        client.portal.call(rollback_source)
    assert (
        client.get("/api/v1/memory/records/" + record["id"], headers=headers).json()
        == record
    )
    assert client.get("/api/v1/memory/export", headers=headers).json()["records"] == [
        record
    ]
    logger.info("memory_actual_source_rollback_verified")


def test_actual_source_invalidation_at_owner_inventory_cap(memory_client):
    """Invalidate1000 actual bounded SQL copies without pretending they are1000 model or API capture calls."""
    client, auth = memory_client
    headers = auth["headers"][0]
    receipt, identity, record = captured_source(client, headers)

    async def seed_and_invalidate():
        """Clone only the owned valid fixture shape and require one bounded source transaction to remove its copies."""
        async with (
            client.app.state.conversation_service.session_factory() as session,
            session.begin(),
        ):
            await session.execute(text("SET LOCAL statement_timeout='5s'"))
            await session.execute(
                text(
                    "INSERT INTO assistant.memories(id,owner_id,kind,scope_id,consent_id,text,method,model_id,provenance,content_trust,created_at,updated_at,expires_at,version) SELECT gen_random_uuid(),m.owner_id,m.kind,m.scope_id,m.consent_id,m.text,m.method,m.model_id,m.provenance,m.content_trust,m.created_at,m.updated_at,m.expires_at,m.version FROM assistant.memories m CROSS JOIN generate_series(1,999) WHERE m.id=:id"
                ),
                dict(id=UUID(record["id"])),
            )
            assert (
                await session.scalar(
                    text(
                        "SELECT count(*) FROM assistant.memories WHERE owner_id=:owner"
                    ),
                    dict(owner=UUID(record["owner_id"])),
                )
                == 1000
            )
            await session.execute(
                text(
                    "UPDATE assistant.messages SET content='new owned source' WHERE id=:id"
                ),
                dict(id=UUID(identity["message_id"])),
            )
            assert (
                await session.scalar(
                    text(
                        "SELECT count(*) FROM assistant.memories WHERE owner_id=:owner"
                    ),
                    dict(owner=UUID(record["owner_id"])),
                )
                == 0
            )

    client.portal.call(seed_and_invalidate)
    assert client.get("/api/v1/memory/export", headers=headers).json()["records"] == []
    logger.info("memory_actual_source_inventory_cap_verified rows=1000")


def test_actual_explicit_manual_edit_detaches_preference_from_source(memory_client):
    """Retain a separately explicit manual preference after source deletion while removing its old extraction provenance."""
    client, auth = memory_client
    headers = auth["headers"][0]
    receipt, identity, record = captured_source(client, headers)
    response = client.patch(
        "/api/v1/memory/records/" + record["id"],
        headers=headers,
        json=dict(expected_version=1, text="Explicit independent manual decision"),
    )
    assert response.status_code == 200 and response.json()["method"] == "manual"
    assert (
        response.json()["model_id"] is None
        and response.json()["provenance"]["kind"] == "manual"
    )
    assert (
        client.delete(
            "/api/v1/conversations/" + identity["conversation_id"], headers=headers
        ).status_code
        == 204
    )
    assert (
        client.get("/api/v1/memory/records/" + record["id"], headers=headers).json()
        == response.json()
    )
    logger.info("memory_actual_explicit_manual_detachment_verified")
