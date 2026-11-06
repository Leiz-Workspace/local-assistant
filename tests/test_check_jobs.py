"""Verify real durable check snapshot/review history, native root/owner/capacity gates and retained corruption evidence."""

import hashlib
import os
import threading
from pathlib import Path
from uuid import uuid4

import pytest

from src.application.services.approvals import ApprovalStore
from src.application.services.workspace_policy import (
    WorkspaceAccessError,
    WorkspaceSpec,
)
from src.infrastructure import check_jobs as module
from src.infrastructure.check_jobs import CheckJobStore
from src.infrastructure.check_runtime import RuntimeSpec
from src.infrastructure.check_sources import NativeCheckSources
from src.infrastructure.readonly_workspace import WorkspaceCatalog


@pytest.fixture
def job_store(tmp_path):
    """Admit explicit disjoint temporary workspace/check/checkpoint roots and existing pinned local tools only."""
    paths = [tmp_path / name for name in ("workspace", "checks", "checkpoints")]
    for path in paths:
        path.mkdir(mode=0o700)
    raw = b'"""Controlled durable selected source."""\nVALUE = 1\n'
    (paths[0] / "value.py").write_bytes(raw)
    owner, workspace = uuid4(), uuid4()
    catalog = WorkspaceCatalog(
        [WorkspaceSpec(owner, workspace, str(paths[0]), "Controlled checks")]
    )
    sha = "20cf97c5db04ca9c51249dec1a54cbc96c24462df280334ada04b8f3c877b746"
    ruff = next(
        (
            path
            for path in (Path.home() / ".cache/uv/archive-v0").glob("*/bin/ruff")
            if hashlib.sha256(path.read_bytes()).hexdigest() == sha
        ),
        None,
    )
    assert ruff is not None, "Existing pinned Ruff required, no installation fallback"
    spec = RuntimeSpec(
        "/usr/bin/python3.12",
        hashlib.sha256(Path("/usr/bin/python3.12").read_bytes()).hexdigest(),
        "/usr/lib/python3.12",
        str(ruff),
        sha,
    )
    checkpoint = os.open(paths[2], os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    store = CheckJobStore(str(paths[1]), catalog, spec, checkpoint)
    sources = NativeCheckSources(
        catalog,
        owner,
        workspace,
        "python_unittest",
        [dict(path="value.py", expected_sha256=hashlib.sha256(raw).hexdigest())],
    )
    try:
        yield store, sources, paths, spec, checkpoint
    finally:
        sources.close()
        store.close()
        os.close(checkpoint)


def test_actual_durable_snapshot_review_and_pending_link_have_no_execution_or_recovered_authority(
    job_store,
):
    """Persist exact bytes and full private review before any pending grant, then retain historical state across store reopen."""
    store, sources, paths, spec, checkpoint = job_store
    captured = store.capture(sources)
    identifier = captured["identifier"]
    assert (
        paths[1] / identifier.hex / "snapshot/value.py"
    ).read_bytes() == sources.originals["value.py"]
    view = store.read(sources.owner, sources.workspace, identifier)
    assert view["state"] == "captured" and view["approval_id"] is None
    assert not view["recovered_approval"] and not view["live_action_authority"]
    approval = uuid4()
    store.link_approval(sources.owner, sources.workspace, identifier, approval)
    assert store.read(sources.owner, sources.workspace, identifier)[
        "approval_id"
    ] == str(approval)
    store.close()
    reopened = CheckJobStore(str(paths[1]), store.catalog, spec, checkpoint)
    try:
        view = reopened.read(sources.owner, sources.workspace, identifier)
        assert view["state"] == "proposed" and not view["recovered_approval"]
    finally:
        reopened.close()


def test_foreign_owner_lookup_has_no_side_effect_or_snapshot_content_access(
    job_store, monkeypatch
):
    """Reject foreign identity before verifying or exposing private selected bytes."""
    store, sources, _, _, _ = job_store
    captured = store.capture(sources)

    def unexpected(*arguments, **options):
        """Fail if a rejected foreign request reaches snapshot byte verification."""
        pytest.fail("foreign snapshot read")

    monkeypatch.setattr(store, "scan_snapshot", unexpected)
    with pytest.raises(WorkspaceAccessError) as caught:
        store.read(uuid4(), sources.workspace, captured["identifier"])
    assert caught.value.status_code == 404


@pytest.mark.parametrize("kind", ["source_bytes", "extra_directory", "review"])
def test_private_snapshot_or_review_mutation_prevents_trusting_history(job_store, kind):
    """Reject real same-owner fixture corruption instead of silently refreshing immutable action context."""
    store, sources, paths, _, _ = job_store
    identifier = store.capture(sources)["identifier"]
    job = paths[1] / identifier.hex
    if kind == "source_bytes":
        (job / "snapshot/value.py").write_bytes(b"changed")
    elif kind == "extra_directory":
        (job / "snapshot/unknown").mkdir(mode=0o700)
    else:
        (job / "review.json").write_bytes(b"changed review")
    with pytest.raises(WorkspaceAccessError):
        store.read(sources.owner, sources.workspace, identifier)
    assert job.exists()


def test_incomplete_unknown_job_reservation_is_retained_and_blocks_admission(job_store):
    """Charge unacknowledged private data conservatively rather than deleting history or accepting an incomplete record."""
    store, sources, paths, _, _ = job_store
    identifier = uuid4()
    partial = paths[1] / identifier.hex
    partial.mkdir(mode=0o700)
    (partial / "UNACKNOWLEDGED").write_bytes(b"retain")
    with pytest.raises(WorkspaceAccessError) as caught:
        store.capture(sources)
    assert caught.value.code == "checks_storage_recovery_required"
    assert (partial / "UNACKNOWLEDGED").read_bytes() == b"retain"


def test_close_during_active_native_storage_work_keeps_runtime_pins_alive(job_store):
    """Reject premature close before releasing any runtime/root capability still lent to admitted work."""
    store = job_store[0]
    descriptor = store.runtime.fd
    with store.operation():
        with pytest.raises(WorkspaceAccessError) as caught:
            store.close()
        assert caught.value.code == "checks_store_busy"
        os.fstat(descriptor)
    assert not store.closing


def pending_native_job(job_store, *, approve=True):
    """Create a disposable real unittest bundle and actual process-local linked review without production consent."""
    store, original, paths, _, _ = job_store
    raw = b'"""Controlled isolated functional check."""\nimport unittest\nimport value\nclass Fixture(unittest.TestCase):\n    """Check only selected disposable code."""\n    def test_value(self):\n        """Observe the selected source value inside the sandbox."""\n        self.assertEqual(value.VALUE,1)\n'
    (paths[0] / "test_value.py").write_bytes(raw)
    files = [
        dict(
            path="value.py",
            expected_sha256=hashlib.sha256(
                (paths[0] / "value.py").read_bytes()
            ).hexdigest(),
        ),
        dict(path="test_value.py", expected_sha256=hashlib.sha256(raw).hexdigest()),
    ]
    sources = NativeCheckSources(
        store.catalog, original.owner, original.workspace, "python_unittest", files
    )
    captured = store.capture(sources)
    approvals = ApprovalStore(store.catalog)
    request = approvals.create(
        sources.owner, sources.workspace, "run_checks", captured["review"]
    )
    store.link_approval(
        sources.owner, sources.workspace, captured["identifier"], request
    )
    if approve:
        review = approvals.review(sources.owner, request)
        approvals.decide(
            sources.owner,
            request,
            "approve",
            review["scope_digest"],
            review["review_nonce"],
        )
    return sources, captured["identifier"], approvals, request


def test_actual_fresh_grant_executes_and_persists_without_quality_or_replay_authority(
    job_store,
):
    """Consume one actual approved scope, execute the selected unittest and retain its exact source-safe observation."""
    store = job_store[0]
    sources, identifier, approvals, request = pending_native_job(job_store)
    try:
        evidence = store.run_attempt(
            sources, identifier, request, approvals, threading.Event(), {}
        )
        assert evidence["observation"]["exit_code"] == 0
        assert (
            evidence["observation"]["started_acknowledged"]
            and not evidence["observation"]["quality_evaluated"]
        )
        assert sources.closed and not evidence["terminal_persistence_uncertain"]
        view = store.read(sources.owner, sources.workspace, identifier)
        assert (
            view["state"] == "observed"
            and view["observation"] == evidence["observation"]
        )
        assert approvals.review(sources.owner, request)["state"] == "consumed"
        with pytest.raises(WorkspaceAccessError) as caught:
            store.run_attempt(
                sources, identifier, request, approvals, threading.Event(), {}
            )
        assert caught.value.code == "checks_job_state_conflict"
    finally:
        sources.close()
        approvals.close()


def test_pending_or_wrong_linked_review_never_starts_native_work(
    job_store, monkeypatch
):
    """Keep an unapproved job reviewable and reject other request IDs before source closure or command execution."""
    store = job_store[0]
    sources, identifier, approvals, request = pending_native_job(
        job_store, approve=False
    )

    def forbidden_run(instance):
        """Fail if an unapproved request reaches the native launcher."""
        pytest.fail("unapproved native run")

    monkeypatch.setattr(module.NativeChecks, "run", forbidden_run)
    try:
        for approval in (request, uuid4()):
            with pytest.raises(WorkspaceAccessError):
                store.run_attempt(
                    sources, identifier, approval, approvals, threading.Event(), {}
                )
        assert not sources.closed
        assert (
            store.read(sources.owner, sources.workspace, identifier)["state"]
            == "proposed"
        )
        assert approvals.review(sources.owner, request)["state"] == "pending"
    finally:
        sources.close()
        approvals.close()


def test_changed_source_is_failed_before_consuming_the_exact_approved_grant(job_store):
    """Reject stale original bytes without refreshing scope, executing code or consuming the still-approved grant."""
    store, _, paths, _, _ = job_store
    sources, identifier, approvals, request = pending_native_job(job_store)
    (paths[0] / "value.py").write_bytes(
        b'"""Controlled changed source."""\nVALUE = 2\n'
    )
    evidence = {}
    try:
        with pytest.raises(WorkspaceAccessError) as caught:
            store.run_attempt(
                sources, identifier, request, approvals, threading.Event(), evidence
            )
        assert caught.value.code == "checks_source_changed"
        assert sources.closed and evidence["observation"] is None
        assert approvals.review(sources.owner, request)["state"] == "approved"
        assert (
            store.read(sources.owner, sources.workspace, identifier)["state"]
            == "failed"
        )
    finally:
        sources.close()
        approvals.close()


@pytest.mark.parametrize(
    "stage", ["intent", "terminal_before_write", "terminal_lost_ack"]
)
def test_native_journal_faults_preserve_prelaunch_and_postexecution_truth(
    job_store, monkeypatch, stage
):
    """Reject prelaunch persistence failure and retain actual results across terminal write/ack uncertainty without retry."""
    store = job_store[0]
    sources, identifier, approvals, request = pending_native_job(job_store)
    original = store.storage.replace_journal

    def fault(directory, value):
        """Inject one selected stage while preserving actual native writes and acknowledgement ordering."""
        if stage == "intent" and value["state"] == "starting":
            raise OSError("controlled intent persistence failure")
        if stage.startswith("terminal") and value["state"] == "observed":
            if stage == "terminal_lost_ack":
                original(directory, value)
            raise OSError("controlled terminal persistence acknowledgement failure")
        return original(directory, value)

    monkeypatch.setattr(store.storage, "replace_journal", fault)
    evidence = {}
    try:
        if stage == "intent":
            with pytest.raises(OSError):
                store.run_attempt(
                    sources, identifier, request, approvals, threading.Event(), evidence
                )
            assert evidence["observation"] is None
            assert approvals.review(sources.owner, request)["state"] == "approved"
        else:
            result = store.run_attempt(
                sources, identifier, request, approvals, threading.Event(), evidence
            )
            assert result["observation"]["exit_code"] == 0
            assert result["terminal_persistence_uncertain"]
            assert approvals.review(sources.owner, request)["state"] == "consumed"
            view = store.read(sources.owner, sources.workspace, identifier)
            assert view["state"] == (
                "observed" if stage == "terminal_lost_ack" else "starting"
            )
        assert sources.closed
    finally:
        sources.close()
        approvals.close()
