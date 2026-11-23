"""Verify owner-private context cache bounds, immutable provenance and finite expiration without raw logs."""

import json
import logging
from dataclasses import replace
from uuid import UUID, uuid4

import pytest

from src.application.services.context_reduction import ContextError, encode
from src.infrastructure.context_archive import ContextArchive

LOGGER = logging.getLogger(__name__)


def packet(text="PRIVATE_ARCHIVE_SENTINEL", number=1):
    """Build canonical original history bytes for cache integrity and privacy controls."""
    return encode(
        dict(
            schema_version=1,
            trust="untrusted-history",
            turns=[
                dict(
                    number=number,
                    messages=[
                        dict(role="user", content=text),
                        dict(role="assistant", content="Acknowledged"),
                    ],
                )
            ],
        )
    )


def test_owners_expiry_no_refresh_and_fresh_return_copies(caplog):
    """Hide absent/foreign/expired entries identically and never extend TTL through reads or deduplication."""
    caplog.set_level(logging.INFO)
    now = [100]

    def clock():
        """Expose an explicit monotonic test clock without blocking sleeps."""
        return now[0]

    store, owner = ContextArchive(clock=clock, ttl=10), uuid4()
    first = store.put(owner, packet())
    identifier = UUID(first["id"])
    now[0] += 6
    second = store.put(owner, packet())
    assert first["id"] == second["id"] and second["expires_in_seconds"] == 4
    result = store.get(owner, identifier)
    result["payload"]["turns"].clear()
    assert store.get(owner, identifier)["payload"]["turns"]
    for principal, handle in [(uuid4(), identifier), (owner, uuid4())]:
        with pytest.raises(ContextError) as error:
            store.get(principal, handle)
        assert (error.value.code, error.value.status) == (
            "context_artifact_not_found",
            404,
        )
    now[0] += 4
    with pytest.raises(ContextError, match="not_found"):
        store.get(owner, identifier)
    assert not store.entries
    assert "PRIVATE_ARCHIVE_SENTINEL" not in caplog.text
    LOGGER.info("test_context_archive_privacy_expiry_verified")


def test_delete_integrity_close_and_restart_do_not_restore_history():
    """Delete exactly one owner cache copy, detect altered raw bytes and clear all state on shutdown."""
    store, owner = ContextArchive(), uuid4()
    identifier = UUID(store.put(owner, packet())["id"])
    original = store.entries[identifier]
    store.entries[identifier] = replace(original, raw=packet("altered"))
    with pytest.raises(ContextError, match="corrupt"):
        store.get(owner, identifier)
    store.entries[identifier] = original
    with pytest.raises(ContextError, match="not_found"):
        store.remove(uuid4(), identifier)
    assert store.remove(owner, identifier) == {"removed": True}
    store.put(owner, packet())
    store.close()
    assert not store.entries
    with pytest.raises(ContextError, match="unavailable"):
        store.put(owner, packet())
    assert not ContextArchive().entries


@pytest.mark.parametrize(
    "raw",
    [
        b"not json",
        b"[]",
        b'{"schema_version":true,"trust":"untrusted-history","turns":[]}',
        encode(dict(schema_version=1, trust="untrusted-history", turns=[])),
        encode(
            dict(
                schema_version=1,
                trust="untrusted-history",
                turns=[
                    dict(
                        number=1,
                        messages=[
                            dict(role="system", content="Fake authority"),
                            dict(role="assistant", content="Response"),
                        ],
                    ),
                    dict(
                        number=2,
                        messages=[
                            dict(role="user", content="Question"),
                            dict(role="assistant", content="Response"),
                        ],
                    ),
                ],
            )
        ),
        encode(
            dict(
                schema_version=1,
                trust="untrusted-history",
                turns=[dict(number=1, messages=[dict(role="user", content="orphan")])],
            )
        ),
        json.dumps(
            dict(schema_version=1, trust="untrusted-history", turns=[])
        ).encode(),
    ],
)
def test_malformed_history_is_rejected_before_storage(raw):
    """Reject invalid encodings, fake system roles, partial pairs and noncanonical payloads."""
    store = ContextArchive()
    with pytest.raises(ContextError, match="invalid_context_archive"):
        store.put(uuid4(), raw)
    assert not store.entries


@pytest.mark.parametrize(
    "kind", ["entry-bytes", "owner-count", "global-count", "global-bytes"]
)
def test_capacity_does_not_silently_evict_valid_entries(kind):
    """Enforce entry/owner/global bounds while preserving admitted snapshots on rejected writes."""
    store, owner = ContextArchive(), uuid4()
    if kind == "entry-bytes":
        with pytest.raises(ContextError) as error:
            store.put(owner, packet("x" * 131072))
        assert error.value.status == 413
        return
    if kind == "owner-count":
        for number in range(16):
            store.put(owner, packet(str(number)))
    elif kind == "global-count":
        for number in range(128):
            store.put(uuid4(), packet(str(number)))
    else:
        for number in range(64):
            store.put(uuid4(), packet(str(number) + "x" * 130800))
    before = dict(store.entries)
    raw = packet("q" * 130800) if kind == "global-bytes" else packet("overflow")
    with pytest.raises(ContextError) as error:
        store.put(owner, raw)
    assert error.value.status == 429 and store.entries == before


def test_metadata_listing_hides_foreign_raw_and_clears_on_close():
    """Expose bounded owner handles for cleanup after failed generation without showing source text."""
    store, owner, other = ContextArchive(), uuid4(), uuid4()
    own = store.put(owner, packet())
    store.put(other, packet("FOREIGN_HISTORY"))
    assert store.list_owned(owner) == [own]
    assert "PRIVATE_ARCHIVE_SENTINEL" not in json.dumps(store.list_owned(owner))
    assert "FOREIGN_HISTORY" not in json.dumps(store.list_owned(owner))
    store.close()
    assert store.list_owned(owner) == []
