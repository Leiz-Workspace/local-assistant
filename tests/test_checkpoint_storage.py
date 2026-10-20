"""Verify native private checkpoint roots, scope separation, exclusivity, bounded inode reads and durable journal ownership."""

import os
from uuid import uuid4

import pytest
from test_atomic_patch import patch_fixture as patch_fixture

from src.application.services.workspace_policy import (
    WorkspaceAccessError,
    WorkspaceSpec,
)
from src.infrastructure.checkpoint_storage import (
    PrivateCheckpointRoot,
    canonical,
    decode_record,
)
from src.infrastructure.readonly_workspace import WorkspaceCatalog


@pytest.fixture
def private_root(tmp_path, patch_fixture):
    """Keep an explicit temporary0700 backup root outside the synthetic workspace and close its exclusive native capability."""
    path = tmp_path / "checkpoints"
    path.mkdir(mode=0o700)
    root = PrivateCheckpointRoot(path, patch_fixture[4].catalog)
    yield root, path
    root.close()


def test_owned_root_lock_restart_and_nonqueued_native_admission(
    private_root, patch_fixture
):
    """Hold actual exclusive store ownership, reject a second process-style open and permit clean reopen after close."""
    root, path = private_root
    with pytest.raises(WorkspaceAccessError, match="checkpoint_store_busy"):
        PrivateCheckpointRoot(path, patch_fixture[4].catalog)
    with root.operation():
        with pytest.raises(WorkspaceAccessError, match="checkpoint_store_busy"):
            with root.operation():
                pytest.fail("overlapping store admitted")
        with pytest.raises(WorkspaceAccessError, match="checkpoint_store_busy"):
            root.close()
        assert not root.closing and os.fstat(root.fd).st_ino == root.identity.st_ino
    root.close()
    replacement = PrivateCheckpointRoot(path, patch_fixture[4].catalog)
    replacement.close()


@pytest.mark.parametrize("position", ["same", "inside", "ancestor"])
def test_native_workspace_overlap_is_rejected_before_lock_write(
    tmp_path, patch_fixture, position
):
    """Reject same-root and either ancestry direction without creating a lock in the configured project."""
    workspace, _, _, spec, store, _ = patch_fixture
    if position == "same":
        root, catalog = workspace, store.catalog
    elif position == "inside":
        root = workspace / "backups"
        root.mkdir(mode=0o700)
        catalog = store.catalog
    else:
        root = tmp_path
        root.chmod(0o700)
        catalog = WorkspaceCatalog(
            [WorkspaceSpec(spec.owner_id, uuid4(), str(workspace), "nested")]
        )
    with pytest.raises(WorkspaceAccessError, match="checkpoint_workspace_overlap"):
        PrivateCheckpointRoot(root, catalog)
    assert not (root / ".store.lock").exists()


@pytest.mark.parametrize(
    "fault", ["mode", "symlink", "lock_link", "root_replace", "lock_replace"]
)
def test_unsafe_or_replaced_root_lock_is_rejected(tmp_path, patch_fixture, fault):
    """Exercise actual unsafe permissions/symlinks/hardlinks and replaced root/lock identity without deleting unrelated files."""
    path = tmp_path / "private"
    path.mkdir(mode=0o700)
    catalog = patch_fixture[4].catalog
    if fault == "mode":
        path.chmod(0o750)
    elif fault == "symlink":
        alias = tmp_path / "alias"
        alias.symlink_to(path)
        path = alias
    elif fault == "lock_link":
        outside = tmp_path / "unrelated"
        outside.write_bytes(b"CANARY")
        outside.chmod(0o600)
        (path / ".store.lock").hardlink_to(outside)
    if fault in {"mode", "symlink", "lock_link"}:
        with pytest.raises((WorkspaceAccessError, OSError)):
            PrivateCheckpointRoot(path, catalog)
    else:
        root = PrivateCheckpointRoot(path, catalog)
        try:
            if fault == "root_replace":
                path.rename(tmp_path / "original")
                path.mkdir(mode=0o700)
            else:
                (path / ".store.lock").unlink()
                (path / ".store.lock").write_bytes(b"unrelated replacement")
            with pytest.raises(WorkspaceAccessError):
                root.validate()
        finally:
            root.close()


def test_actual_bounded_file_read_and_atomic_journal(private_root):
    """Round-trip private canonical records and atomically publish a new journal without leaving temporary entries."""
    root, path = private_root
    original = dict(description="Synthetic checkpoint journal.", state="ready")
    root.create_file(root.fd, "journal.json", canonical(original))
    assert decode_record(root.read(root.fd, "journal.json")) == original
    root.replace_journal(root.fd, dict(original, state="applying"))
    assert decode_record(root.read(root.fd, "journal.json"))["state"] == "applying"
    assert not list(path.glob(".journal-*"))
    assert (path / "journal.json").stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize(
    "fault", ["symlink", "hardlink", "permissions", "size", "duplicate", "nan"]
)
def test_private_read_rejects_untrusted_inode_or_ambiguous_json(
    private_root, tmp_path, fault
):
    """Reject actual native aliases/permissions/oversize and ambiguous JSON without interpreting it as recovery authority."""
    root, path = private_root
    target = path / "record.json"
    raw = b'{"description":"Synthetic record."}'
    if fault in {"symlink", "hardlink"}:
        outside = tmp_path / "unrelated"
        outside.write_bytes(raw)
        outside.chmod(0o600)
        if fault == "symlink":
            target.symlink_to(outside)
        else:
            target.hardlink_to(outside)
    else:
        target.write_bytes(
            {
                "size": b"x" * 32769,
                "duplicate": b'{"x":1,"x":2}',
                "nan": b'{"x":NaN}',
            }.get(fault, raw)
        )
        target.chmod(0o644 if fault == "permissions" else 0o600)
    with pytest.raises((WorkspaceAccessError, OSError)):
        decode_record(root.read(root.fd, "record.json"))
