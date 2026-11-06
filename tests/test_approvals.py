"""Verify real process-local scoped approvals, exact controlled expiry, one-shot concurrency and private bounded events."""

import hashlib
import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from test_workspace_reader import source_workspace as source_workspace

from src.application.services.approvals import ApprovalError, ApprovalStore, scope_for

ARTIFACT = b'{"description":"Review a disposable fixture patch","diff":"-return value + 1\\n+return value * 2"}'


@pytest.fixture
def approvals(source_workspace):
    """Provide a real accepted catalog and a disclosed controllable monotonic clock without source reads."""
    clock = [0.0]
    return (
        ApprovalStore(source_workspace[0], clock=lambda: clock[0]),
        source_workspace[1],
        clock,
    )


def request_for(store, spec, artifact=ARTIFACT, kind="patch"):
    """Create one trusted application request and obtain the full owner-only review without approving it implicitly."""
    identifier = store.create(spec.owner_id, spec.workspace_id, kind, artifact)
    return identifier, store.review(spec.owner_id, identifier)


def approve(store, spec, identifier, review):
    """Submit an explicit synthetic owner decision for exactly the reviewed digest and nonce."""
    return store.decide(
        spec.owner_id,
        identifier,
        "approve",
        review["scope_digest"],
        review["review_nonce"],
    )


def test_explicit_review_decision_and_exact_one_shot_consumption(approvals):
    """Require pending review, explicit approval and exact current content before one immutable audit receipt."""
    store, spec, _ = approvals
    identifier, review = request_for(store, spec)
    assert review["state"] == "pending" and review["remaining_seconds"] == 120
    assert (
        review["artifact"] == ARTIFACT.decode()
        and review["artifact_sha256"] == hashlib.sha256(ARTIFACT).hexdigest()
    )
    assert len(review["review_nonce"]) == 43 and len(review["scope_digest"]) == 64
    with pytest.raises(ApprovalError, match="approval_state_conflict"):
        store.consume(spec.owner_id, identifier, spec.workspace_id, "patch", ARTIFACT)
    event = approve(store, spec, identifier, review)
    assert event["state"] == "approved" and "review_nonce" not in event
    assert store.review(spec.owner_id, identifier)["review_nonce"] is None
    receipt = store.consume(
        spec.owner_id, identifier, spec.workspace_id, "patch", ARTIFACT
    )
    assert (
        receipt["state"] == "consumed"
        and receipt["scope_digest"] == review["scope_digest"]
    )
    with pytest.raises(ApprovalError, match="approval_state_conflict"):
        store.consume(spec.owner_id, identifier, spec.workspace_id, "patch", ARTIFACT)
    with pytest.raises(ApprovalError, match="approval_state_conflict"):
        approve(store, spec, identifier, review)
    assert [
        row["state"] for row in store.review(spec.owner_id, identifier)["events"]
    ] == ["pending", "approved", "consumed"]


@pytest.mark.parametrize("mode", ["pending", "approved"])
def test_exact_monotonic_expiry_cannot_be_extended_by_wall_metadata(approvals, mode):
    """Expire at exactly120 seconds and log expiration once even if display time is deliberately changed."""
    store, spec, clock = approvals
    identifier, review = request_for(store, spec)
    clock[0] = 119.999
    if mode == "approved":
        approve(store, spec, identifier, review)
    store._records[identifier].expires_at = "2999-01-01T00:00:00+00:00"
    clock[0] = 120.0
    with pytest.raises(ApprovalError, match="approval_state_conflict"):
        if mode == "pending":
            approve(store, spec, identifier, review)
        else:
            store.consume(
                spec.owner_id, identifier, spec.workspace_id, "patch", ARTIFACT
            )
    first = store.review(spec.owner_id, identifier)
    second = store.review(spec.owner_id, identifier)
    assert first["state"] == "expired" and first["remaining_seconds"] == 0
    assert (
        first["events"] == second["events"]
        and sum(row["state"] == "expired" for row in first["events"]) == 1
    )


@pytest.mark.parametrize("change", ["workspace", "kind", "artifact"])
def test_scope_change_invalidates_instead_of_widening_or_reusing(approvals, change):
    """Invalidate exact-scope grants after a changed action and refuse later restoration/replay of the old grant."""
    store, spec, _ = approvals
    identifier, review = request_for(store, spec)
    approve(store, spec, identifier, review)
    with pytest.raises(ApprovalError, match="approval_scope_changed"):
        store.consume(
            spec.owner_id,
            identifier,
            uuid4() if change == "workspace" else spec.workspace_id,
            "run_checks" if change == "kind" else "patch",
            ARTIFACT + b" " if change == "artifact" else ARTIFACT,
        )
    assert store.review(spec.owner_id, identifier)["state"] == "invalidated"
    with pytest.raises(ApprovalError):
        store.consume(spec.owner_id, identifier, spec.workspace_id, "patch", ARTIFACT)


def test_foreign_unknown_and_untyped_owner_never_mutate_events(approvals):
    """Deny foreign IDs before lazy expiration/events and preserve indistinguishable not-found behavior."""
    store, spec, clock = approvals
    identifier, _ = request_for(store, spec)
    clock[0] = 121.0
    events = list(store._events)
    for owner, request_id in [
        (uuid4(), identifier),
        (spec.owner_id, uuid4()),
        (str(spec.owner_id), identifier),
    ]:
        with pytest.raises(ApprovalError, match="approval_not_found") as caught:
            store.review(owner, request_id)
        assert caught.value.status_code == 404 and list(store._events) == events


@pytest.mark.parametrize(
    "fault",
    ["nonce", "digest", "decision_type", "digest_type", "nonce_type", "unicode_digest"],
)
def test_invalid_decisions_cannot_approve_or_mutate_scope(approvals, fault):
    """Reject wrong or malformed review echoes without implicit consent or private diagnostics."""
    store, spec, _ = approvals
    identifier, review = request_for(store, spec)
    decision, digest, nonce = "approve", review["scope_digest"], review["review_nonce"]
    if fault == "nonce":
        nonce = "a" * 43
    elif fault == "digest":
        digest = "0" * 64
    elif fault == "decision_type":
        decision = []
    elif fault == "digest_type":
        digest = []
    elif fault == "nonce_type":
        nonce = []
    else:
        digest = "á" * 64
    with pytest.raises(ApprovalError):
        store.decide(spec.owner_id, identifier, decision, digest, nonce)
    assert store.review(spec.owner_id, identifier)["state"] == "pending"


def test_rejection_cannot_be_replayed_or_consumed(approvals):
    """Make an explicit negative decision terminal and revoke its review nonce immediately."""
    store, spec, _ = approvals
    identifier, review = request_for(store, spec)
    store.decide(
        spec.owner_id,
        identifier,
        "reject",
        review["scope_digest"],
        review["review_nonce"],
    )
    with pytest.raises(ApprovalError):
        approve(store, spec, identifier, review)
    with pytest.raises(ApprovalError):
        store.consume(spec.owner_id, identifier, spec.workspace_id, "patch", ARTIFACT)
    assert store.review(spec.owner_id, identifier)["state"] == "rejected"


def test_artifact_and_event_copies_cannot_change_approved_scope(approvals):
    """Copy mutable caller bytes/review dictionaries so later mutations do not alter the reviewed artifact."""
    store, spec, _ = approvals
    raw = bytearray(ARTIFACT)
    identifier, review = request_for(store, spec, raw)
    raw[:] = b"changed"
    review["artifact"] = "untrusted replacement"
    review["events"][0]["state"] = "approved"
    current = store.review(spec.owner_id, identifier)
    assert (
        current["artifact"] == ARTIFACT.decode()
        and current["events"][0]["state"] == "pending"
    )
    approve(store, spec, identifier, current)
    assert (
        store.consume(spec.owner_id, identifier, spec.workspace_id, "patch", ARTIFACT)[
            "state"
        ]
        == "consumed"
    )


def test_fixed_capacity_terminal_retirement_and_event_bounds(approvals):
    """Exercise actual64-request capacity, terminal eviction and256-event bound without evicting active grants."""
    store, spec, _ = approvals
    requests = [request_for(store, spec) for _ in range(64)]
    with pytest.raises(ApprovalError, match="approval_capacity") as caught:
        request_for(store, spec)
    assert caught.value.status_code == 429
    first, review = requests[0]
    store.decide(
        spec.owner_id, first, "reject", review["scope_digest"], review["review_nonce"]
    )
    request_for(store, spec)
    with pytest.raises(ApprovalError, match="approval_not_found"):
        store.review(spec.owner_id, first)
    assert len(store._records) == 64
    for identifier, review in requests[1:]:
        store.decide(
            spec.owner_id,
            identifier,
            "reject",
            review["scope_digest"],
            review["review_nonce"],
        )
    for _ in range(100):
        identifier, review = request_for(store, spec)
        approve(store, spec, identifier, review)
        store.consume(spec.owner_id, identifier, spec.workspace_id, "patch", ARTIFACT)
    assert len(store._records) == 64 and len(store._events) == 256


def test_shutdown_restart_and_concurrent_consumption_are_fail_closed(approvals):
    """Serialize real competing thread consumption and ensure process-local grants cannot survive teardown/restart."""
    store, spec, _ = approvals
    identifier, review = request_for(store, spec)
    approve(store, spec, identifier, review)
    barrier = threading.Barrier(2)

    def consume():
        """Attempt the exact same approved artifact concurrently through the actual synchronized store."""
        barrier.wait(2)
        try:
            return store.consume(
                spec.owner_id, identifier, spec.workspace_id, "patch", ARTIFACT
            )["state"]
        except ApprovalError:
            return "rejected"

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(lambda _: consume(), range(2)))
    assert sorted(outcomes) == ["consumed", "rejected"]
    pending, _ = request_for(store, spec)
    store.close()
    with pytest.raises(ApprovalError, match="approval_unavailable"):
        store.review(spec.owner_id, pending)
    fresh = ApprovalStore(store.catalog)
    with pytest.raises(ApprovalError, match="approval_not_found"):
        fresh.review(spec.owner_id, identifier)


def test_private_audit_and_catalog_authorization_before_source_access(
    approvals, monkeypatch, caplog
):
    """Audit stable metadata only and authorize configuration scope without ever reading repository sources."""
    store, spec, _ = approvals
    caplog.set_level(logging.INFO)

    def forbidden(*arguments):
        """Prove approval creation/review does not open a filesystem capability."""
        pytest.fail("approval opened source root")

    monkeypatch.setattr(store.catalog, "open", forbidden)
    with pytest.raises(ApprovalError, match="approval_workspace_not_found"):
        store.create(uuid4(), spec.workspace_id, "patch", ARTIFACT)
    identifier, review = request_for(store, spec)
    approve(store, spec, identifier, review)
    assert "disposable" not in caplog.text and "return value" not in caplog.text
    assert review["review_nonce"] not in caplog.text and str(identifier) in caplog.text


@pytest.mark.parametrize("artifact", [b"", b" ", b"\xff", b"x" * 32769, None])
def test_invalid_artifacts_and_types_cannot_create_scope(approvals, artifact):
    """Reject empty/binary/unbounded review data before creating any grant or audit request."""
    store, spec, _ = approvals
    with pytest.raises(ApprovalError):
        scope_for(spec.owner_id, spec.workspace_id, "patch", artifact)
    assert not store._records


@pytest.mark.parametrize("phase", ["decision", "consume"])
def test_deadline_crossing_during_validation_cannot_publish_grant(approvals, phase):
    """Advance a disclosed clock between owner lookup and final transition and refuse the now-expired authorization."""
    store, spec, _ = approvals
    identifier, review = request_for(store, spec)
    if phase == "consume":
        approve(store, spec, identifier, review)
    ticks = iter([119.999, 120.0])

    def crossing_clock():
        """Expose exactly the authorization-boundary clock crossing without a wall-clock sleep."""
        return next(ticks, 120.0)

    store.clock = crossing_clock
    with pytest.raises(ApprovalError, match="approval_state_conflict"):
        if phase == "decision":
            approve(store, spec, identifier, review)
        else:
            store.consume(
                spec.owner_id, identifier, spec.workspace_id, "patch", ARTIFACT
            )
    events = store.review(spec.owner_id, identifier)["events"]
    assert events[-1]["state"] == "expired"
    assert not any(event["state"] == "consumed" for event in events)
