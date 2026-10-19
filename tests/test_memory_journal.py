"""Verify memory journal serialization, preflight rejection and additive migration/grant/downgrade boundaries."""

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest
from test_memory_contract import NOW, TEXT, payload

from src.application.services.memory_contract import (
    MemoryConsent,
    MemoryPolicyError,
    MemoryRecord,
)
from src.infrastructure.repositories.memory_journal import (
    PostgresMemoryJournal,
    record_values,
    typed_owner,
)

ROOT = Path(__file__).resolve().parents[1]


def migration():
    """Load the new migration as source without running DDL or opening a connection."""
    spec = importlib.util.spec_from_file_location(
        "memory_v005", ROOT / "migrations/versions/0005_memory_journal.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_exact_manual_snapshot_serialization_and_hash():
    """Preserve exact UTF-8 text and typed IDs while making nested provenance actual JSONB input."""
    record = MemoryRecord.model_validate(payload()["record"])
    values = record_values(record)
    assert values["id"] == record.id and values["text"] == TEXT
    assert json.loads(values["provenance"]) == dict(
        kind="manual", content_sha256=hashlib.sha256(TEXT.encode()).hexdigest()
    )
    extracted = MemoryRecord.model_validate(payload(extracted=True)["record"])
    encoded = json.loads(record_values(extracted)["provenance"])
    assert encoded["conversation_id"] == str(extracted.provenance.conversation_id)
    assert encoded["message_id"] == str(extracted.provenance.message_id)


@pytest.mark.parametrize("owner", [None, "user", True, 123])
def test_untyped_owner_fails_closed(owner):
    """Never coerce a caller value into an authenticated repository principal."""
    with pytest.raises(MemoryPolicyError, match="memory_owner_invalid"):
        typed_owner(owner)


@pytest.mark.parametrize(
    "fault", ["blank", "bytes", "nul", "negative_ttl", "boolean_ttl", "past_receipt"]
)
def test_manual_builder_refuses_unsafe_capture_without_io(fault):
    """Reject bad content and retention before a journal INSERT can be constructed."""
    data = payload()
    consent = MemoryConsent.model_validate(data["consent"])
    journal = PostgresMemoryJournal(None)
    value, seconds, now = TEXT, None, NOW
    if fault == "blank":
        value = " "
    elif fault == "bytes":
        value = "ệ" * 1366
    elif fault == "nul":
        value = "x\0y"
    elif fault == "negative_ttl":
        seconds = -1
    elif fault == "boolean_ttl":
        seconds = True
    else:
        now = consent.expires_at
    with pytest.raises(MemoryPolicyError):
        journal._manual(
            data["record"]["owner_id"], consent, value, now, seconds=seconds
        )


def test_server_manual_builder_cannot_accept_source_or_producer_overrides():
    """Derive all capture identities and hashes from the locked receipt and supplied literal text."""
    data = payload("project")
    consent = MemoryConsent.model_validate(data["consent"])
    record = PostgresMemoryJournal(None)._manual(consent.owner_id, consent, TEXT, NOW)
    assert record.id != data["record"]["id"] and record.consent_id == consent.id
    assert record.kind == consent.kind and record.scope_id == consent.scope_id
    assert record.model_id is None and record.method == "manual"
    assert record.expires_at == consent.expires_at


def test_migration_copies_reviewed_tables_and_overrides_inherited_grants(monkeypatch):
    """Render only additive memory DDL with explicit mutable-column grants after inherited privilege revocation."""
    module = migration()
    statements = []

    def capture(value):
        """Retain rendered SQL only without executing schema operations."""
        statements.append(str(value))

    monkeypatch.setattr(module.op, "execute", capture)
    module.upgrade()
    ddl = "\n".join(statements)
    assert module.revision == "0005" and module.down_revision == "0004"
    assert (ROOT / "docs/proposals/d29-memory-schema.sql").read_text() in ddl
    assert "REVOKE ALL ON assistant.memory_settings" in ddl
    assert "GRANT UPDATE (revoked_at) ON assistant.memory_consents" in ddl
    assert (
        "GRANT UPDATE (text, method, model_id, provenance, updated_at, expires_at, version)"
        in ddl
    )
    assert "ALTER TABLE assistant.files" not in ddl and "TRUNCATE" not in ddl
    assert "lock_timeout='5s'" in ddl and "statement_timeout='30s'" in ddl


def test_downgrade_refuses_any_populated_memory_resource(monkeypatch):
    """Require empty settings/receipts/records before dropping only the additive memory relations."""
    module = migration()
    statements = []

    def capture(value):
        """Retain the guarded downgrade SQL without executing it."""
        statements.append(str(value))

    monkeypatch.setattr(module.op, "execute", capture)
    module.downgrade()
    ddl = "\n".join(statements)
    for table in ("memory_settings", "memory_consents", "memories"):
        assert "EXISTS (SELECT 1 FROM assistant." + table + ")" in ddl
        assert "DROP TABLE assistant." + table in ddl
    assert ddl.index("RAISE EXCEPTION") < ddl.index("DROP TABLE")
