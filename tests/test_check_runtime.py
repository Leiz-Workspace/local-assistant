"""Verify actual private system-runtime capture/reopen, exact integrity fences and no-install isolated Python/Ruff execution."""

import hashlib
import json
import os
import threading
from pathlib import Path
from uuid import uuid4

import pytest

from src.application.services.workspace_policy import WorkspaceAccessError
from src.infrastructure import check_runtime as module
from src.infrastructure.check_runner import NativeChecks
from src.infrastructure.check_runtime import RuntimeCapsule, RuntimeSpec
from src.infrastructure.check_runtime_io import canonical_manifest


@pytest.fixture
def runtime_spec():
    """Select only already installed exact trusted Python and pinned cached Ruff bytes for disposable capsule tests."""
    sha = "20cf97c5db04ca9c51249dec1a54cbc96c24462df280334ada04b8f3c877b746"
    ruff = next(
        (
            path
            for path in (Path.home() / ".cache/uv/archive-v0").glob("*/bin/ruff")
            if hashlib.sha256(path.read_bytes()).hexdigest() == sha
        ),
        None,
    )
    assert ruff is not None, (
        "Existing pinned Ruff is required; no installation fallback"
    )
    return RuntimeSpec(
        "/usr/bin/python3.12",
        hashlib.sha256(Path("/usr/bin/python3.12").read_bytes()).hexdigest(),
        "/usr/lib/python3.12",
        str(ruff),
        sha,
    )


@pytest.fixture
def runtime_root(tmp_path):
    """Borrow one explicitly created owned0700 disposable storage root without registering a real workspace."""
    root = tmp_path / "private"
    root.mkdir(mode=0o700)
    descriptor = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    try:
        yield root, descriptor
    finally:
        os.close(descriptor)


def test_actual_runtime_capture_reopen_and_private_python_stdlib_execution(
    runtime_root, runtime_spec, tmp_path
):
    """Capture existing exact runtime bytes, exclude external hooks/cache and execute both finite profiles through the real supervisor."""
    path, descriptor = runtime_root
    capsule = RuntimeCapsule(descriptor, runtime_spec)
    try:
        assert capsule.allocated_bytes <= 67108864
        assert not any(
            part in name
            for name in capsule.manifest["files"]
            for part in (
                "__pycache__",
                "sitecustomize",
                "site-packages",
                "dist-packages",
            )
        )
        original = capsule.sha256, capsule.version
        snapshot = tmp_path / "snapshot"
        snapshot.mkdir(mode=0o700)
        (snapshot / "test_private.py").write_text(
            '"""Verify the private stdlib capsule."""\nimport encodings,sys,unittest\nclass Fixture(unittest.TestCase):\n    """Observe private interpreter and library paths."""\n    def test_paths(self):\n        """Reject fallback to host Python packages or stdlib."""\n        self.assertEqual(sys.prefix,"/runtime")\n        self.assertTrue(encodings.__file__.startswith("/runtime/lib/"))\n        self.assertTrue(unittest.__file__.startswith("/runtime/lib/"))\n'
        )
        pin = os.open(snapshot, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
        try:
            for profile in ("python_unittest", "ruff_check"):
                result = NativeChecks(
                    pin, capsule.fd, profile, min(os.sched_getaffinity(0)), uuid4()
                ).run()
                assert result["exit_code"] == 0, result
        finally:
            os.close(pin)
        capsule.validate()
        assert (capsule.sha256, capsule.version) == original
    finally:
        capsule.close()
    reopened = RuntimeCapsule(descriptor, runtime_spec)
    try:
        assert (reopened.sha256, reopened.version) == original
    finally:
        reopened.close()
    assert (path / "runtime/manifest.json").is_file()


def test_wrong_configured_tool_digest_fails_before_runtime_creation(
    runtime_root, runtime_spec
):
    """Leave no partial runtime when initial operator configuration names the wrong trusted tool digest."""
    wrong = RuntimeSpec(
        runtime_spec.python,
        "0" * 64,
        runtime_spec.stdlib,
        runtime_spec.ruff,
        runtime_spec.ruff_sha256,
    )
    with pytest.raises(WorkspaceAccessError) as caught:
        RuntimeCapsule(runtime_root[1], wrong)
    assert caught.value.code == "checks_runtime_digest_mismatch"
    assert not (runtime_root[0] / "runtime").exists()


def test_private_runtime_mutation_invalidates_the_retained_launch_version(
    runtime_root, runtime_spec
):
    """Reject same-owner host fixture tampering instead of silently refreshing an approved runtime identity."""
    capsule = RuntimeCapsule(runtime_root[1], runtime_spec)
    try:
        path = runtime_root[0] / "runtime/lib/python3.12/os.py"
        path.chmod(0o600)
        path.write_bytes(
            path.read_bytes() + b"\n# controlled private integrity mutation\n"
        )
        path.chmod(0o400)
        with pytest.raises(WorkspaceAccessError):
            capsule.validate()
    finally:
        capsule.close()


def test_incomplete_retained_capsule_is_not_deleted_or_guessed_rebuilt(
    runtime_root, runtime_spec
):
    """Keep preexisting unacknowledged runtime bytes and fail closed for explicit recovery."""
    partial = runtime_root[0] / "runtime"
    partial.mkdir(mode=0o700)
    (partial / "UNACKNOWLEDGED").write_bytes(b"preserve")
    with pytest.raises((WorkspaceAccessError, FileNotFoundError)):
        RuntimeCapsule(runtime_root[1], runtime_spec)
    assert (partial / "UNACKNOWLEDGED").read_bytes() == b"preserve"


@pytest.mark.parametrize("kind", ["empty_directory", "hardlink", "boolean_size"])
def test_complete_retained_runtime_rejects_unknown_members_aliases_or_ambiguous_schema(
    runtime_root, runtime_spec, kind
):
    """Reject actual extra directories/hardlinks and bool-as-zero metadata even when reopening without baseline fingerprints."""
    capsule = RuntimeCapsule(runtime_root[1], runtime_spec)
    capsule.close()
    root = runtime_root[0] / "runtime"
    if kind == "empty_directory":
        (root / "unknown").mkdir(mode=0o700)
    elif kind == "hardlink":
        os.link(root / "lib/python3.12/os.py", root / "lib/python3.12/alias.py")
    else:
        entry = root / "lib/python3.12/controlled_empty_fixture.dat"
        entry.write_bytes(b"")
        entry.chmod(0o400)
        path = root / "manifest.json"
        manifest = json.loads(path.read_bytes())
        manifest["files"]["lib/python3.12/controlled_empty_fixture.dat"] = dict(
            sha256=hashlib.sha256(b"").hexdigest(), size=False, mode=0o400
        )
        path.chmod(0o600)
        path.write_bytes(canonical_manifest(manifest, 131072))
        path.chmod(0o400)
    with pytest.raises((WorkspaceAccessError, OSError)):
        RuntimeCapsule(runtime_root[1], runtime_spec)
    assert (root / "manifest.json").exists()


@pytest.mark.parametrize("kind", ["manifest", "previously_hashed_binary"])
def test_native_final_fences_detect_late_mutation_during_complete_inventory_hashing(
    runtime_root, runtime_spec, monkeypatch, kind
):
    """Reject controlled writes after earlier reads instead of publishing a stale runtime version from a mixed-time scan."""
    capsule = RuntimeCapsule(runtime_root[1], runtime_spec)
    original = module.hash_source
    calls = 0

    def mutate_later(*arguments, **options):
        """Mutate an already observed private inode only after the initial hash stage has advanced."""
        nonlocal calls
        result = original(*arguments, **options)
        calls += 1
        if calls == 2:
            target = (
                runtime_root[0]
                / "runtime"
                / ("manifest.json" if kind == "manifest" else "bin/python3.12")
            )
            target.chmod(0o600)
            target.write_bytes(target.read_bytes() + b" ")
            target.chmod(0o400 if kind == "manifest" else 0o500)
        return result

    monkeypatch.setattr(module, "hash_source", mutate_later)
    try:
        with pytest.raises(WorkspaceAccessError) as caught:
            capsule.validate()
        assert caught.value.code == "checks_runtime_changed"
    finally:
        capsule.close()


def test_runtime_validation_honors_operation_cancellation_before_metadata_read(
    runtime_root, runtime_spec, monkeypatch
):
    """Signal the actual caller-owned stop event before any further private validation I/O."""
    capsule = RuntimeCapsule(runtime_root[1], runtime_spec)
    stop = threading.Event()
    stop.set()

    def unexpected_read(*arguments, **options):
        """Fail the test if cancelled validation tries to read even bounded metadata."""
        pytest.fail("cancelled runtime metadata read")

    monkeypatch.setattr(module, "read_private", unexpected_read)
    try:
        with pytest.raises(WorkspaceAccessError) as caught:
            capsule.validate(stop)
        assert caught.value.code == "checks_capture_cancelled"
    finally:
        capsule.close()
