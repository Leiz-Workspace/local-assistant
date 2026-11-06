"""Verify actual principal-only read-only memory export, disabled controls and exact persisted extraction provenance."""

import logging

from test_memory_extraction_live import (
    ControlledCore,
    http_receipt,
    http_source,
)
from test_memory_http import enable_and_grant
from test_memory_http import memory_client as memory_client

logger = logging.getLogger(__name__)


def test_actual_owner_disabled_export_and_foreign_isolation(memory_client):
    """Export all retained own settings/receipts/Unicode records while disabled without leaking another principal."""
    client, auth = memory_client
    headers, foreign = auth["headers"]
    receipt = enable_and_grant(client, headers)
    foreign_receipt = enable_and_grant(client, foreign)
    for token, consent, value in [
        (headers, receipt, "Own a\u0301 𝄞 preference"),
        (foreign, foreign_receipt, "Foreign private value"),
    ]:
        response = client.post(
            "/api/v1/memory/records",
            headers=token,
            json=dict(consent_id=consent["id"], text=value),
        )
        assert response.status_code == 201
    assert (
        client.delete(
            "/api/v1/memory/consents/" + receipt["id"], headers=headers
        ).status_code
        == 200
    )
    assert (
        client.put(
            "/api/v1/memory/settings",
            headers=headers,
            json=dict(expected_revision=1, enabled=False, extraction_enabled=False),
        ).status_code
        == 200
    )
    response = client.get("/api/v1/memory/export", headers=headers)
    assert (
        response.status_code == 200
        and response.headers["cache-control"] == "private, no-store"
    )
    assert (
        response.headers["content-disposition"]
        == 'attachment; filename="memory-export.json"'
    )
    data = response.json()
    assert (
        data["format"] == "local-assistant-memory-v1"
        and data["content_trust"] == "untrusted"
    )
    assert data["settings"]["enabled"] is False and data["settings"]["revision"] == 2
    assert len(data["consents"]) == len(data["records"]) == 1
    assert (
        data["consents"][0]["id"] == receipt["id"]
        and data["consents"][0]["revoked_at"] is not None
    )
    assert data["records"][0]["text"] == "Own a\u0301 𝄞 preference"
    assert (
        "Foreign private value" not in response.text
        and foreign_receipt["id"] not in response.text
    )
    assert client.get("/api/v1/memory/export").status_code == 401
    assert (
        client.get("/api/v1/memory/records", headers=headers).json()["records"][0][
            "version"
        ]
        == 1
    )
    logger.info("memory_actual_owner_export_verified")


def test_actual_empty_export_does_not_initialize_owner(memory_client):
    """Read inert revision0 without creating implicit settings/consent or enabling memory."""
    client, auth = memory_client
    response = client.get("/api/v1/memory/export", headers=auth["headers"][0])
    assert response.status_code == 200
    data = response.json()
    assert (
        data["settings"]["revision"] == 0
        and not data["consents"]
        and not data["records"]
    )
    assert (
        client.get("/api/v1/memory/settings", headers=auth["headers"][0]).json()[
            "revision"
        ]
        == 0
    )


def test_actual_export_extracted_jsonb_identity_without_model_call(memory_client):
    """Round-trip actual SQL extracted provenance through export using a declared controlled protocol port."""
    client, auth = memory_client
    headers = auth["headers"][0]
    receipt = http_receipt(client, headers)
    value = "I prefer exact a\u0301 𝄞."
    identity = http_source(client, headers, value)
    client.app.state.memory_service.extractor.inference = ControlledCore(blocking=False)
    result = client.post(
        "/api/v1/memory/extractions",
        headers=headers,
        json=dict(consent_id=receipt["id"], **identity),
    )
    assert result.status_code == 200
    response = client.get("/api/v1/memory/export", headers=headers)
    assert response.status_code == 200
    record = response.json()["records"][0]
    assert record == result.json()["record"]
    assert record["provenance"]["message_id"] == identity["message_id"]
    assert record["model_id"] == "controlled-core" and record["text"] == value
