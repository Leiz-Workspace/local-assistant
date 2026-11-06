"""Verify actual approved single-file native replacement, byte/metadata/version boundaries and precise commit-failure receipts."""

import hashlib
import os
import stat
import threading
from uuid import uuid4

import pytest

from src.application.services.approvals import ApprovalStore
from src.application.services.workspace_policy import (
    WorkspaceAccessError,
    WorkspaceSpec,
)
from src.infrastructure import atomic_patch as module
from src.infrastructure.atomic_patch import NativePatch
from src.infrastructure.readonly_workspace import WorkspaceCatalog


@pytest.fixture
def patch_fixture(tmp_path):
    """Create explicitly owned temporary source/catalog and close every retained native proposal pin on teardown."""
    root = tmp_path / "repo"
    root.mkdir(mode=0o700)
    (root / "src").mkdir(mode=0o755)
    source = root / "src/main.py"
    raw = b'"""Owned synthetic source."""\r\nVALUE = "Cedar"\r\n'
    source.write_bytes(raw)
    source.chmod(0o644)
    spec = WorkspaceSpec(uuid4(), uuid4(), str(root), "patch-fixture")
    catalog = WorkspaceCatalog([spec])
    store = ApprovalStore(catalog)
    proposals = []

    def build(
        replacement='"""Owned synthetic source."""\r\nVALUE = "Birch"\r\n', **options
    ):
        """Capture a new proposal using the known original fixture digest rather than reading any substituted target."""
        values = dict(
            path="src/main.py",
            expected_sha256=hashlib.sha256(raw).hexdigest(),
            replacement=replacement,
        )
        values.update(options)
        proposal = NativePatch(catalog, spec.owner_id, spec.workspace_id, **values)
        proposals.append(proposal)
        return proposal

    yield root, source, raw, spec, store, build
    for proposal in proposals:
        proposal.close()


def authorize(store, proposal):
    """Perform an explicit synthetic owner review/decision for this exact native artifact without applying it."""
    identifier = proposal.register_approval(store)
    review = store.review(proposal.owner, identifier)
    store.decide(
        proposal.owner,
        identifier,
        "approve",
        review["scope_digest"],
        review["review_nonce"],
    )
    return identifier


def test_proposal_and_pending_approval_never_write_source_or_temporary_entries(
    patch_fixture,
):
    """Expose the full exact proposal/diff while proving creation and an unapproved apply leave all native names/bytes unchanged."""
    root, source, raw, _, store, build = patch_fixture
    names = set((root / "src").iterdir())
    proposal = build()
    identifier = proposal.register_approval(store)
    review = store.review(proposal.owner, identifier)
    assert '"replacement"' in review["artifact"] and "a/src/main.py" in proposal.diff
    assert proposal.public()["original"].encode() == raw
    with pytest.raises(WorkspaceAccessError, match="patch_approval_required"):
        proposal.apply(store, identifier)
    assert source.read_bytes() == raw and set((root / "src").iterdir()) == names
    assert (
        proposal.state == "proposed"
        and store.review(proposal.owner, identifier)["state"] == "pending"
    )


@pytest.mark.parametrize(
    "replacement",
    [
        '"""Unicode fixture."""\nVALUE = "chào 𝄞"\n',
        "new text without final LF",
        "",
        "CRLF\r\nkept\r\n",
    ],
)
def test_actual_atomic_approved_replacement_preserves_exact_bytes_mode_and_group(
    patch_fixture, replacement
):
    """Write only the approved file with exact Unicode/CRLF/empty/no-final-LF bytes and preserved eligible UID/GID/mode."""
    root, source, raw, _, store, build = patch_fixture
    before = source.stat()
    proposal = build(replacement)
    identifier = authorize(store, proposal)
    result = proposal.apply(store, identifier)
    after = source.stat()
    assert result["state"] == "applied" and result["applied"] is True
    assert result["new_sha256"] == hashlib.sha256(replacement.encode()).hexdigest()
    assert source.read_bytes() == replacement.encode()
    assert after.st_ino != before.st_ino and stat.S_IMODE(after.st_mode) == 0o644
    assert (after.st_uid, after.st_gid) == (before.st_uid, before.st_gid)
    assert not list((root / "src").glob(".assistant-patch-*"))
    assert store.review(proposal.owner, identifier)["state"] == "consumed"
    with pytest.raises(WorkspaceAccessError):
        proposal.apply(store, identifier)
    assert proposal.public()["receipt"] == result
    result["uncertainties"].append("untrusted-caller")
    assert "untrusted-caller" not in proposal.public()["receipt"]["uncertainties"]
    if not replacement.endswith("\n") and replacement:
        assert "\\ No newline at end of file" in proposal.diff


@pytest.mark.parametrize(
    "fault", ["source", "metadata", "root", "parent", "hardlink", "symlink"]
)
def test_changed_version_or_unsafe_native_target_never_applies(
    patch_fixture, fault, tmp_path
):
    """Reject actual post-review source/root/parent/metadata/link changes before writing any replacement."""
    root, source, raw, _, store, build = patch_fixture
    proposal = build()
    identifier = authorize(store, proposal)
    unrelated = tmp_path / "outside"
    unrelated.write_text("UNRELATED-CANARY")
    if fault == "source":
        source.write_text("externally changed\n")
    elif fault == "metadata":
        source.chmod(0o600)
    elif fault == "root":
        root.rename(tmp_path / "old-root")
        root.mkdir(mode=0o700)
    elif fault == "parent":
        (root / "src").rename(root / "old-src")
        (root / "src").mkdir(mode=0o755)
        source.write_bytes(raw)
    else:
        source.unlink()
        if fault == "hardlink":
            source.hardlink_to(unrelated)
        else:
            source.symlink_to(unrelated)
    with pytest.raises((WorkspaceAccessError, OSError)):
        proposal.apply(store, identifier)
    assert unrelated.read_text() == "UNRELATED-CANARY"
    assert store.review(proposal.owner, identifier)["state"] == "approved"
    assert not list(root.rglob(".assistant-patch-*"))


@pytest.mark.parametrize(
    "fault",
    [
        "hidden",
        "traversal",
        "absolute",
        "digest",
        "binary",
        "large",
        "no_change",
        "world_write",
        "readonly",
        "parent_write",
        "xattr",
    ],
)
def test_invalid_or_unsupported_proposal_rejects_without_review(patch_fixture, fault):
    """Refuse unsafe paths/source/metadata and mismatched/no-op proposals without creating approval or temporary files."""
    root, source, raw, _, store, build = patch_fixture
    options = {}
    if fault in {"hidden", "traversal", "absolute"}:
        options["path"] = {
            "hidden": ".env",
            "traversal": "../outside",
            "absolute": "/etc/passwd",
        }[fault]
    elif fault == "digest":
        options["expected_sha256"] = "0" * 64
    elif fault == "binary":
        source.write_bytes(b"\x00binary")
    elif fault == "large":
        source.write_bytes(b"x" * 8193)
    elif fault == "no_change":
        options["replacement"] = raw.decode()
    elif fault == "world_write":
        source.chmod(0o666)
    elif fault == "readonly":
        source.chmod(0o444)
    elif fault == "parent_write":
        (root / "src").chmod(0o777)
    else:
        os.setxattr(source, "user.patch-fixture", b"metadata")
    with pytest.raises((WorkspaceAccessError, OSError)):
        build(**options)
    assert not store._records and not list(root.rglob(".assistant-patch-*"))


@pytest.mark.parametrize("fault", ["file_fsync", "rename", "cancel_before_commit"])
def test_precommit_failures_preserve_source_and_clean_owned_temporary(
    patch_fixture, monkeypatch, fault
):
    """Inject only the native pre-commit failure and verify original bytes plus honest approval-consumption state."""
    root, source, raw, _, store, build = patch_fixture
    proposal = build()
    identifier = authorize(store, proposal)
    stop = threading.Event()
    if fault == "file_fsync":
        original = module.os.fsync

        def fail_file(descriptor):
            """Fail only a regular prepared file sync while preserving other actual native sync operations."""
            if stat.S_ISREG(os.fstat(descriptor).st_mode):
                raise OSError("CONTROLLED-PRIVATE-FSYNC")
            return original(descriptor)

        monkeypatch.setattr(module.os, "fsync", fail_file)
    elif fault == "rename":

        def fail_rename(*arguments, **options):
            """Fail before the actual rename without changing either acknowledged-owned inode."""
            raise OSError("CONTROLLED-PRIVATE-RENAME")

        monkeypatch.setattr(module.os, "replace", fail_rename)
    else:
        original = store.consume

        def cancel_after_consume(*arguments):
            """Consume the exact valid approval then signal cancellation before the actual rename."""
            result = original(*arguments)
            stop.set()
            return result

        monkeypatch.setattr(store, "consume", cancel_after_consume)
    with pytest.raises((OSError, WorkspaceAccessError)):
        proposal.apply(store, identifier, stop)
    assert source.read_bytes() == raw and not list(
        (root / "src").glob(".assistant-patch-*")
    )
    assert proposal.state == "failed" and proposal.receipt is None
    assert store.review(proposal.owner, identifier)["state"] == (
        "approved" if fault == "file_fsync" else "consumed"
    )


@pytest.mark.parametrize("fault", ["dir_fsync", "rename_ack"])
def test_postcommit_faults_preserve_authoritative_applied_receipt(
    patch_fixture, monkeypatch, fault
):
    """Retain actual committed bytes/receipt after directory-sync or syscall-acknowledgement failure instead of claiming no change."""
    root, source, _, _, store, build = patch_fixture
    proposal = build()
    identifier = authorize(store, proposal)
    if fault == "dir_fsync":
        original = module.os.fsync

        def fail_directory(descriptor):
            """Fail only the actual parent-directory sync after file replacement has committed."""
            if stat.S_ISDIR(os.fstat(descriptor).st_mode):
                raise OSError("CONTROLLED-PRIVATE-DIR-FSYNC")
            return original(descriptor)

        monkeypatch.setattr(module.os, "fsync", fail_directory)
    else:
        original = module.os.replace

        def lost_ack(*arguments, **options):
            """Perform the real atomic rename then simulate an acknowledgement error for inode-based reconciliation."""
            original(*arguments, **options)
            raise OSError("CONTROLLED-PRIVATE-RENAME-ACK")

        monkeypatch.setattr(module.os, "replace", lost_ack)
    receipt = proposal.apply(store, identifier)
    assert receipt["applied"] is True and source.read_bytes() == proposal.replacement
    assert receipt["state"] == (
        "applied_durability_uncertain" if fault == "dir_fsync" else "applied"
    )
    assert receipt["rename_ack_reconciled"] == (fault == "rename_ack")
    assert not list((root / "src").glob(".assistant-patch-*"))


@pytest.mark.parametrize("fault", ["source", "prepared_bytes", "prepared_name"])
def test_last_fence_rejects_changes_after_preparation(
    patch_fixture, monkeypatch, fault
):
    """Change real source or prepared temporary entries at the fsync boundary and reject before approval consumption."""
    root, source, raw, _, store, build = patch_fixture
    proposal = build()
    identifier = authorize(store, proposal)
    original = module.os.fsync
    changed = []

    def alter(descriptor):
        """Inject one actual native mutation after prepared-file fsync without modifying host production files."""
        result = original(descriptor)
        if stat.S_ISREG(os.fstat(descriptor).st_mode) and not changed:
            changed.append(True)
            if fault == "source":
                source.write_bytes(b"independent edit\n")
            elif fault == "prepared_bytes":
                os.pwrite(descriptor, b"UNAPPROVED", 0)
            else:
                entry = next((root / "src").glob(".assistant-patch-*"))
                entry.unlink()
                entry.write_bytes(b"UNRELATED-TEMPORARY-CANARY")
        return result

    monkeypatch.setattr(module.os, "fsync", alter)
    with pytest.raises(WorkspaceAccessError):
        proposal.apply(store, identifier)
    assert source.read_bytes() == (b"independent edit\n" if fault == "source" else raw)
    assert store.review(proposal.owner, identifier)["state"] == "approved"
    temporary = list((root / "src").glob(".assistant-patch-*"))
    if fault == "prepared_name":
        assert (
            len(temporary) == 1
            and temporary[0].read_bytes() == b"UNRELATED-TEMPORARY-CANARY"
        )
        assert proposal.error_code == "patch_cleanup_uncertain"
    else:
        assert not temporary


def test_actual_cooperating_writer_lock_denies_before_temporary_write(patch_fixture):
    """Hold an independent real advisory lock and reject patch admission without consuming its approved grant."""
    root, source, raw, _, store, build = patch_fixture
    proposal = build()
    identifier = authorize(store, proposal)
    with source.open("rb") as locked:
        module.fcntl.flock(locked.fileno(), module.fcntl.LOCK_EX | module.fcntl.LOCK_NB)
        with pytest.raises(WorkspaceAccessError, match="patch_busy"):
            proposal.apply(store, identifier)
    assert source.read_bytes() == raw and not list(root.rglob(".assistant-patch-*"))
    assert store.review(proposal.owner, identifier)["state"] == "approved"


def test_unknown_rename_outcome_preserves_uncertainty_and_no_retry(
    patch_fixture, monkeypatch
):
    """Simulate an uncooperative native target change during a lost rename acknowledgement and report unknown instead of success/failure."""
    root, source, _, _, store, build = patch_fixture
    proposal = build()
    identifier = authorize(store, proposal)

    def unacknowledged(*arguments, **options):
        """Remove the target at the syscall boundary so the local commit outcome cannot be established."""
        source.unlink()
        raise OSError("CONTROLLED-PRIVATE-UNKNOWN-RENAME")

    monkeypatch.setattr(module.os, "replace", unacknowledged)
    result = proposal.apply(store, identifier)
    assert result["state"] == "outcome_unknown" and result["applied"] is None
    assert not source.exists() and not list(root.rglob(".assistant-patch-*"))
    assert store.review(proposal.owner, identifier)["state"] == "consumed"
    with pytest.raises(WorkspaceAccessError):
        proposal.apply(store, identifier)


@pytest.mark.parametrize("fault", ["expiry", "deadline", "unlink"])
def test_expiry_deadline_and_unlink_failure_are_honest(
    patch_fixture, monkeypatch, fault
):
    """Exercise exact monotonic boundaries and an owned-temp cleanup failure without claiming successful replacement."""
    root, source, raw, _, store, build = patch_fixture
    proposal = build()
    identifier = authorize(store, proposal)
    original = module.os.fsync

    def fail(descriptor):
        """Inject expiry/deadline or failed owned-temp unlink only after a real regular-file fsync."""
        original(descriptor)
        if stat.S_ISREG(os.fstat(descriptor).st_mode):
            if fault == "expiry":
                proposal.clock = lambda: proposal.expires
            elif fault == "deadline":
                proposal.clock = lambda: proposal.expires - 1
            else:
                raise OSError("CONTROLLED-PRIVATE-PREPARE")

    monkeypatch.setattr(module.os, "fsync", fail)
    if fault == "unlink":
        original_unlink = module.os.unlink

        def deny_owned(path, **options):
            """Deny only this fixture's acknowledged temporary cleanup and preserve all unrelated unlink operations."""
            if str(path).startswith(".assistant-patch-"):
                raise OSError("CONTROLLED-PRIVATE-UNLINK")
            return original_unlink(path, **options)

        monkeypatch.setattr(module.os, "unlink", deny_owned)
    with pytest.raises(WorkspaceAccessError):
        proposal.apply(store, identifier)
    assert source.read_bytes() == raw and proposal.receipt is None
    assert bool(list(root.rglob(".assistant-patch-*"))) == (fault == "unlink")
    assert store.review(proposal.owner, identifier)["state"] == "approved"
