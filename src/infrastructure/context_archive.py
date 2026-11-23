"""Keep bounded owner-private raw history snapshots in process memory with explicit expiry, recall and deletion."""

import hashlib
import json
import logging
import time
from dataclasses import dataclass
from uuid import UUID, uuid4

from src.application.services.context_reduction import ContextError, encode

LOGGER = logging.getLogger(__name__)


def validate_packet(raw):
    """Reject malformed or ambiguous cache packets, including partial turns and noncanonical encodings."""
    try:
        packet = json.loads(raw)
        valid = (
            type(packet) is dict
            and set(packet) == {"schema_version", "trust", "turns"}
            and type(packet["schema_version"]) is int
            and packet["schema_version"] == 1
            and packet["trust"] == "untrusted-history"
            and type(packet["turns"]) is list
            and 1 <= len(packet["turns"]) <= 127
        )
        previous = 0
        for turn in packet["turns"] if valid else ():
            valid = (
                type(turn) is dict
                and set(turn) == {"number", "messages"}
                and type(turn["number"]) is int
                and previous < turn["number"] <= 127
                and type(turn["messages"]) is list
                and len(turn["messages"]) == 2
            )
            if not valid:
                break
            previous = turn["number"]
            for role, row in zip(("user", "assistant"), turn["messages"]):
                if (
                    type(row) is not dict
                    or set(row) != {"role", "content"}
                    or row["role"] != role
                    or type(row["content"]) is not str
                    or not row["content"].strip()
                ):
                    valid = False
            if not valid:
                break
        if not valid or encode(packet) != raw:
            raise ValueError
    except (ValueError, TypeError, UnicodeError, RecursionError, ContextError):
        raise ContextError("invalid_context_archive") from None


@dataclass(frozen=True)
class ArchiveEntry:
    """Retain immutable bytes and owner binding without restoring any permission or durable state."""

    owner: UUID
    raw: bytes
    sha256: str
    expires: float


class ContextArchive:
    """Own a bounded ephemeral cache; raw data never enters disk history, logs or a cross-owner lookup."""

    def __init__(self, *, clock=time.monotonic, ttl=1800):
        """Start an empty process-local store with fixed maximum lifetime and explicit resource bounds."""
        if not 1 <= ttl <= 1800:
            raise ValueError("invalid_archive_ttl")
        self.clock, self.ttl = clock, ttl
        self.entries = {}
        self.closed = False

    def prune(self):
        """Expire entries without extending their lifetime on read."""
        now = self.clock()
        self.entries = {
            key: value for key, value in self.entries.items() if value.expires > now
        }

    def put(self, owner, raw):
        """Admit an exact bounded history packet and deduplicate only this owner's identical immutable bytes."""
        self.prune()
        if self.closed or type(owner) is not UUID:
            raise ContextError("context_archive_unavailable", 503)
        if type(raw) is not bytes or not 1 <= len(raw) <= 131072:
            raise ContextError("context_archive_entry_too_large", 413)
        validate_packet(raw)
        sha = hashlib.sha256(raw).hexdigest()
        for identifier, entry in self.entries.items():
            if entry.owner == owner and entry.raw == raw:
                return self.metadata(identifier, entry)
        owned = [entry for entry in self.entries.values() if entry.owner == owner]
        if (
            len(owned) >= 16
            or len(self.entries) >= 128
            or sum(len(entry.raw) for entry in owned) + len(raw) > 2097152
            or sum(len(entry.raw) for entry in self.entries.values()) + len(raw)
            > 8388608
        ):
            raise ContextError("context_archive_capacity", 429)
        identifier = uuid4()
        entry = ArchiveEntry(owner, raw, sha, self.clock() + self.ttl)
        self.entries[identifier] = entry
        LOGGER.info(
            "context_archive_created artifact_id=%s bytes=%d", identifier, len(raw)
        )
        return self.metadata(identifier, entry)

    def metadata(self, identifier, entry):
        """Expose only a handle/digest/size/remaining lifetime without owner identity or raw history."""
        return dict(
            id=str(identifier),
            sha256=entry.sha256,
            bytes=len(entry.raw),
            expires_in_seconds=max(0, int(entry.expires - self.clock())),
            storage="process-memory",
        )

    def list_owned(self, owner):
        """List only current-owner cache metadata, including snapshots from interrupted completions."""
        self.prune()
        LOGGER.info("context_archive_metadata_listed")
        return [
            self.metadata(identifier, entry)
            for identifier, entry in self.entries.items()
            if entry.owner == owner and not self.closed
        ]

    def get(self, owner, identifier):
        """Hide absent, expired and foreign records behind the same failure and return a fresh payload copy."""
        self.prune()
        entry = self.entries.get(identifier)
        if self.closed or entry is None or entry.owner != owner:
            raise ContextError("context_artifact_not_found", 404)
        if hashlib.sha256(entry.raw).hexdigest() != entry.sha256:
            raise ContextError("context_archive_corrupt", 503)
        LOGGER.info("context_archive_recalled artifact_id=%s", identifier)
        return dict(self.metadata(identifier, entry), payload=json.loads(entry.raw))

    def remove(self, owner, identifier):
        """Delete only the authenticated owner's cached copy, without changing original conversation storage."""
        self.get(owner, identifier)
        del self.entries[identifier]
        LOGGER.info("context_archive_removed artifact_id=%s", identifier)
        return dict(removed=True)

    def close(self):
        """Release all raw references on service shutdown without persisting or replaying them."""
        self.entries.clear()
        self.closed = True
        LOGGER.info("context_archive_closed")
