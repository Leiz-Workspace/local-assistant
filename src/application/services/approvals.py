"""Own bounded explicit owner/workspace/content-bound approval events with exact monotonic expiry and one-shot consumption."""

import hashlib
import hmac
import json
import logging
import re
import secrets
import threading
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from time import monotonic
from uuid import UUID, uuid4

logger = logging.getLogger(__name__)
TTL_SECONDS = 120
MAX_REQUESTS = 64
MAX_EVENTS = 256
MAX_ARTIFACT_BYTES = 32768
KINDS = frozenset({"patch", "run_checks"})
ACTIVE = frozenset({"pending", "approved"})


class ApprovalError(Exception):
    """Expose a stable approval failure without private review artifacts, nonces or credential text."""

    def __init__(self, code, status_code=409):
        """Record an audit-safe code and status for authenticated transport adapters."""
        super().__init__(code)
        self.code = code
        self.status_code = status_code
        logger.warning("approval_rejected code=%s", code)


@dataclass(frozen=True, slots=True)
class ApprovalScope:
    """Bind authenticated identity, one action kind and the complete exact review artifact digest."""

    owner_id: UUID
    workspace_id: UUID
    kind: str
    artifact_sha256: str
    digest: str


@dataclass(slots=True)
class ApprovalRecord:
    """Retain server-only nonce/deadline and copied review bytes for one bounded ephemeral request."""

    identifier: UUID
    scope: ApprovalScope
    artifact: bytes
    nonce: str | None
    deadline: float
    expires_at: str
    state: str = "pending"


def scope_for(owner, workspace, kind, artifact):
    """Hash typed trusted scope and exact immutable UTF-8 review bytes without accepting caller digests."""
    if (
        type(owner) is not UUID
        or type(workspace) is not UUID
        or not isinstance(kind, str)
        or kind not in KINDS
    ):
        raise ApprovalError("approval_scope_invalid", 422)
    try:
        if (
            not isinstance(artifact, (bytes, bytearray))
            or not 1 <= len(artifact) <= MAX_ARTIFACT_BYTES
        ):
            raise ValueError()
        raw = bytes(artifact)
        if len(raw) > MAX_ARTIFACT_BYTES:
            raise ValueError()
        if not raw.decode("utf-8").strip():
            raise ValueError()
    except (ValueError, UnicodeError):
        raise ApprovalError("approval_artifact_invalid", 422) from None
    artifact_digest = hashlib.sha256(raw).hexdigest()
    encoded = json.dumps(
        dict(
            owner_id=str(owner),
            workspace_id=str(workspace),
            kind=kind,
            artifact_sha256=artifact_digest,
        ),
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    logger.info("approval_scope_derived")
    return ApprovalScope(
        owner, workspace, kind, artifact_digest, hashlib.sha256(encoded).hexdigest()
    ), raw


class ApprovalStore:
    """Serialize ephemeral approval transitions with bounded state; restart and shutdown invalidate every grant."""

    def __init__(self, catalog, *, clock=monotonic):
        """Bind only the accepted catalog and a trusted monotonic clock without opening source roots or loading credentials."""
        self.catalog = catalog
        self.clock = clock
        self._records = {}
        self._events = deque(maxlen=MAX_EVENTS)
        self._lock = threading.RLock()
        self.closing = False
        logger.info("approval_store_initialized")

    def _open(self):
        """Refuse every operation once dependency teardown has invalidated this process-local store."""
        if self.closing:
            raise ApprovalError("approval_unavailable", 503)

    def _event(self, record, state):
        """Record only immutable server IDs, scope metadata and a stable transition without sensitive artifact/nonce values."""
        record.state = state
        event = dict(
            event_id=str(uuid4()),
            request_id=str(record.identifier),
            owner_id=str(record.scope.owner_id),
            workspace_id=str(record.scope.workspace_id),
            kind=record.scope.kind,
            scope_digest=record.scope.digest,
            state=state,
            recorded_at=datetime.now(timezone.utc).isoformat(),
        )
        self._events.append(event)
        logger.info(
            "approval_event request_id=%s event_id=%s owner_id=%s workspace_id=%s kind=%s scope_digest=%s state=%s",
            record.identifier,
            event["event_id"],
            record.scope.owner_id,
            record.scope.workspace_id,
            record.scope.kind,
            record.scope.digest,
            state,
        )
        return dict(event)

    def _expire(self, record):
        """Invalidate pending or approved requests at the exact monotonic deadline without relying on wall-clock display time."""
        if record.state in ACTIVE and self.clock() >= record.deadline:
            record.nonce = None
            self._event(record, "expired")

    def _find(self, owner, identifier):
        """Authorize exact typed owner before expiry/events or exposing whether a request exists."""
        self._open()
        record = self._records.get(identifier) if type(identifier) is UUID else None
        if record is None or type(owner) is not UUID or record.scope.owner_id != owner:
            raise ApprovalError("approval_not_found", 404)
        self._expire(record)
        return record

    def create(self, owner, workspace, kind, artifact):
        """Create a trusted application request only for an exact configured owner/workspace and complete concrete artifact."""
        with self._lock:
            self._open()
            scope, raw = scope_for(owner, workspace, kind, artifact)
            if not any(
                spec.owner_id == owner and spec.workspace_id == workspace
                for spec in self.catalog.specifications
            ):
                raise ApprovalError("approval_workspace_not_found", 404)
            for record in self._records.values():
                self._expire(record)
            if len(self._records) >= MAX_REQUESTS:
                retired = next(
                    (
                        identifier
                        for identifier, record in self._records.items()
                        if record.state not in ACTIVE
                    ),
                    None,
                )
                if retired is None:
                    raise ApprovalError("approval_capacity", 429)
                del self._records[retired]
            identifier = uuid4()
            record = ApprovalRecord(
                identifier,
                scope,
                raw,
                secrets.token_urlsafe(32),
                self.clock() + TTL_SECONDS,
                (
                    datetime.now(timezone.utc) + timedelta(seconds=TTL_SECONDS)
                ).isoformat(),
            )
            self._records[identifier] = record
            self._event(record, "pending")
            return identifier

    def review(self, owner, identifier):
        """Return a fresh full owner-only review and bounded event copies with no authority beyond an explicit later decision."""
        with self._lock:
            record = self._find(owner, identifier)
            logger.info("approval_reviewed request_id=%s", identifier)
            return dict(
                request_id=str(identifier),
                owner_id=str(record.scope.owner_id),
                workspace_id=str(record.scope.workspace_id),
                kind=record.scope.kind,
                scope_digest=record.scope.digest,
                artifact_sha256=record.scope.artifact_sha256,
                artifact=record.artifact.decode("utf-8"),
                review_nonce=record.nonce,
                state=record.state,
                expires_at=record.expires_at,
                remaining_seconds=max(0.0, record.deadline - self.clock()),
                events=[
                    dict(event)
                    for event in self._events
                    if event["request_id"] == str(identifier)
                ],
            )

    def decide(self, owner, identifier, decision, digest, nonce):
        """Apply one explicit typed approve/reject decision for the exact displayed scope and unpredictable owner-only nonce."""
        with self._lock:
            record = self._find(owner, identifier)
            if record.state != "pending":
                raise ApprovalError("approval_state_conflict")
            if (
                not isinstance(decision, str)
                or decision not in {"approve", "reject"}
                or not isinstance(digest, str)
                or not re.fullmatch(r"[a-f0-9]{64}", digest)
                or not isinstance(nonce, str)
                or not re.fullmatch(r"[A-Za-z0-9_-]{43}", nonce)
            ):
                raise ApprovalError("approval_decision_invalid", 422)
            if not hmac.compare_digest(
                record.scope.digest, digest
            ) or not hmac.compare_digest(record.nonce, nonce):
                raise ApprovalError("approval_review_changed")
            self._expire(record)
            if record.state != "pending":
                raise ApprovalError("approval_state_conflict")
            record.nonce = None
            return self._event(
                record, "approved" if decision == "approve" else "rejected"
            )

    def consume(self, owner, identifier, workspace, kind, artifact):
        """Consume exactly one unexpired grant for current trusted artifact/scope; mismatches invalidate rather than widen it."""
        with self._lock:
            record = self._find(owner, identifier)
            if record.state != "approved":
                raise ApprovalError("approval_state_conflict")
            current, _ = scope_for(owner, workspace, kind, artifact)
            self._expire(record)
            if record.state != "approved":
                raise ApprovalError("approval_state_conflict")
            if not hmac.compare_digest(current.digest, record.scope.digest):
                self._event(record, "invalidated")
                raise ApprovalError("approval_scope_changed")
            return self._event(record, "consumed")

    def close(self):
        """Invalidate every outstanding grant on shutdown without allowing a restart or another process to revive it."""
        with self._lock:
            self.closing = True
            for record in self._records.values():
                if record.state in ACTIVE:
                    record.nonce = None
                    self._event(record, "invalidated")
            logger.info("approval_store_closed records=%d", len(self._records))
