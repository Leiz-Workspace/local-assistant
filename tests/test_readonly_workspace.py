"""Exercise actual Linux workspace descriptors, owner isolation, link/mount escape and resource cleanup."""

import errno
import fcntl
import json
import logging
import os
import subprocess
from pathlib import Path
from uuid import uuid4

import pytest

from src.application.services.workspace_policy import (
    WorkspaceAccessError,
    WorkspaceSpec,
)
from src.infrastructure import readonly_workspace as module
from src.infrastructure.file_verifier import sandbox_command
from src.infrastructure.readonly_workspace import WorkspaceCatalog

logger = logging.getLogger(__name__)


@pytest.fixture
def workspace(tmp_path):
    """Create a disposable explicit root and outside canary with no project or host secret access."""
    root = tmp_path / "repository"
    root.mkdir()
    (root / "src").mkdir()
    (root / "src/main.py").write_text('"""Synthetic source fixture."""\nVALUE = 42\n')
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("OUTSIDE-CANARY")
    spec = WorkspaceSpec(uuid4(), uuid4(), str(root), "demo")
    return WorkspaceCatalog([spec]), spec, root, outside


def test_actual_descriptor_is_readonly_and_always_closed(workspace):
    """Read only an admitted in-root file and prove write denial, CLOEXEC and exceptional descriptor cleanup."""
    catalog, spec, root, _ = workspace
    with catalog.open(spec.owner_id, spec.workspace_id) as handle:
        root_fd = handle.fd
        with pytest.raises(RuntimeError):
            with handle.entry("src/main.py") as descriptor:
                file_fd = descriptor
                assert os.read(descriptor, 4096) == (root / "src/main.py").read_bytes()
                assert fcntl.fcntl(descriptor, fcntl.F_GETFD) & fcntl.FD_CLOEXEC
                with pytest.raises(OSError) as caught:
                    os.write(descriptor, b"write attempt")
                assert caught.value.errno == errno.EBADF
                raise RuntimeError("controlled caller interruption")
        with pytest.raises(OSError):
            os.fstat(file_fd)
        assert handle.discover() == dict(
            workspace_id=str(spec.workspace_id),
            name="demo",
            repository_kind="directory",
            read_only=True,
        )
    with pytest.raises(OSError):
        os.fstat(root_fd)
    handle.close()
    with pytest.raises(WorkspaceAccessError) as caught:
        handle.discover()
    assert caught.value.code == "workspace_closed"
    logger.info("workspace_actual_readonly_cleanup_verified")


@pytest.mark.parametrize(
    "kind", ["foreign", "unknown", "string_owner", "string_workspace"]
)
def test_denied_identity_never_opens_filesystem(workspace, monkeypatch, kind):
    """Make foreign, unknown and untyped identities indistinguishable before any filesystem syscall."""
    catalog, spec, _, _ = workspace
    owner = uuid4() if kind == "foreign" else spec.owner_id
    identifier = uuid4() if kind == "unknown" else spec.workspace_id
    if kind == "string_owner":
        owner = str(owner)
    if kind == "string_workspace":
        identifier = str(identifier)

    def forbidden_open(*args, **kwargs):
        """Fail the test if authorization attempts any filesystem root open."""
        pytest.fail("unauthorized identity reached filesystem")

    monkeypatch.setattr(module, "open_root", forbidden_open)
    with pytest.raises(WorkspaceAccessError) as caught:
        with catalog.open(owner, identifier):
            pytest.fail("unauthorized admission")
    assert caught.value.code == "workspace_not_found"


@pytest.mark.parametrize(
    "kind",
    ["file_link", "directory_link", "inside_link", "hard_link", "fifo", "socket"],
)
def test_actual_unsafe_targets_never_yield_an_entry(workspace, kind):
    """Refuse actual external/internal symlinks, hard-link aliases and nonregular IPC objects without blocking."""
    import socket

    catalog, spec, root, outside = workspace
    target = root / "unsafe"
    sock = None
    if kind == "file_link":
        target.symlink_to(outside / "secret.txt")
    elif kind == "directory_link":
        target.symlink_to(outside, target_is_directory=True)
    elif kind == "inside_link":
        target.symlink_to(root / "src/main.py")
    elif kind == "hard_link":
        os.link(outside / "secret.txt", target)
    elif kind == "fifo":
        os.mkfifo(target)
    else:
        sock = socket.socket(socket.AF_UNIX)
        sock.bind(str(target))
    try:
        path = "unsafe/secret.txt" if kind == "directory_link" else "unsafe"
        with catalog.open(spec.owner_id, spec.workspace_id) as handle:
            with pytest.raises(WorkspaceAccessError):
                with handle.entry(path):
                    pytest.fail("unsafe target admitted")
        assert (outside / "secret.txt").read_text() == "OUTSIDE-CANARY"
    finally:
        if sock is not None:
            sock.close()


def test_root_ancestors_cannot_be_symlinks(workspace, tmp_path):
    """Reject a symlinked configured root ancestor rather than resolving it into an implicit allowlist."""
    _, spec, root, _ = workspace
    alias = tmp_path / "alias"
    alias.symlink_to(root.parent, target_is_directory=True)
    catalog = WorkspaceCatalog(
        [
            WorkspaceSpec(
                spec.owner_id, spec.workspace_id, str(alias / root.name), "alias"
            )
        ]
    )
    with pytest.raises(WorkspaceAccessError) as caught:
        with catalog.open(spec.owner_id, spec.workspace_id):
            pytest.fail("symlinked root admitted")
    assert caught.value.code == "workspace_root_unavailable"


def test_replacing_configured_root_invalidates_existing_handle(workspace):
    """Reject root inode replacement before further entry admission while preserving all original bytes."""
    catalog, spec, root, _ = workspace
    with catalog.open(spec.owner_id, spec.workspace_id) as handle:
        moved = root.with_name("original-moved")
        root.rename(moved)
        root.mkdir()
        with pytest.raises(WorkspaceAccessError) as caught:
            with handle.entry("src/main.py"):
                pytest.fail("stale root admitted")
        assert caught.value.code == "workspace_root_changed"
        assert (moved / "src/main.py").is_file()


@pytest.mark.parametrize("kind", ["directory", "pointer", "symlink"])
def test_repository_discovery_never_executes_or_follows_git(
    workspace, monkeypatch, kind
):
    """Classify only in-root git markers without reading worktree pointers or invoking repository commands."""
    catalog, spec, root, outside = workspace
    marker = root / ".git"
    if kind == "directory":
        marker.mkdir()
        (marker / "config").write_text("UNTRUSTED-GIT-CONFIG")
    elif kind == "pointer":
        marker.write_text("gitdir: " + str(outside))
    else:
        marker.symlink_to(outside, target_is_directory=True)

    def forbidden_command(*args, **kwargs):
        """Prove repository discovery cannot execute git, hooks or any subprocess."""
        pytest.fail("discovery attempted command execution")

    monkeypatch.setattr(subprocess, "run", forbidden_command)
    with catalog.open(spec.owner_id, spec.workspace_id) as handle:
        if kind == "symlink":
            with pytest.raises(WorkspaceAccessError) as caught:
                handle.discover()
            assert caught.value.code == "workspace_repository_unsafe"
        else:
            assert handle.discover()["repository_kind"] == (
                "git_directory" if kind == "directory" else "git_pointer_unresolved"
            )
        with pytest.raises(WorkspaceAccessError):
            with handle.entry(".git/config"):
                pytest.fail("hidden git contents exposed")


def test_catalog_is_explicit_bounded_and_has_no_implicit_cwd(workspace, monkeypatch):
    """Keep empty catalogs inert and reject duplicate IDs or excessive configured roots without opening them."""
    _, spec, _, _ = workspace
    assert WorkspaceCatalog().specifications == ()
    for values in [[spec, spec], [spec] * 9, ["not a specification"], iter([spec])]:
        with pytest.raises(WorkspaceAccessError) as caught:
            WorkspaceCatalog(values)
        assert caught.value.code == "workspace_catalog_invalid"


def test_missing_kernel_primitive_has_no_weaker_fallback(workspace, monkeypatch):
    """Refuse unsupported platforms instead of falling back to a race-prone resolved pathname."""
    catalog, spec, _, _ = workspace
    monkeypatch.setattr(module.platform, "machine", lambda: "unsupported-architecture")
    with pytest.raises(WorkspaceAccessError) as caught:
        with catalog.open(spec.owner_id, spec.workspace_id):
            pytest.fail("fallback admitted")
    assert caught.value.code == "workspace_platform_unsupported"


def test_actual_bind_mount_escape_is_kernel_rejected(workspace):
    """Prove NO_XDEV rejects an outside bind mount in a private credential-free mount namespace."""
    _, _, root, outside = workspace
    (root / "mounted").mkdir()
    code = """import errno
import os
from uuid import UUID
from src.application.services.workspace_policy import WorkspaceSpec, WorkspaceAccessError
from src.infrastructure.readonly_workspace import WorkspaceCatalog, open_beneath
spec=WorkspaceSpec(UUID(int=1),UUID(int=2),"/workspace","probe")
with WorkspaceCatalog([spec]).open(spec.owner_id,spec.workspace_id) as handle:
    assert os.stat("/workspace/mounted/secret.txt").st_dev == os.fstat(handle.fd).st_dev
    try:
        descriptor = open_beneath(handle.fd,"mounted/secret.txt")
    except OSError as error:
        assert error.errno == errno.EXDEV
    else:
        os.close(descriptor)
        raise AssertionError("kernel NO_XDEV failed")
    try:
        with handle.entry("mounted/secret.txt"):
            raise AssertionError("outside bind mount admitted")
    except WorkspaceAccessError as error:
        assert error.code=="workspace_entry_unavailable"
print("mount_boundary_verified")
"""
    command = sandbox_command(["/venv/bin/python", "-c", code])
    boundary = command.index("--")
    command[boundary:boundary] = [
        "--ro-bind",
        str(root),
        "/workspace",
        "--ro-bind",
        str(outside),
        "/workspace/mounted",
    ]
    result = subprocess.run(
        command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=10
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "mount_boundary_verified"
    logger.info("workspace_actual_bind_mount_boundary_verified")


def test_logs_and_descriptors_expose_no_root_or_contents(workspace, caplog):
    """Expose only configured display metadata and stable codes in public discovery and audit logs."""
    catalog, spec, root, _ = workspace
    caplog.set_level(logging.INFO)
    before = len(list(Path("/proc/self/fd").iterdir()))
    for _ in range(10):
        with catalog.open(spec.owner_id, spec.workspace_id) as handle:
            data = handle.discover()
            with handle.entry("src/main.py") as descriptor:
                assert os.read(descriptor, 4096)
            with pytest.raises(WorkspaceAccessError):
                with handle.entry("../OUTSIDE-CANARY"):
                    pytest.fail("traversal admitted")
    assert len(list(Path("/proc/self/fd").iterdir())) == before
    assert str(root) not in caplog.text + json.dumps(data)
    assert "VALUE = 42" not in caplog.text and "OUTSIDE-CANARY" not in caplog.text


def test_symlink_swap_at_kernel_admission_cannot_escape(workspace, monkeypatch):
    """Reject a directory replaced by an outside symlink after root validation but before actual openat2."""
    catalog, spec, root, outside = workspace
    original = module.open_beneath
    swapped = False

    def replace_before_open(directory, path, **options):
        """Inject one real path replacement at the target syscall boundary without mocking kernel resolution."""
        nonlocal swapped
        if path == "src/secret.txt":
            (root / "src").rename(root / "original-src")
            (root / "src").symlink_to(outside, target_is_directory=True)
            swapped = True
        return original(directory, path, **options)

    monkeypatch.setattr(module, "open_beneath", replace_before_open)
    with catalog.open(spec.owner_id, spec.workspace_id) as handle:
        with pytest.raises(WorkspaceAccessError):
            with handle.entry("src/secret.txt"):
                pytest.fail("racing outside symlink admitted")
    assert swapped and (outside / "secret.txt").read_text() == "OUTSIDE-CANARY"


def test_initial_root_stat_failure_does_not_leak_descriptor(workspace, monkeypatch):
    """Join a newly opened root even if identity inspection fails before normal context-manager ownership."""
    catalog, spec, _, _ = workspace
    before = len(list(Path("/proc/self/fd").iterdir()))

    def failed_stat(descriptor):
        """Inject a native descriptor inspection error without leaking a configured pathname."""
        raise OSError(errno.EIO, "controlled stat failure")

    monkeypatch.setattr(module.os, "fstat", failed_stat)
    with pytest.raises(WorkspaceAccessError) as caught:
        with catalog.open(spec.owner_id, spec.workspace_id):
            pytest.fail("uninspected root admitted")
    assert caught.value.code == "workspace_root_unavailable"
    assert len(list(Path("/proc/self/fd").iterdir())) == before


def test_missing_openat2_syscall_fails_closed_and_closes_anchor(workspace, monkeypatch):
    """Prove kernel ENOSYS returns unsupported and releases the absolute-path anchor without a fallback."""
    catalog, spec, _, _ = workspace
    before = len(list(Path("/proc/self/fd").iterdir()))

    class MissingSyscall:
        """Represent a controlled libc syscall function returning real ENOSYS semantics."""

        def __call__(self, *args):
            """Set the thread-local native errno exactly as an unavailable Linux syscall would."""
            module.ctypes.set_errno(errno.ENOSYS)
            return -1

    class MissingLibrary:
        """Provide only the syscall attribute required by the openat2 adapter."""

        syscall = MissingSyscall()

    monkeypatch.setattr(module.ctypes, "CDLL", lambda *args, **kwargs: MissingLibrary())
    with pytest.raises(WorkspaceAccessError) as caught:
        with catalog.open(spec.owner_id, spec.workspace_id):
            pytest.fail("missing syscall fallback admitted")
    assert caught.value.code == "workspace_platform_unsupported"
    assert len(list(Path("/proc/self/fd").iterdir())) == before
