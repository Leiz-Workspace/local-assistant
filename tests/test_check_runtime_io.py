"""Verify stable bounded runtime copying, native private inode fences and strict manifest parsing with retained fault evidence."""

import hashlib
import os
import threading
from time import monotonic

import pytest

from src.application.services.workspace_policy import WorkspaceAccessError
from src.infrastructure import check_runtime_io as module


@pytest.fixture
def runtime_directories(tmp_path):
    """Retain owned disposable source/destination pins and close them after every native copy test."""
    paths = [tmp_path / name for name in ("source", "destination")]
    for path in paths:
        path.mkdir(mode=0o700)
    descriptors = [
        os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC) for path in paths
    ]
    try:
        yield paths, descriptors, threading.Event(), monotonic() + 5
    finally:
        for descriptor in descriptors:
            os.close(descriptor)


def test_actual_bounded_copy_has_exact_bytes_hash_mode_and_stable_private_read(
    runtime_directories,
):
    """Capture only verified bytes into a fresh private inode without changing the trusted input or logging its payload."""
    paths, descriptors, stop, deadline = runtime_directories
    raw = b'"""Controlled private runtime fixture."""\r\nVALUE = 1\r\n'
    (paths[0] / "module.py").write_bytes(raw)
    sha = hashlib.sha256(raw).hexdigest()
    assert (
        module.hash_source(
            descriptors[0], "module.py", 1024, stop, deadline, root_owned=False
        )
        == sha
    )
    record = module.copy_source(
        *descriptors[:1],
        "module.py",
        descriptors[1],
        "module.py",
        0o400,
        1024,
        stop,
        deadline,
        expected_sha256=sha,
        root_owned=False,
    )
    assert record == dict(sha256=sha, size=len(raw), mode=0o400)
    read, version = module.read_private(
        descriptors[1], "module.py", 1024, os.fstat(descriptors[1]).st_dev
    )
    assert read == raw and len(version) == 7
    assert (paths[0] / "module.py").read_bytes() == raw


@pytest.mark.parametrize("kind", ["symlink", "hardlink", "oversize", "wrong_digest"])
def test_unsafe_source_or_wrong_digest_cannot_publish_a_ready_runtime_file(
    runtime_directories, kind
):
    """Reject real aliases, excessive bytes and integrity mismatches without deleting incomplete private evidence."""
    paths, descriptors, stop, deadline = runtime_directories
    source = paths[0] / "module.py"
    source.write_bytes(b"x" * (1025 if kind == "oversize" else 4))
    if kind == "symlink":
        source.rename(paths[0] / "original")
        source.symlink_to("original")
    elif kind == "hardlink":
        os.link(source, paths[0] / "alias")
    with pytest.raises((WorkspaceAccessError, OSError)):
        module.copy_source(
            descriptors[0],
            "module.py",
            descriptors[1],
            "copied.py",
            0o400,
            1024,
            stop,
            deadline,
            expected_sha256="0" * 64,
            root_owned=False,
        )
    if kind == "wrong_digest":
        assert (paths[1] / "copied.py").exists()
        assert (paths[1] / "copied.py").stat().st_mode & 0o777 == 0o600


def test_existing_private_entry_is_not_truncated_or_reused(runtime_directories):
    """Keep an already present destination untouched when exclusive capture cannot acknowledge a new owned inode."""
    paths, descriptors, stop, deadline = runtime_directories
    (paths[0] / "module.py").write_bytes(b"new")
    (paths[1] / "module.py").write_bytes(b"existing")
    with pytest.raises(FileExistsError):
        module.copy_source(
            descriptors[0],
            "module.py",
            descriptors[1],
            "module.py",
            0o400,
            1024,
            stop,
            deadline,
            root_owned=False,
        )
    assert (paths[1] / "module.py").read_bytes() == b"existing"


def test_explicit_hash_pinned_uv_seed_alias_becomes_a_fresh_single_link_copy(
    runtime_directories,
):
    """Support uv hardlinked tool seeds only under explicit digest validation while keeping private output inode ownership strict."""
    paths, descriptors, stop, deadline = runtime_directories
    raw = b"CONTROLLED-TOOL-SEED"
    (paths[0] / "tool").write_bytes(raw)
    os.link(paths[0] / "tool", paths[0] / "tool-alias")
    sha = hashlib.sha256(raw).hexdigest()
    assert (
        module.hash_source(
            descriptors[0],
            "tool",
            1024,
            stop,
            deadline,
            root_owned=False,
            allow_seed_links=True,
        )
        == sha
    )
    module.copy_source(
        descriptors[0],
        "tool",
        descriptors[1],
        "tool",
        0o500,
        1024,
        stop,
        deadline,
        expected_sha256=sha,
        root_owned=False,
        allow_seed_links=True,
    )
    assert (paths[0] / "tool").stat().st_nlink == 2
    assert (paths[1] / "tool").stat().st_nlink == 1
    assert (paths[1] / "tool").read_bytes() == raw
    with pytest.raises(WorkspaceAccessError):
        module.copy_source(
            descriptors[0],
            "tool",
            descriptors[1],
            "unverified",
            0o500,
            1024,
            stop,
            deadline,
            root_owned=False,
            allow_seed_links=True,
        )


@pytest.mark.parametrize("name", ["../escape", "/absolute", "nested/file", ".", ".."])
def test_destination_name_cannot_widen_the_borrowed_directory_capability(
    runtime_directories, name
):
    """Reject caller path components before source reads or target inode creation."""
    paths, descriptors, stop, deadline = runtime_directories
    (paths[0] / "module.py").write_bytes(b"unchanged")
    with pytest.raises(WorkspaceAccessError):
        module.copy_source(
            descriptors[0],
            "module.py",
            descriptors[1],
            name,
            0o400,
            1024,
            stop,
            deadline,
            root_owned=False,
        )
    assert list(paths[1].iterdir()) == []


def test_write_failure_retains_partial_private_evidence_and_original_source(
    runtime_directories, monkeypatch
):
    """Keep unknown incomplete capture data rather than guessing cleanup ownership after a native write error."""
    paths, descriptors, stop, deadline = runtime_directories
    (paths[0] / "module.py").write_bytes(b"unchanged")

    def failed_write(*arguments):
        """Inject a native target write failure after exclusive inode creation."""
        raise OSError("controlled target write failure")

    monkeypatch.setattr(module.os, "write", failed_write)
    with pytest.raises(OSError):
        module.copy_source(
            descriptors[0],
            "module.py",
            descriptors[1],
            "module.py",
            0o400,
            1024,
            stop,
            deadline,
            root_owned=False,
        )
    assert (paths[0] / "module.py").read_bytes() == b"unchanged"
    assert (paths[1] / "module.py").exists()


@pytest.mark.parametrize(
    "raw", [b'{"a":1,"a":2}', b'{"a":NaN}', b"[]", b"\xff", b"{" * 1024]
)
def test_ambiguous_or_invalid_manifest_never_becomes_runtime_authority(raw):
    """Refuse duplicate keys, nonfinite values, wrong container type and malformed/oversized JSON."""
    with pytest.raises(WorkspaceAccessError):
        module.decode_manifest(raw, 512)
