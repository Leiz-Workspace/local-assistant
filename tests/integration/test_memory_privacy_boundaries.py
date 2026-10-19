"""Verify actual owner/export/error/log/deletion boundaries with declared controlled model replies and untrusted literal input."""

import logging
from uuid import UUID

import pytest
from sqlalchemy import text
from test_memory_extraction_live import http_receipt, http_source
from test_memory_http import memory_client as memory_client
from test_memory_source_privacy import captured_source

from src.application.ports.inference import CompletionResult

logger = logging.getLogger(__name__)


class OutputPort:
    """Return explicitly adversarial protocol fixtures without claiming actual model behavior."""

    def __init__(self, content):
        """Retain a fixed reply and call count without opening model/network/process resources."""
        self.content = content
        self.calls = 0

    async def complete(self, **kwargs):
        """Expose only the declared final string for real source/capture/privacy boundary checks."""
        self.calls += 1
        return CompletionResult(self.content, "controlled-core", "fast", "stop")


@pytest.mark.parametrize(
    "reply",
    [
        '{"status":"selected","quote":"FOREIGN_PRIVATE_CANARY"}',
        '{"status":"selected","quote":"same"}',
        '{"status":"selected","quote":"same same","owner_id":"forged"}',
        '{"status":"selected","quote":"same same","quote":"FOREIGN_PRIVATE_CANARY"}',
    ],
)
def test_actual_adversarial_completion_is_private_and_not_persisted(
    memory_client, caplog, reply
):
    """Reject malformed/foreign/ambiguous completion data before SQL insertion without echoing it into errors/logs."""
    client, auth = memory_client
    headers = auth["headers"][0]
    receipt = http_receipt(client, headers)
    identity = http_source(client, headers, "same same")
    port = OutputPort(reply)
    client.app.state.memory_service.extractor.inference = port
    with caplog.at_level("INFO"):
        response = client.post(
            "/api/v1/memory/extractions",
            headers=headers,
            json=dict(consent_id=receipt["id"], **identity),
        )
    assert response.status_code == 503 and response.json() == dict(
        detail=dict(code="memory_selection_invalid")
    )
    assert response.headers["cache-control"] == "private, no-store"
    assert "FOREIGN_PRIVATE_CANARY" not in response.text + caplog.text
    assert client.get("/api/v1/memory/export", headers=headers).json()["records"] == []
    assert port.calls == 1 and not client.app.state.memory_service.extractor.operations
    logger.info("memory_adversarial_protocol_privacy_verified")


def test_actual_foreign_source_refused_before_any_model_call(memory_client):
    """Keep an authenticated principal's explicit source selection from ever sending a foreign message to inference."""
    client, auth = memory_client
    headers, foreign = auth["headers"]
    receipt = http_receipt(client, headers)
    identity = http_source(client, foreign, "FOREIGN_PRIVATE_CANARY")
    port = OutputPort("must never be used")
    client.app.state.memory_service.extractor.inference = port
    response = client.post(
        "/api/v1/memory/extractions",
        headers=headers,
        json=dict(consent_id=receipt["id"], **identity),
    )
    assert (
        response.status_code == 404
        and "FOREIGN_PRIVATE_CANARY" not in response.text
        and port.calls == 0
    )
    logger.info("memory_foreign_source_pre_model_privacy_verified")


def test_actual_untrusted_literal_export_auth_and_logs(memory_client, caplog):
    """Return explicit literal HTML/shell-like owner data only as private JSON while denying foreign/auth/selector leakage."""
    client, auth = memory_client
    headers, foreign = auth["headers"]
    receipt = http_receipt(client, headers)
    other = http_receipt(client, foreign)
    literal = "<script>PRIVATE_LITERAL_9261</script> $(not_a_command) a\u0301 𝄞"
    with caplog.at_level("INFO"):
        own = client.post(
            "/api/v1/memory/records",
            headers=headers,
            json=dict(consent_id=receipt["id"], text=literal),
        )
        other_record = client.post(
            "/api/v1/memory/records",
            headers=foreign,
            json=dict(consent_id=other["id"], text="FOREIGN_PRIVATE_CANARY"),
        )
        response = client.get(
            "/api/v1/memory/export?owner_id=" + str(auth["principals"][1]),
            headers=headers,
        )
        bad = client.post(
            "/api/v1/memory/records",
            headers=headers,
            json=dict(
                consent_id=receipt["id"],
                text="INVALID_PRIVATE_BODY",
                owner_id=str(auth["principals"][1]),
            ),
        )
    assert own.status_code == other_record.status_code == 201
    assert (
        response.status_code == 200 and response.json()["records"][0]["text"] == literal
    )
    assert response.json()["records"][0]["content_trust"] == "untrusted"
    assert response.headers["content-type"] == "application/json"
    assert (
        response.headers["cache-control"] == "private, no-store"
        and response.headers["x-content-type-options"] == "nosniff"
    )
    assert (
        response.headers["content-disposition"]
        == 'attachment; filename="memory-export.json"'
    )
    assert "FOREIGN_PRIVATE_CANARY" not in response.text
    assert bad.status_code == 422 and "INVALID_PRIVATE_BODY" not in bad.text
    assert all(
        marker not in caplog.text
        for marker in [
            "PRIVATE_LITERAL_9261",
            "FOREIGN_PRIVATE_CANARY",
            "INVALID_PRIVATE_BODY",
        ]
    )
    for extra, status in [
        ({}, 401),
        ({"Authorization": "Bearer invalid"}, 401),
        ({**headers, "Origin": "https://foreign.invalid"}, 403),
        ({**headers, "X-Forwarded-For": "127.0.0.1"}, 403),
    ]:
        rejected = client.get("/api/v1/memory/export", headers=extra)
        assert rejected.status_code == status and literal not in rejected.text
    assert (
        client.get(
            "/api/v1/memory/records/" + other_record.json()["id"], headers=headers
        ).status_code
        == 404
    )
    logger.info("memory_literal_export_privacy_verified")


def test_actual_disabled_memory_delete_physically_removes_only_record(memory_client):
    """Permanently delete one owned SQL memory record while retaining its separate original source and another owner's record."""
    client, auth = memory_client
    headers, foreign = auth["headers"]
    receipt, identity, record = captured_source(client, headers)
    other_receipt, other_identity, other_record = captured_source(client, foreign)
    route = "/api/v1/memory/records/" + record["id"] + "?expected_version=1"
    assert client.delete(route, headers=foreign).status_code == 404
    assert (
        client.put(
            "/api/v1/memory/settings",
            headers=headers,
            json=dict(expected_revision=1, enabled=False, extraction_enabled=False),
        ).status_code
        == 200
    )
    assert client.delete(route, headers=headers).status_code == 204

    async def physical_counts():
        """Inspect only exact random fixture identities to distinguish real SQL deletion from hidden API metadata."""
        async with client.app.state.conversation_service.session_factory() as session:
            memory = await session.scalar(
                text("SELECT count(*) FROM assistant.memories WHERE id=:id"),
                dict(id=UUID(record["id"])),
            )
            source = await session.scalar(
                text("SELECT content FROM assistant.messages WHERE id=:id"),
                dict(id=UUID(identity["message_id"])),
            )
            return memory, source

    count, source = client.portal.call(physical_counts)
    assert count == 0 and source == record["text"]
    assert client.get("/api/v1/memory/export", headers=headers).json()["records"] == []
    assert (
        client.get(
            "/api/v1/memory/records/" + record["id"], headers=headers
        ).status_code
        == 404
    )
    assert (
        client.get(
            "/api/v1/memory/records/" + other_record["id"], headers=foreign
        ).status_code
        == 200
    )
    logger.info("memory_actual_physical_record_delete_verified source_retained=True")
