"""Verify actual current-source recovery classifications without mutation, causality inference, replay grants or guessed cleanup."""

import threading
from uuid import uuid4

import pytest
from test_atomic_patch import patch_fixture as patch_fixture
from test_checkpoints import checkpoint_store as checkpoint_store

from src.application.services.workspace_policy import WorkspaceAccessError
from src.infrastructure.checkpoint_recovery import observe_checkpoint


@pytest.mark.parametrize(
    "state",
    ["original", "replacement", "other", "missing", "symlink", "oversize", "root"],
)
def test_actual_recovery_observations_never_restore_or_create_grants(
    checkpoint_store, patch_fixture, tmp_path, state
):
    """Compare current native bytes/root against actual committed history and keep missing/unsafe data unavailable instead of guessing."""
    store, _ = checkpoint_store
    root, source, raw, spec, approvals, build = patch_fixture
    proposal = build()
    identifier = store.capture(proposal)
    snapshot = store.read(spec.owner_id, spec.workspace_id, identifier)
    if state == "replacement":
        source.write_bytes(proposal.replacement)
    elif state == "other":
        source.write_bytes(b"independent external bytes\n")
    elif state == "missing":
        source.unlink()
    elif state == "symlink":
        source.unlink()
        source.symlink_to(tmp_path / "outside")
    elif state == "oversize":
        source.write_bytes(b"x" * 8193)
    elif state == "root":
        root.rename(tmp_path / "old-root")
        root.mkdir(mode=0o700)
    observed = observe_checkpoint(
        store.catalog, spec.owner_id, spec.workspace_id, snapshot
    )
    assert observed["observation"] == {
        "original": "observed_original",
        "replacement": "observed_replacement",
        "other": "observed_other",
        "root": "root_changed",
    }.get(state, "source_unavailable")
    assert (
        not observed["source_modified"]
        and not observed["recovered_approval"]
        and not observed["action_taken"]
        and not observed["causality_inferred"]
    )
    assert not approvals._records
    assert (
        store.read(spec.owner_id, spec.workspace_id, identifier)["journal"]["state"]
        == "ready"
    )


def test_recovery_cancellation_and_owner_mismatch_fail_before_source_access(
    checkpoint_store, patch_fixture
):
    """Refuse foreign context and already-cancelled inspection without reading current source or recovering any action."""
    store, _ = checkpoint_store
    _, _, _, spec, _, build = patch_fixture
    identifier = store.capture(build())
    snapshot = store.read(spec.owner_id, spec.workspace_id, identifier)
    stop = threading.Event()
    stop.set()
    with pytest.raises(WorkspaceAccessError, match="checkpoint_cancelled"):
        observe_checkpoint(
            store.catalog, spec.owner_id, spec.workspace_id, snapshot, stop
        )
    with pytest.raises(WorkspaceAccessError, match="checkpoint_not_found"):
        observe_checkpoint(store.catalog, uuid4(), spec.workspace_id, snapshot)
