"""Supervise fixed non-root credential-free coding evaluation with bounded pipes, wall time and joined namespace cleanup."""

import json
import logging
import os
import selectors
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

logger = logging.getLogger(__name__)
MAX_SECONDS = 8
MAX_STDOUT = 65536
MAX_STDERR = 4096
WORKER = Path(__file__).resolve().parents[2] / "scripts/coding_sandbox_worker.py"


def coding_sandbox_command():
    """Mount only trusted system runtime and one fixed worker in isolated namespaces under UID/GID65534."""
    interpreter = Path(sys.executable).resolve()
    if interpreter.parent != Path("/usr/bin") or not interpreter.name.startswith(
        "python3"
    ):
        raise RuntimeError("coding_sandbox_runtime_unsupported")
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
        "--ro-bind",
        str(WORKER),
        "/worker.py",
        "--proc",
        "/proc",
        "--dev",
        "/dev",
        "--tmpfs",
        "/tmp",
        "--remount-ro",
        "/tmp",
        "--chdir",
        "/",
        "--uid",
        "65534",
        "--gid",
        "65534",
        "--setenv",
        "LANG",
        "C.UTF-8",
        "--setenv",
        "PATH",
        "/usr/bin",
        "--",
        str(interpreter),
        "-I",
        "-B",
        "/worker.py",
    ]


def evaluate_candidate(code, inputs, stop=None):
    """Return bounded function observations only after process/pipes close; trusted parent owns expected outputs."""
    stop = stop if stop is not None else threading.Event()
    if not isinstance(code, str) or len(code.encode("utf-8")) > 8192:
        raise ValueError("coding_candidate_limit")
    if not isinstance(inputs, list) or not 1 <= len(inputs) <= 16:
        raise ValueError("coding_inputs_limit")
    raw = json.dumps(
        dict(code=code, inputs=inputs), ensure_ascii=False, allow_nan=False
    ).encode()
    if len(raw) > 32768:
        raise ValueError("coding_request_limit")
    started = time.monotonic()
    deadline = started + MAX_SECONDS
    status = "failed"
    stdout, stderr = bytearray(), bytearray()
    process = None
    selector = selectors.DefaultSelector()
    try:
        if stop.is_set():
            status = "cancelled"
            return dict(status=status, results=[], elapsed_seconds=0.0)
        process = subprocess.Popen(
            coding_sandbox_command(),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"},
            start_new_session=True,
            close_fds=True,
        )
        for stream, event, label in [
            (process.stdin, selectors.EVENT_WRITE, "stdin"),
            (process.stdout, selectors.EVENT_READ, "stdout"),
            (process.stderr, selectors.EVENT_READ, "stderr"),
        ]:
            os.set_blocking(stream.fileno(), False)
            selector.register(stream, event, label)
        offset = 0
        while selector.get_map():
            if stop.is_set():
                status = "cancelled"
                break
            if time.monotonic() >= deadline:
                status = "timeout"
                break
            for key, _ in selector.select(
                min(0.05, max(0, deadline - time.monotonic()))
            ):
                if key.data == "stdin":
                    try:
                        offset += os.write(key.fd, raw[offset : offset + 4096])
                        finished = offset == len(raw)
                    except BrokenPipeError:
                        finished = True
                    if finished:
                        selector.unregister(key.fileobj)
                        key.fileobj.close()
                else:
                    data = os.read(key.fd, 4096)
                    if not data:
                        selector.unregister(key.fileobj)
                        key.fileobj.close()
                        continue
                    output = stdout if key.data == "stdout" else stderr
                    output.extend(data)
                    limit = MAX_STDOUT if key.data == "stdout" else MAX_STDERR
                    if len(output) > limit:
                        status = "output_limit"
                        break
            if status == "output_limit":
                break
        else:
            try:
                code_value = process.wait(
                    timeout=max(0.001, deadline - time.monotonic())
                )
                status = "completed" if code_value == 0 else "failed"
            except subprocess.TimeoutExpired:
                status = "timeout"
    except (OSError, ValueError, RuntimeError):
        status = "unavailable"
    finally:
        if process is not None:
            if process.poll() is None:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            process.wait()
            for stream in (process.stdin, process.stdout, process.stderr):
                if not stream.closed:
                    stream.close()
        selector.close()
        logger.info("coding_sandbox_joined status=%s", status)
    results = []
    if status == "completed":
        try:
            payload = json.loads(stdout)
            if not isinstance(payload, dict) or set(payload) != {"results"}:
                raise ValueError()
            results = payload["results"]
            if not isinstance(results, list) or len(results) != len(inputs):
                raise ValueError()
            for result in results:
                if not isinstance(result, dict) or set(result) not in (
                    {"value"},
                    {"error"},
                ):
                    raise ValueError()
                json.dumps(result, allow_nan=False)
        except (ValueError, TypeError, UnicodeError, RecursionError):
            status, results = "invalid_output", []
    return dict(
        status=status,
        results=results,
        elapsed_seconds=round(time.monotonic() - started, 4),
    )


def compare_oracles(observations, expected):
    """Compare exact returned JSON values against trusted host-only oracles instead of candidate PASS markers."""
    if observations["status"] != "completed" or len(observations["results"]) != len(
        expected
    ):
        return [False] * len(expected)
    outcomes = []
    for actual, wanted in zip(observations["results"], expected, strict=True):
        outcomes.append(
            set(actual) == {"value"}
            and json.dumps(
                actual["value"], sort_keys=True, ensure_ascii=False, allow_nan=False
            )
            == json.dumps(wanted, sort_keys=True, ensure_ascii=False, allow_nan=False)
        )
    logger.info(
        "coding_oracles_compared cases=%d passed=%d", len(outcomes), sum(outcomes)
    )
    return outcomes
