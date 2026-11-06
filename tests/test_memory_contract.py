"""Verify consent-bound memory defaults, four scopes, Unicode provenance and policy refusal without live-memory claims."""

import hashlib
import json
import logging
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from src.application.services.memory_contract import (
    FileEvidence,
    MemoryBundle,
    MemoryConsent,
    MemoryPolicyError,
    MemoryRecord,
    MemorySettings,
    MessageEvidence,
    authorize_memory,
    retention_cap,
)

NOW = datetime(2026, 10, 19, 9, tzinfo=timezone.utc)
TEXT = "Private Unicode a\u0301 𝄞 preference."


def payload(kind="preference", *, extracted=False):
    """Create explicit synthetic owner/receipt/provenance snapshots with no implicit runtime consent."""
    owner, receipt = uuid4(), uuid4()
    scope = owner if kind in ("episodic", "preference") else uuid4()
    evidence = dict(
        kind="manual", content_sha256=hashlib.sha256(TEXT.encode()).hexdigest()
    )
    if extracted:
        evidence = dict(
            kind="conversation_message",
            conversation_id=scope if kind == "session" else uuid4(),
            message_id=uuid4(),
            role="user",
            content_sha256="a" * 64,
            quote="a\u0301 𝄞",
            start=7,
            end=11,
        )
    return dict(
        settings=dict(
            owner_id=owner,
            revision=1,
            enabled=True,
            extraction_enabled=extracted,
            updated_at=NOW - timedelta(minutes=2),
        ),
        consent=dict(
            id=receipt,
            owner_id=owner,
            kind=kind,
            scope_id=scope,
            settings_revision=1,
            allow_extraction=extracted,
            granted_at=NOW - timedelta(minutes=1),
            expires_at=NOW + timedelta(minutes=30),
        ),
        record=dict(
            id=uuid4(),
            owner_id=owner,
            kind=kind,
            scope_id=scope,
            consent_id=receipt,
            text=TEXT,
            method="extracted" if extracted else "manual",
            model_id="existing-core-fixture" if extracted else None,
            provenance=evidence,
            created_at=NOW,
            updated_at=NOW,
            expires_at=NOW + timedelta(minutes=15),
        ),
    )


@pytest.mark.parametrize("kind", ["session", "episodic", "preference", "project"])
@pytest.mark.parametrize("extracted", [False, True])
def test_four_classes_and_explicit_snapshot_authorization(kind, extracted):
    """Accept all four classes only with matching explicit scope/consent and exact typed provenance."""
    bundle = MemoryBundle.model_validate(payload(kind, extracted=extracted))
    record = authorize_memory(bundle, bundle.record.owner_id, NOW, action="write")
    assert record.kind == kind and record.content_trust == "untrusted"
    parsed = MemoryBundle.model_validate_json(bundle.model_dump_json())
    assert parsed == bundle


def test_default_settings_are_inert():
    """Require independent memory/extraction opt-in rather than deriving consent from existing history."""
    settings = MemorySettings(owner_id=uuid4(), revision=1, updated_at=NOW)
    assert not settings.enabled and not settings.extraction_enabled
    with pytest.raises(ValueError):
        MemorySettings(
            owner_id=uuid4(), revision=1, updated_at=NOW, extraction_enabled=True
        )


@pytest.mark.parametrize(
    "field,value",
    [
        ("owner_id", uuid4()),
        ("id", uuid4()),
        ("scope_id", uuid4()),
        ("kind", "episodic"),
        ("expires_at", NOW + timedelta(minutes=10)),
        ("granted_at", NOW + timedelta(seconds=1)),
    ],
)
def test_mismatched_receipt_cannot_bind_record(field, value):
    """Reject cross-owner, receipt, class/scope and time-window substitutions before use."""
    data = payload()
    data["consent"][field] = value
    with pytest.raises(ValueError):
        MemoryBundle.model_validate(data)


@pytest.mark.parametrize(
    "fault",
    [
        "disabled",
        "epoch",
        "revoked",
        "expired",
        "future",
        "settings_after_grant",
        "foreign",
    ],
)
def test_current_consent_policy_refuses_inactive_snapshots(fault):
    """Deny current use/write when owner consent was disabled, revoked, expired or replaced."""
    data = payload()
    principal, now = data["record"]["owner_id"], NOW
    if fault == "disabled":
        data["settings"]["enabled"] = False
    elif fault == "epoch":
        data["settings"]["revision"] = 2
    elif fault == "revoked":
        data["consent"]["revoked_at"] = NOW
    elif fault == "expired":
        now += timedelta(minutes=30)
    elif fault == "future":
        now -= timedelta(minutes=2)
    elif fault == "settings_after_grant":
        data["settings"]["updated_at"] = NOW
    else:
        principal = uuid4()
    bundle = MemoryBundle.model_validate(data)
    with pytest.raises(MemoryPolicyError):
        authorize_memory(bundle, principal, now, action="use")


def test_extraction_disable_blocks_new_capture_but_preserves_existing_use():
    """Treat extraction opt-out separately from full memory disablement under still-active consent."""
    data = payload(extracted=True)
    data["settings"]["extraction_enabled"] = False
    bundle = MemoryBundle.model_validate(data)
    with pytest.raises(MemoryPolicyError, match="memory_extraction_disabled"):
        authorize_memory(bundle, bundle.record.owner_id, NOW, action="write")
    assert (
        authorize_memory(bundle, bundle.record.owner_id, NOW, action="use").method
        == "extracted"
    )
    data["consent"]["allow_extraction"] = False
    with pytest.raises(ValueError):
        MemoryBundle.model_validate(data)


@pytest.mark.parametrize(
    "fault",
    [
        "hash",
        "model",
        "blank",
        "bytes",
        "extra",
        "trust",
        "naive",
        "bool_version",
        "nul",
    ],
)
def test_manual_private_content_contract(fault):
    """Reject content-hash drift, producer spoofing, unbounded/blank text and schema coercion."""
    data = payload()
    record = data["record"]
    if fault == "hash":
        record["provenance"]["content_sha256"] = "b" * 64
    elif fault == "model":
        record["model_id"] = "unexpected-producer"
    elif fault == "blank":
        record["text"] = "  "
    elif fault == "bytes":
        record["text"] = "ệ" * 1366
    elif fault == "extra":
        record["tools"] = ["execute"]
    elif fault == "trust":
        record["content_trust"] = "system"
    elif fault == "naive":
        record["created_at"] = NOW.replace(tzinfo=None)
    elif fault == "nul":
        record["text"] = "private\0text"
    else:
        record["version"] = True
    with pytest.raises(ValueError):
        MemoryBundle.model_validate(data)


@pytest.mark.parametrize("kind", ["session", "episodic", "preference", "project"])
def test_exact_retention_boundary_and_overflow(kind):
    """Accept the declared inclusive lifetime cap and reject one microsecond beyond it."""
    data = payload(kind)
    data["consent"]["granted_at"] = NOW
    data["consent"]["expires_at"] = NOW + retention_cap(kind)
    data["record"]["expires_at"] = data["consent"]["expires_at"]
    assert (
        MemoryBundle.model_validate(data).record.expires_at
        == data["record"]["expires_at"]
    )
    data["consent"]["expires_at"] += timedelta(microseconds=1)
    with pytest.raises(ValueError):
        MemoryBundle.model_validate(data)


def test_unicode_message_and_file_provenance_stays_literal():
    """Preserve combining/astral code points and reject fabricated lengths, roles and cross-file locators."""
    data = payload("session", extracted=True)
    message = MessageEvidence.model_validate(data["record"]["provenance"])
    assert message.end - message.start == len("a\u0301 𝄞")
    for change in (dict(end=10), dict(role="assistant"), dict(content_sha256="broken")):
        with pytest.raises(ValueError):
            MessageEvidence.model_validate(dict(data["record"]["provenance"], **change))
    file_id = uuid4()
    file_data = dict(
        kind="file_quote",
        file_id=file_id,
        source_sha256="c" * 64,
        locator="file:" + str(file_id) + "#sheet=1&cell=A1",
        field="cached_value",
        quote="a\u0301 𝄞",
        start=0,
        end=4,
    )
    assert FileEvidence.model_validate(file_data).quote == message.quote
    with pytest.raises(ValueError):
        FileEvidence.model_validate(dict(file_data, file_id=uuid4()))
    data["record"]["provenance"]["conversation_id"] = uuid4()
    with pytest.raises(ValueError):
        MemoryBundle.model_validate(data)


@pytest.mark.parametrize("value", [True, "1", 2])
def test_fixed_policy_version_is_strict(value):
    """Reject boolean/string policy coercion and undeclared policy versions."""
    with pytest.raises(ValueError):
        MemoryConsent.model_validate(dict(payload()["consent"], policy_version=value))


def test_unvalidated_copy_does_not_bypass_authorization():
    """Revalidate even internal frozen-model copies before making a policy decision."""
    bundle = MemoryBundle.model_validate(payload())
    malformed = bundle.model_copy(
        update={"record": bundle.record.model_copy(update={"text": "changed"})}
    )
    with pytest.raises(MemoryPolicyError, match="memory_authorization_invalid"):
        authorize_memory(malformed, bundle.record.owner_id, NOW, action="use")


@pytest.mark.parametrize("fault", ["action", "principal", "time", "bundle"])
def test_authorization_requires_server_typed_arguments(fault):
    """Reject unknown actions, untyped principals, naive clocks and arbitrary dictionaries."""
    bundle = MemoryBundle.model_validate(payload())
    args = dict(bundle=bundle, principal=bundle.record.owner_id, now=NOW, action="use")
    args[
        dict(action="action", principal="principal", time="now", bundle="bundle")[fault]
    ] = {
        "action": "execute",
        "principal": str(bundle.record.owner_id),
        "time": NOW.replace(tzinfo=None),
        "bundle": bundle.model_dump(),
    }[fault]
    with pytest.raises(MemoryPolicyError):
        authorize_memory(**args)


def test_schema_contains_discriminated_consent_and_provenance():
    """Expose all four classes, receipt binding and tagged source structures for D30 schema consumers."""
    schema = MemoryBundle.model_json_schema()
    definitions = schema["$defs"]
    assert definitions["MemoryConsent"]["properties"]["kind"]["enum"] == [
        "session",
        "episodic",
        "preference",
        "project",
    ]
    assert set(
        definitions["MemoryRecord"]["properties"]["provenance"]["discriminator"][
            "mapping"
        ]
    ) == {"manual", "conversation_message", "file_quote"}
    assert "consent_id" in definitions["MemoryRecord"]["required"]
    assert definitions["MemorySettings"]["properties"]["enabled"]["default"] is False
    assert json.loads(json.dumps(schema)) == schema


def test_audit_logs_exclude_private_text_and_identity(caplog):
    """Keep successful and rejected consent audit logs free of source content and owner identifiers."""
    caplog.set_level(logging.INFO)
    bundle = MemoryBundle.model_validate(payload())
    authorize_memory(bundle, bundle.record.owner_id, NOW, action="write")
    with pytest.raises(MemoryPolicyError):
        authorize_memory(bundle, uuid4(), NOW, action="use")
    assert (
        "memory_authorized" in caplog.text and "memory_policy_rejected" in caplog.text
    )
    assert TEXT not in caplog.text and str(bundle.record.owner_id) not in caplog.text
    assert bundle.record.provenance.content_sha256 not in caplog.text
