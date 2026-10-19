"""Verify source-bound literal memory selection and cancellation-resistant owned work without model-quality claims."""

import asyncio
import hashlib
import json
import logging
from dataclasses import FrozenInstanceError
from uuid import uuid4

import pytest

from apps.api.services.memory_work import joined_memory_work
from src.application.services.memory_contract import MemoryPolicyError
from src.application.services.memory_selection import (
    MessageMemorySource,
    parse_selection,
    selection_messages,
)


def source(value="I prefer Vietnamese. a\u0301 𝄞."):
    """Build an exact synthetic bounded snapshot without asserting actual storage ownership."""
    return MessageMemorySource(
        uuid4(), uuid4(), hashlib.sha256(value.encode()).hexdigest(), value
    )


def selected(quote):
    """Encode the strict two-field model fixture with no human judgment or fabricated inference."""
    return json.dumps(dict(status="selected", quote=quote), ensure_ascii=False)


def test_literal_unicode_selection_and_untrusted_prompt():
    """Preserve combining/astral text exactly and keep the complete source in a separate untrusted data block."""
    snapshot = source()
    assert parse_selection(selected("a\u0301 𝄞."), snapshot) == "a\u0301 𝄞."
    messages = selection_messages("preference", snapshot)
    assert messages[0]["role"] == "system" and "untrusted" in messages[0]["content"]
    assert json.loads(messages[1]["content"]) == dict(
        memory_kind="preference", source_text=snapshot.text
    )
    with pytest.raises(FrozenInstanceError):
        snapshot.text = "changed"


@pytest.mark.parametrize(
    "raw",
    [
        "{}",
        "[]",
        "not JSON",
        '{"status":"selected","quote":"x","quote":"y"}',
        '{"status":"selected","quote":NaN}',
        '{"status":"selected","quote":"I","owner_id":"foreign"}',
        '{"status":"selected","quote":null}',
        '{"status":"insufficient_evidence","quote":"I"}',
        '{"status":"invented","quote":"I"}',
    ],
)
def test_malformed_or_spoofed_model_output_rejected(raw):
    """Reject duplicates, nonfinite/extra fields and inconsistent status rather than repairing model output."""
    with pytest.raises(MemoryPolicyError, match="memory_selection_invalid"):
        parse_selection(raw, source())


@pytest.mark.parametrize("quote", ["invented fact", "á 𝄞.", " ", 17, {"text": "I"}])
def test_absent_normalized_blank_and_nonlexical_quotes_fail(quote):
    """Never substitute a normalized, fabricated or structured value for a literal unique source quote."""
    with pytest.raises(MemoryPolicyError):
        parse_selection(selected(quote), source())


def test_overlapping_duplicate_quote_is_ambiguous():
    """Reject overlapping matches instead of treating the first match as authoritative."""
    with pytest.raises(MemoryPolicyError):
        parse_selection(selected("aaa"), source("aaaa"))


def test_exact_quote_source_and_output_limits():
    """Accept inclusive byte boundaries and reject one byte beyond without truncating source or quote."""
    assert len(source("x" * 8192).text) == 8192
    with pytest.raises(MemoryPolicyError, match="memory_source_limit"):
        source("x" * 8193)
    snapshot = source("x" * 2048 + ".")
    assert parse_selection(selected("x" * 2048), snapshot) == "x" * 2048
    with pytest.raises(MemoryPolicyError):
        parse_selection(selected("x" * 2049), source("x" * 2049 + "."))
    raw = selected("I")
    assert parse_selection(raw + " " * (8192 - len(raw)), source()) == "I"
    with pytest.raises(MemoryPolicyError):
        parse_selection(raw + " " * (8193 - len(raw)), source())


@pytest.mark.parametrize("fault", ["hash", "owner_type", "blank", "nul"])
def test_invalid_snapshot_cannot_become_evidence(fault):
    """Reject corrupted source snapshots before prompt creation or quote scoring."""
    value = "valid"
    arguments = dict(
        conversation_id=uuid4(),
        message_id=uuid4(),
        content_sha256=hashlib.sha256(value.encode()).hexdigest(),
        text=value,
    )
    if fault == "hash":
        arguments["content_sha256"] = "0" * 64
    elif fault == "owner_type":
        arguments["conversation_id"] = "not-a-uuid"
    elif fault == "blank":
        arguments["text"] = " "
    else:
        arguments["text"] = "x\0y"
    with pytest.raises(MemoryPolicyError):
        MessageMemorySource(**arguments)


def test_insufficient_evidence_returns_no_selected_memory():
    """Represent absence explicitly rather than manufacturing a selected quote or score."""
    assert (
        parse_selection('{"status":"insufficient_evidence","quote":null}', source())
        is None
    )


def test_selection_audit_excludes_private_content(caplog):
    """Log only schema/count outcomes rather than source text, hashes or IDs."""
    caplog.set_level(logging.INFO)
    snapshot = source("PRIVATE-QUOTE-SENTINEL")
    parse_selection(selected(snapshot.text), snapshot)
    assert "memory_selection_verified" in caplog.text
    assert (
        snapshot.text not in caplog.text and snapshot.content_sha256 not in caplog.text
    )
    assert str(snapshot.message_id) not in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["cancel", "repeated_cancel", "timeout"])
async def test_owned_work_joins_cleanup_for_every_interruption(mode):
    """Keep the owned child cleanup alive when parent cancellation repeats or a deadline fires."""
    entered, cleaning = asyncio.Event(), asyncio.Event()
    joined = []

    async def blocked():
        """Expose a cleanup barrier independent of parent task cancellation state."""
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            cleaning.set()
            await asyncio.sleep(0.02)
            joined.append(True)

    task = asyncio.create_task(
        joined_memory_work(blocked(), timeout=0.01 if mode == "timeout" else None)
    )
    await entered.wait()
    if mode != "timeout":
        task.cancel()
        if mode == "repeated_cancel":
            await cleaning.wait()
            task.cancel()
    with pytest.raises(TimeoutError if mode == "timeout" else asyncio.CancelledError):
        await task
    assert joined == [True]
