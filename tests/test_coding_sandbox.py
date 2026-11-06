"""Verify actual non-root namespace coding observations, host-only oracles and bounded joined evaluator failures."""

import asyncio
import socket
import threading
from pathlib import Path

import pytest

from apps.api.services.workspaces import joined_work
from src.infrastructure import coding_sandbox as module
from src.infrastructure.coding_sandbox import compare_oracles, evaluate_candidate


def candidate(body, imports=""):
    """Build fully described fixture source without evaluating it in the host test process."""
    return (
        '"""Synthetic evaluator fixture."""\n'
        + imports
        + '\ndef solve(*arguments):\n    """Return controlled sandbox observations."""\n'
        + "\n".join("    " + line for line in body.splitlines())
        + "\n"
    )


def test_actual_function_values_use_host_only_oracles():
    """Compare exact values/type against independent parent expectations without trusting printed markers."""
    result = evaluate_candidate(
        candidate("return arguments[0] // arguments[1]"), [[10, 3], [-10, 3], [0, 5]]
    )
    assert result["status"] == "completed", result
    assert compare_oracles(result, [3, -4, 0]) == [True, True, True]
    assert compare_oracles(result, [3, -3, False]) == [True, False, False]


def test_actual_worker_hard_resource_limits():
    """Read actual worker limits and verify hard bounds without pretending they are measured memory performance."""
    code = candidate(
        "return [list(resource.getrlimit(limit)) for limit in [resource.RLIMIT_AS, resource.RLIMIT_CPU, resource.RLIMIT_FSIZE, resource.RLIMIT_CORE, resource.RLIMIT_NOFILE, resource.RLIMIT_NPROC]]",
        "import resource\n",
    )
    result = evaluate_candidate(code, [[]])
    expected = [
        [512 * 1024**2, 512 * 1024**2],
        [2, 3],
        [0, 0],
        [0, 0],
        [32, 32],
        [16, 16],
    ]
    assert compare_oracles(result, [expected]) == [True], result


def test_actual_cpu_limit_stops_busy_candidate():
    """Exercise the native hard CPU limit with an actual busy candidate instead of a mocked exit code."""
    result = evaluate_candidate(candidate("while True:\n    pass"), [[]])
    assert result["status"] == "failed", result
    assert not result["results"]


def test_actual_uid_env_host_paths_network_and_writes(tmp_path, monkeypatch):
    """Prove native UID65534/credential clearing and absence of host files/network/write capability."""
    private = tmp_path / "PRIVATE-CANARY"
    private.write_text("fixture-only-secret")
    monkeypatch.setenv("VAULT_TOKEN", "fixture-vault-canary")
    monkeypatch.setenv("DATABASE_URL", "fixture-db-canary")
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        body = f"""assert os.getuid() == 65534 and os.getgid() == 65534
assert 'VAULT_TOKEN' not in os.environ and 'DATABASE_URL' not in os.environ
assert not os.path.exists({str(private)!r}) and not os.path.exists('/home')
assert not os.path.exists('/var/run/docker.sock')
try:
    open('/tmp/coding-write-probe', 'w')
except OSError:
    pass
else:
    raise AssertionError('writable filesystem')
connection = socket.socket()
connection.settimeout(0.1)
try:
    connection.connect(('127.0.0.1', {listener.getsockname()[1]}))
except OSError:
    pass
else:
    raise AssertionError('host network reachable')
return 'isolated' """
        result = evaluate_candidate(candidate(body, "import os, socket\n"), [[]])
    assert result["status"] == "completed" and compare_oracles(
        result, ["isolated"]
    ) == [True], result
    assert private.read_text() == "fixture-only-secret"


@pytest.mark.parametrize(
    "mode", ["marker", "stdout", "stderr", "exit", "memory", "exception"]
)
def test_actual_candidate_failure_cannot_self_certify(mode):
    """Reject protocol/limit/exception failures and printed PASS without accepting an invented functional result."""
    bodies = {
        "marker": 'print("TESTS_PASSED")\nreturn 123',
        "stdout": 'print("x" * 200000)\nreturn 123',
        "stderr": 'sys.stderr.write("x" * 20000)\nreturn 123',
        "exit": "os._exit(0)",
        "memory": "return bytearray(1024**3)",
        "exception": 'raise ValueError("private candidate diagnostic")',
    }
    result = evaluate_candidate(candidate(bodies[mode], "import os, sys\n"), [[]])
    assert compare_oracles(result, [123]) == [False]
    assert result["status"] in {"invalid_output", "output_limit", "failed", "completed"}


@pytest.mark.parametrize("mode", ["timeout", "cancel"])
def test_actual_stalled_worker_is_joined_without_surviving_namespace(monkeypatch, mode):
    """Stop an actual sleeping candidate and require no fixed-worker process to remain after evaluator return."""
    monkeypatch.setattr(module, "MAX_SECONDS", 0.1)
    stop = threading.Event()
    if mode == "cancel":
        timer = threading.Timer(0.03, stop.set)
        timer.start()
    result = evaluate_candidate(
        candidate("time.sleep(60)\nreturn 1", "import time\n"), [[]], stop
    )
    if mode == "cancel":
        timer.join()
    assert result["status"] == mode + ("led" if mode == "cancel" else ""), result
    survivors = []
    for path in Path("/proc").glob("[0-9]*/cmdline"):
        try:
            arguments = path.read_bytes().split(b"\0")
        except OSError:
            continue
        if b"/worker.py" in arguments or str(module.WORKER).encode() in arguments:
            survivors.append(path.parent.name)
    assert not survivors


@pytest.mark.asyncio
async def test_outer_cancellation_joins_actual_evaluator_thread():
    """Propagate a real outer cancellation through the owned stop event and join sandbox/thread cleanup."""
    stop = threading.Event()
    entered = threading.Event()
    exited = threading.Event()

    def run():
        """Own a real blocking evaluator and record its completion before caller cancellation returns."""
        entered.set()
        try:
            return evaluate_candidate(
                candidate("time.sleep(60)\nreturn 1", "import time\n"), [[]], stop
            )
        finally:
            exited.set()

    task = asyncio.create_task(joined_work(stop, run))
    assert await asyncio.to_thread(entered.wait, 2)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert exited.is_set() and stop.is_set()


@pytest.mark.parametrize(
    "code,inputs", [(None, [[]]), ("x" * 8193, [[]]), ("code", []), ("code", [[]] * 17)]
)
def test_invalid_requests_reject_before_process_start(monkeypatch, code, inputs):
    """Reject bounded evaluator-contract violations before spawning any namespace process."""

    def forbidden(*arguments, **options):
        """Prove invalid evaluator input cannot start an OS process."""
        pytest.fail("invalid request started process")

    monkeypatch.setattr(module.subprocess, "Popen", forbidden)
    with pytest.raises(ValueError):
        evaluate_candidate(code, inputs)
