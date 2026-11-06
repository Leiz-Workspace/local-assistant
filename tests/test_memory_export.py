"""Verify explicit memory export inventory/UTF-8 bounds and content-free audit without database or model claims."""

import json
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from src.application.services import memory_export
from src.application.services.memory_contract import MemoryPolicyError


def test_export_unicode_identity_and_private_audit(caplog):
    """Preserve owner UUID/time and exact Unicode while logging only counts and byte length."""
    owner = uuid4()
    value = "Private a\u0301 𝄞"
    now = datetime.now(timezone.utc)
    with caplog.at_level("INFO"):
        result = memory_export.memory_export_payload(
            dict(owner_id=owner, enabled=False), [], [dict(text=value)], now
        )
    assert result["settings"]["owner_id"] == str(owner)
    assert result["records"][0]["text"] == value
    assert (
        result["content_trust"] == "untrusted"
        and datetime.fromisoformat(result["observed_at"]) == now
    )
    assert value not in caplog.text and str(owner) not in caplog.text


@pytest.mark.parametrize("field", ["records", "consents"])
def test_export_inventory_limits_refuse_instead_of_truncate(field):
    """Accept exactly the owner inventory cap and refuse the first excess row."""
    values = dict(consents=[], records=[])
    values[field] = [{}] * 1000
    assert (
        len(memory_export.memory_export_payload({}, **values, observed_at=None)[field])
        == 1000
    )
    values[field].append({})
    with pytest.raises(MemoryPolicyError, match="memory_export_limit"):
        memory_export.memory_export_payload({}, **values, observed_at=None)


def test_export_exact_utf8_byte_boundary(monkeypatch):
    """Count actual UTF-8 JSON bytes and reject one byte below the exact serialized payload size."""
    args = ({}, [], [dict(text="𝄞 a\u0301")], None)
    result = memory_export.memory_export_payload(*args)
    size = len(
        json.dumps(
            result, ensure_ascii=False, allow_nan=False, separators=(",", ":")
        ).encode()
    )
    monkeypatch.setattr(memory_export, "MAX_EXPORT_BYTES", size)
    assert memory_export.memory_export_payload(*args) == result
    monkeypatch.setattr(memory_export, "MAX_EXPORT_BYTES", size - 1)
    with pytest.raises(MemoryPolicyError, match="memory_export_limit"):
        memory_export.memory_export_payload(*args)
