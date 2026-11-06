"""Verify actual owner-scoped native source snapshots, immutable byte/version receipts and changed-source/root/link/cancel rejection."""

import hashlib
import os
import threading
from uuid import uuid4

import pytest

from src.application.services.workspace_policy import (
    WorkspaceAccessError,
    WorkspaceSpec,
)
from src.infrastructure import check_sources as module
from src.infrastructure.check_sources import NativeCheckSources
from src.infrastructure.readonly_workspace import WorkspaceCatalog


@pytest.fixture
def selected_workspace(tmp_path):
    """Create only explicitly owned disposable Python sources and one authorized application workspace mapping."""
    root = tmp_path / "workspace"
    root.mkdir(mode=0o700)
    (root / "src").mkdir(mode=0o700)
    raw = b'"""Controlled selected source."""\r\nVALUE = 1\r\n'
    (root / "src/value.py").write_bytes(raw)
    owner, workspace = uuid4(), uuid4()
    catalog = WorkspaceCatalog(
        [WorkspaceSpec(owner, workspace, str(root), "Controlled checks")]
    )
    files = [
        {"path": "src/value.py", "expected_sha256": hashlib.sha256(raw).hexdigest()}
    ]
    return root, raw, owner, workspace, catalog, files


def capture(selected_workspace, **overrides):
    """Capture through the exact native policy while allowing only test-controlled scope or event overrides."""
    _, _, owner, workspace, catalog, files = selected_workspace
    return NativeCheckSources(
        catalog,
        overrides.get("owner", owner),
        overrides.get("workspace", workspace),
        "python_unittest",
        overrides.get("files", files),
        overrides.get("stop"),
    )


def test_exact_source_bytes_metadata_and_root_pin_lifetime(selected_workspace):
    """Keep CRLF bytes/digests/native receipts immutable and close the owned root without erasing historical metadata."""
    snapshot = capture(selected_workspace)
    descriptor = snapshot.handle.fd
    try:
        assert snapshot.originals["src/value.py"] == selected_workspace[1]
        with pytest.raises(TypeError):
            snapshot.originals["src/value.py"] = b"changed"
        view = snapshot.metadata()
        version = snapshot.version
        view["files"][0]["native"].clear()
        view["root"].clear()
        assert snapshot.metadata()["files"][0]["native"]
        snapshot.validate()
        assert snapshot.version == version
    finally:
        snapshot.close()
    assert snapshot.metadata()["source_version"] == version
    with pytest.raises(OSError):
        os.fstat(descriptor)
    with pytest.raises(WorkspaceAccessError) as caught:
        snapshot.validate()
    assert caught.value.code == "checks_sources_closed"


@pytest.mark.parametrize("scope", ["owner", "workspace"])
def test_unknown_or_foreign_scope_never_reads_source(selected_workspace, scope):
    """Authorize configured application identity before entering any native source path."""
    with pytest.raises(WorkspaceAccessError) as caught:
        capture(selected_workspace, **{scope: uuid4()})
    assert caught.value.status_code == 404


@pytest.mark.parametrize(
    "change", ["bytes", "same_bytes_new_inode", "mode", "parent", "root"]
)
def test_native_source_context_change_needs_a_new_snapshot_and_review(
    selected_workspace, change
):
    """Reject real source/hash/inode/mode/parent/root changes without silently updating the original approved context."""
    root, raw, _, _, _, _ = selected_workspace
    snapshot = capture(selected_workspace)
    original = snapshot.version
    try:
        path = root / "src/value.py"
        if change == "bytes":
            path.write_bytes(raw + b"VALUE = 2\n")
        elif change == "same_bytes_new_inode":
            replacement = root / "src/new.py"
            replacement.write_bytes(raw)
            os.replace(replacement, path)
        elif change == "mode":
            path.chmod(0o400)
        elif change == "parent":
            retained = root / "retained"
            (root / "src").rename(retained)
            (root / "src").mkdir(mode=0o700)
            (retained / "value.py").rename(path)
        else:
            root.rename(root.parent / "retained-root")
            root.mkdir(mode=0o700)
        with pytest.raises(WorkspaceAccessError):
            snapshot.validate()
        assert (
            snapshot.version == original and snapshot.originals["src/value.py"] == raw
        )
    finally:
        snapshot.close()


@pytest.mark.parametrize(
    "kind", ["symlink", "hardlink", "fifo", "binary", "oversize", "wrong_hash"]
)
def test_unsafe_source_and_digest_mismatch_fail_before_private_snapshot_publication(
    selected_workspace, kind
):
    """Deny actual links/special files, invalid source bytes, size overflow and stale expected digests without executing code."""
    root, raw, _, _, _, files = selected_workspace
    path = root / "src/value.py"
    if kind == "symlink":
        path.rename(root / "src/original.py")
        path.symlink_to("original.py")
    elif kind == "hardlink":
        os.link(path, root / "src/alias.py")
    elif kind == "fifo":
        path.unlink()
        os.mkfifo(path)
    elif kind in {"binary", "oversize"}:
        value = b"\x00" if kind == "binary" else b"x" * 8193
        path.write_bytes(value)
        files[0]["expected_sha256"] = hashlib.sha256(value).hexdigest()
    else:
        files[0]["expected_sha256"] = "0" * 64
    with pytest.raises(WorkspaceAccessError):
        capture(selected_workspace)


def test_cancelled_capture_and_revalidation_stop_before_source_use(selected_workspace):
    """Signal a real operation-owned cancellation event during both proposal capture and later source-version validation."""
    stop = threading.Event()
    stop.set()
    with pytest.raises(WorkspaceAccessError) as caught:
        capture(selected_workspace, stop=stop)
    assert caught.value.code == "checks_capture_cancelled"
    snapshot = capture(selected_workspace)
    try:
        with pytest.raises(WorkspaceAccessError) as caught:
            snapshot.validate(stop)
        assert caught.value.code == "checks_capture_cancelled"
    finally:
        snapshot.close()


def test_unselected_workspace_change_does_not_widen_or_invalidate_selected_bytes(
    selected_workspace,
):
    """Allow unrelated source-tree entry changes while binding only explicitly selected immutable Python inputs."""
    root, raw, _, _, _, _ = selected_workspace
    snapshot = capture(selected_workspace)
    try:
        (root / "README.md").write_text(
            "Unselected controlled fixture, never mounted or executed.\n"
        )
        snapshot.validate()
        assert tuple(snapshot.originals) == ("src/value.py",)
        assert snapshot.originals["src/value.py"] == raw
    finally:
        snapshot.close()


def test_snapshot_read_helper_cannot_expand_the_fixed_selection(selected_workspace):
    """Deny an unselected path before reading bytes through the retained source capability."""
    root = selected_workspace[0]
    (root / "README.md").write_text("Unselected controlled fixture.\n")
    snapshot = capture(selected_workspace)
    try:
        with pytest.raises(WorkspaceAccessError) as caught:
            snapshot.read("README.md", threading.Event(), float("inf"))
        assert caught.value.code == "checks_source_path_invalid"
    finally:
        snapshot.close()


def test_final_native_fence_catches_an_earlier_source_changed_during_later_read(
    selected_workspace, monkeypatch
):
    """Reject controlled concurrent change after an earlier selected file was re-read without silently refreshing its old version."""
    root, raw, _, _, _, files = selected_workspace
    other = b'"""Controlled second selected source."""\nVALUE = 2\n'
    (root / "src/other.py").write_bytes(other)
    files.append(
        dict(path="src/other.py", expected_sha256=hashlib.sha256(other).hexdigest())
    )
    snapshot = capture(selected_workspace)
    original = module.NativeCheckSources.read

    def mutate_previous(instance, path, stop, deadline):
        """Change only the controlled earlier fixture after the later source read has finished."""
        result = original(instance, path, stop, deadline)
        if path == "src/other.py":
            (root / "src/value.py").write_bytes(raw + b"VALUE = 3\n")
        return result

    monkeypatch.setattr(module.NativeCheckSources, "read", mutate_previous)
    try:
        with pytest.raises(WorkspaceAccessError) as caught:
            snapshot.validate()
        assert caught.value.code == "checks_source_changed"
        assert snapshot.originals["src/value.py"] == raw
    finally:
        snapshot.close()
