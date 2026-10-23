"""Run fixed resource-fault fixtures in offline read-only bubblewrap with small private tmpfs and strict process limits."""

import hashlib
import json
import logging
import os
import subprocess
import time
from pathlib import Path

logger = logging.getLogger(__name__)
WORKER = Path(__file__).parent / "fixtures/runtime/fault_worker.py"


def command(snapshot, mode):
    """Expose only fixed stdlib Python/script and empty private scratch under immutable caps without host/project/credential mounts."""
    if type(mode) is not str or mode not in {"memory", "disk"}:
        raise ValueError("invalid_fault_mode")
    return [
        "/usr/bin/bwrap",
        "--unshare-all",
        "--die-with-parent",
        "--new-session",
        "--cap-drop",
        "ALL",
        "--clearenv",
        "--ro-bind",
        "/usr",
        "/usr",
        "--symlink",
        "usr/bin",
        "/bin",
        "--symlink",
        "usr/lib",
        "/lib",
        "--symlink",
        "usr/lib64",
        "/lib64",
        "--dir",
        "/app",
        "--ro-bind",
        str(snapshot),
        "/app/probe.py",
        "--proc",
        "/proc",
        "--dev",
        "/dev",
        "--size",
        "65536",
        "--tmpfs",
        "/scratch",
        "--setenv",
        "PATH",
        "/usr/bin:/bin",
        "--setenv",
        "LANG",
        "C.UTF-8",
        "--setenv",
        "PYTHONDONTWRITEBYTECODE",
        "1",
        "--chdir",
        "/app",
        "--remount-ro",
        "/",
        "--",
        "/usr/bin/prlimit",
        "--as=268435456",
        "--cpu=2:3",
        "--nofile=32",
        "--fsize=1048576",
        "--core=0",
        "--",
        "/usr/bin/python3",
        "/app/probe.py",
        mode,
    ]


def run_fault(root, mode):
    """Retain exact worker bytes and finite first observation, join the child and publish only expected recovered failures."""
    root.mkdir(mode=0o700, exist_ok=False)
    raw = WORKER.read_bytes()
    snapshot = root / "executed-worker.py"
    fd = os.open(snapshot, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o400)
    with os.fdopen(fd, "wb") as stream:
        stream.write(raw)
    started = time.perf_counter()
    result = subprocess.run(
        command(snapshot.resolve(), mode),
        capture_output=True,
        timeout=10,
        start_new_session=True,
        env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"},
    )
    (root / "first-stdout.json").write_bytes(result.stdout)
    (root / "first-stderr.log").write_bytes(result.stderr)
    assert (
        result.returncode == 0
        and len(result.stdout) <= 4096
        and len(result.stderr) <= 4096
    )
    value = json.loads(result.stdout)
    assert (
        value["mode"] == mode
        and value["expected_failure"]
        == {"memory": "MemoryError", "disk": "ENOSPC"}[mode]
    )
    assert (
        value["address_space_cap_bytes"] == 268435456
        and not value["host_oom_triggered"]
        and not value["host_disk_filled"]
    )
    assert snapshot.read_bytes() == raw
    logger.info(
        "native_bounded_fault_joined mode=%s outcome=%s",
        mode,
        value["expected_failure"],
    )
    return dict(
        description="Owned fixture exhaustion under256MiB address-space/64KiB tmpfs, not host OOM/disk-fill or a model runtime benchmark.",
        measurement=value,
        worker_sha256=hashlib.sha256(raw).hexdigest(),
        wall_seconds=time.perf_counter() - started,
        exit_code=result.returncode,
        child_reaped=True,
    )
