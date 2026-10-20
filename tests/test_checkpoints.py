"""Verify actual durable Git source checkpoints, quotas, owner/content binding and immutable action evidence on temporary sources."""

from uuid import uuid4

import pytest
from test_atomic_patch import authorize
from test_atomic_patch import patch_fixture as patch_fixture

from src.application.services.workspace_policy import WorkspaceAccessError
from src.infrastructure.checkpoint_storage import canonical, decode_record
from src.infrastructure.checkpoints import CheckpointStore


@pytest.fixture
def checkpoint_store(tmp_path, patch_fixture):
    """Create one explicitly private durable root outside the source fixture and retain backup files after native store close."""
    path = tmp_path / "checkpoint-store"
    path.mkdir(mode=0o700)
    store = CheckpointStore(path, patch_fixture[4].catalog)
    yield store, path
    store.close()


def test_actual_git_checkpoint_journal_and_restart_preserve_original_bytes(
    checkpoint_store, patch_fixture
):
    """Capture an actual committed source, apply the approved edit once and read durable original/receipt after reopening storage."""
    store, path = checkpoint_store
    _, source, raw, spec, approvals, build = patch_fixture
    proposal = build()
    identifier = store.capture(proposal)
    snapshot = store.read(spec.owner_id, spec.workspace_id, identifier)
    assert (
        snapshot["original"].encode() == raw and snapshot["journal"]["state"] == "ready"
    )
    assert source.read_bytes() == raw and not approvals._records
    approval = authorize(approvals, proposal)
    store.transition(proposal, identifier)
    result = proposal.apply(approvals, approval)
    store.transition(proposal, identifier, finish=True)
    assert result["applied"] is True and source.read_bytes() == proposal.replacement
    store.close()
    reopened = CheckpointStore(path, approvals.catalog)
    try:
        after = reopened.read(spec.owner_id, spec.workspace_id, identifier)
        assert (
            after["original"].encode() == raw and after["journal"]["receipt"] == result
        )
        assert not after["recovered_approval"] and not after["current_source_observed"]
        assert len(reopened.list(spec.owner_id, spec.workspace_id)) == 1
    finally:
        reopened.close()


@pytest.mark.parametrize("fault", ["owner", "workspace", "unknown", "typed"])
def test_owner_scope_denial_is_uniform_before_historical_source_read(
    checkpoint_store, patch_fixture, fault
):
    """Deny forged scopes and unknown checkpoints without exposing stored source bytes or modifying journal states."""
    store, _ = checkpoint_store
    _, source, raw, spec, _, build = patch_fixture
    identifier = store.capture(build())
    with pytest.raises(WorkspaceAccessError, match="checkpoint_not_found"):
        store.read(
            uuid4()
            if fault == "owner"
            else str(spec.owner_id)
            if fault == "typed"
            else spec.owner_id,
            uuid4() if fault == "workspace" else spec.workspace_id,
            uuid4() if fault == "unknown" else identifier,
        )
    assert source.read_bytes() == raw
    assert (
        store.read(spec.owner_id, spec.workspace_id, identifier)["journal"]["state"]
        == "ready"
    )


@pytest.mark.parametrize("fault", ["object", "config", "journal", "record", "extra"])
def test_changed_private_backup_is_not_silently_used_or_cleaned(
    checkpoint_store, patch_fixture, fault
):
    """Mutate real private storage and reject integrity/state corruption while preserving unacknowledged entries as recovery warnings."""
    store, path = checkpoint_store
    _, source, raw, spec, _, build = patch_fixture
    proposal = build()
    identifier = store.capture(proposal)
    directory = path / identifier.hex
    if fault == "object":
        object_file = next(
            p for p in (directory / "repo/objects").rglob("*") if p.is_file()
        )
        object_file.write_bytes(b"corrupted private object")
    elif fault == "config":
        (directory / "repo/config").write_bytes(b"[include]\n path=/home/forbidden\n")
    elif fault == "journal":
        journal = decode_record((directory / "journal.json").read_bytes())
        journal["record_sha256"] = "0" * 64
        (directory / "journal.json").write_bytes(canonical(journal))
    elif fault == "record":
        record = decode_record((directory / "record.json").read_bytes())
        record["metadata"]["base_sha256"] = "0" * 64
        (directory / "record.json").write_bytes(canonical(record))
    else:
        (directory / ".journal-unknown.tmp").write_bytes(b"UNRELATED-PRIVATE-CANARY")
    if fault == "extra":
        snapshot = store.read(spec.owner_id, spec.workspace_id, identifier)
        assert snapshot["recovery_warnings"] == ["unacknowledged_private_entry"]
    else:
        with pytest.raises(WorkspaceAccessError):
            store.read(spec.owner_id, spec.workspace_id, identifier)
    with pytest.raises(WorkspaceAccessError):
        store.transition(proposal, identifier)
    assert source.read_bytes() == raw
    if fault == "extra":
        assert (
            directory / ".journal-unknown.tmp"
        ).read_bytes() == b"UNRELATED-PRIVATE-CANARY"


def test_checkpoint_reservation_limit_retains_all_backups_and_stops_new_source_work(
    checkpoint_store, patch_fixture, monkeypatch
):
    """Use disclosed smaller policy caps to verify actual durable reservation accounting across restart without retiring checkpoints."""
    from src.infrastructure import checkpoints as module

    store, path = checkpoint_store
    _, source, raw, spec, approvals, build = patch_fixture
    monkeypatch.setattr(module, "MAX_OWNER_CHECKPOINTS", 2)
    first = store.capture(build())
    second = store.capture(build())
    with pytest.raises(WorkspaceAccessError, match="checkpoint_capacity"):
        store.capture(build())
    store.close()
    reopened = CheckpointStore(path, approvals.catalog)
    try:
        assert {
            row["checkpoint_id"]
            for row in reopened.list(spec.owner_id, spec.workspace_id)
        } == {str(first), str(second)}
        with pytest.raises(WorkspaceAccessError, match="checkpoint_capacity"):
            reopened.capture(build())
    finally:
        reopened.close()
    assert source.read_bytes() == raw and not approvals._records


def test_incomplete_reservation_fails_closed_without_guessing_cleanup(
    checkpoint_store, patch_fixture
):
    """Retain an unacknowledged private directory and deny new checkpoint creation rather than ignoring its reserved capacity."""
    store, path = checkpoint_store
    _, source, raw, _, approvals, build = patch_fixture
    orphan = path / uuid4().hex
    orphan.mkdir(mode=0o700)
    (orphan / "CANARY").write_bytes(b"UNACKNOWLEDGED")
    with pytest.raises(WorkspaceAccessError, match="checkpoint_recovery_required"):
        store.capture(build())
    assert (
        orphan / "CANARY"
    ).read_bytes() == b"UNACKNOWLEDGED" and source.read_bytes() == raw
    assert not approvals._records


def test_journal_transition_replay_and_changed_proposal_are_denied(
    checkpoint_store, patch_fixture
):
    """Permit exactly one intent transition for the original immutable review and reject reusing its checkpoint for another proposal."""
    store, _ = checkpoint_store
    _, _, _, _, _, build = patch_fixture
    proposal = build()
    identifier = store.capture(proposal)
    with pytest.raises(WorkspaceAccessError, match="checkpoint_proposal_changed"):
        store.transition(build(), identifier)
    store.transition(proposal, identifier)
    with pytest.raises(WorkspaceAccessError, match="checkpoint_state_conflict"):
        store.transition(proposal, identifier)


def test_actual_git_readback_failure_prevents_checkpoint_publication(
    checkpoint_store, patch_fixture, monkeypatch
):
    """Inject a real wrong source blob and reject its SHA256 before publishing any ready checkpoint or approval."""
    from src.infrastructure.checkpoint_git import CheckpointGit

    store, path = checkpoint_store
    _, source, raw, _, approvals, build = patch_fixture
    original = CheckpointGit.execute
    altered = []

    def change_source(self, operation, data=b"", identifiers=()):
        """Change only the first actual private source blob while retaining real Git object/commit creation."""
        if operation == "blob" and not altered:
            altered.append(True)
            data = b"wrong private source bytes\n"
        return original(self, operation, data, identifiers)

    monkeypatch.setattr(CheckpointGit, "execute", change_source)
    with pytest.raises(WorkspaceAccessError, match="checkpoint_integrity_failed"):
        store.capture(build())
    assert source.read_bytes() == raw and not approvals._records
    assert not list(path.glob("*/record.json"))
    with pytest.raises(WorkspaceAccessError, match="checkpoint_recovery_required"):
        store.capture(build())
