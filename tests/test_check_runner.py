"""Verify actual bounded native check observations, readonly/FD/network policy, Ruff compatibility and joined timeout/cancellation."""

import base64
import hashlib
import json
import logging
import os
import shutil
import threading
from pathlib import Path
from uuid import uuid4

import pytest

from src.application.services.workspace_policy import WorkspaceAccessError
from src.infrastructure import check_runner as module
from src.infrastructure.check_runner import NativeChecks

logger = logging.getLogger(__name__)


def sandboxed_pins():
    """Return the PIDs of host processes running a sandboxed private pin (/runtime/bin/...)."""
    pids = []
    for path in Path("/proc").glob("[0-9]*/cmdline"):
        try:
            arguments = path.read_bytes().split(b"\x00")
        except OSError:
            continue
        if {b"/runtime/bin/python3.12", b"/runtime/bin/ruff"}.intersection(arguments):
            pids.append(int(path.parent.name))
    return pids


def parent_of(pid):
    """Return the parent PID from /proc/<pid>/stat, or None once the process is gone."""
    try:
        stat = Path(f"/proc/{pid}/stat").read_text()
    except OSError:
        return None
    return int(stat.rsplit(")", 1)[1].split()[1])


def descends_from(pid, ancestor):
    """Walk the parent chain of a live process up to PID 1."""
    seen = set()
    while pid and pid > 1 and pid not in seen:
        if pid == ancestor:
            return True
        seen.add(pid)
        pid = parent_of(pid)
    return False


def orphaned(pid):
    """A process whose parent is PID 1 or a systemd user manager was reparented after its launcher exited."""
    parent = parent_of(pid)
    if parent is None:
        return False
    try:
        return Path(f"/proc/{parent}/comm").read_text().strip() == "systemd"
    except OSError:
        return False


@pytest.fixture
def native_job(tmp_path, monkeypatch):
    """Provide disposable source/private executable pins and assert every actual supervised process exits before pin teardown."""
    snapshot, runtime = tmp_path / "snapshot", tmp_path / "runtime"
    snapshot.mkdir(mode=0o700)
    runtime.mkdir(mode=0o700)
    (runtime / "bin").mkdir(mode=0o700)
    shutil.copyfile("/usr/bin/python3.12", runtime / "bin/python3.12")
    (runtime / "bin/python3.12").chmod(0o500)
    descriptors = [
        os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
        for path in (snapshot, runtime)
    ]
    original = module.subprocess.Popen
    processes = []
    original_affinity = os.sched_getaffinity(0)

    def tracked(*arguments, **options):
        """Keep only actual owned subprocess handles for mandatory joined lifecycle verification."""
        process = original(*arguments, **options)
        processes.append(process)
        return process

    monkeypatch.setattr(module.subprocess, "Popen", tracked)
    preexisting = set(sandboxed_pins())
    try:
        yield snapshot, runtime, descriptors, processes
    finally:
        assert os.sched_getaffinity(0) == original_affinity
        assert not any(
            thread.name.startswith("checks-native-") for thread in threading.enumerate()
        )
        for process in processes:
            assert process.poll() is not None
            with pytest.raises(ProcessLookupError):
                os.kill(process.pid, 0)
        for pid in sandboxed_pins():
            # Other pytest workers and concurrent CI jobs on the same host run the same pins;
            # only a process this test started, or an orphan that appeared during it, is a leak.
            assert not (
                descends_from(pid, os.getpid())
                or (pid not in preexisting and orphaned(pid))
            ), pid
        for descriptor in descriptors:
            os.close(descriptor)
        logger.info("checks_native_fixture_joined")


def fixture_source(snapshot, body):
    """Write one described trusted test fixture without importing or running its body in the host."""
    raw = (
        '"""Controlled disposable native check fixture."""\n'
        "import unittest\n\n"
        "class Fixture(unittest.TestCase):\n"
        '    """Observe one explicitly selected disposable behavior."""\n\n'
        "    def test_behavior(self):\n"
        '        """Run only inside the native readonly snapshot namespace."""\n'
        + "\n".join("        " + line for line in body.splitlines())
        + "\n"
    ).encode()
    (snapshot / "test_fixture.py").write_bytes(raw)
    return raw


def runner(native_job, profile="python_unittest", stop=None):
    """Bind the actual finite profile to retained disposable pins and one currently permitted CPU."""
    return NativeChecks(
        *native_job[2], profile, min(os.sched_getaffinity(0)), uuid4(), stop
    )


@pytest.mark.parametrize(
    "body,exit_code",
    [
        ("self.assertEqual(2 + 2, 4)", 0),
        ("self.assertEqual(2 + 2, 5)", 1),
        ('__import__("os")._exit(0)', 0),
    ],
)
def test_actual_exit_is_observed_without_forged_quality_or_changed_source(
    native_job, body, exit_code
):
    """Retain true success/failure/forged-zero exits while exposing no quality/approval or host-write authority."""
    raw = fixture_source(native_job[0], body)
    attempt = runner(native_job)
    result = attempt.run()
    assert result["started_acknowledged"] and result["outcome"] == "exited"
    assert result["exit_code"] == exit_code
    assert (
        not result["quality_evaluated"] and not result["host_source_write_capability"]
    )
    assert not result["cleanup_uncertain"]
    assert result["stdout_complete"] and result["stderr_complete"]
    assert (
        result["stdout_sha256"]
        == hashlib.sha256(base64.b64decode(result["stdout_base64"])).hexdigest()
    )
    assert (native_job[0] / "test_fixture.py").read_bytes() == raw
    result["policy"]["network"] = True
    assert not attempt.observation["policy"]["network"]
    for descriptor in native_job[2]:
        os.fstat(descriptor)


def test_actual_non_utf8_output_is_preserved_exactly_as_untrusted_base64(native_job):
    """Keep arbitrary program output bytes exact without decoding failures or marker-based certification."""
    fixture_source(native_job[0], 'import sys\nsys.stdout.buffer.write(b"\\xff\\x00")')
    result = runner(native_job).run()
    assert result["exit_code"] == 0
    assert base64.b64decode(result["stdout_base64"]) == b"\xff\x00"
    assert result["stdout_bytes"] == 2 and result["output_is_untrusted"]


@pytest.mark.parametrize("stream,limit", [("stdout", 16384), ("stderr", 4096)])
def test_actual_output_overflow_is_bounded_and_joined(native_job, stream, limit):
    """Stop overproducing real programs, retain only admitted bytes and join owned processes before returning failure."""
    fixture_source(
        native_job[0],
        f'import sys\nsys.{stream}.buffer.write(b"x" * {limit + 1})\nsys.{stream}.flush()',
    )
    attempt = runner(native_job)
    with pytest.raises(WorkspaceAccessError) as caught:
        attempt.run()
    assert caught.value.code == "checks_output_limit"
    assert attempt.observation["outcome"] == stream + "_limit"
    assert attempt.observation[stream + "_bytes"] == limit
    assert not attempt.observation[stream + "_complete"]
    assert (
        attempt.observation[stream + "_sha256"]
        == hashlib.sha256(
            base64.b64decode(attempt.observation[stream + "_base64"])
        ).hexdigest()
    )
    assert attempt.observation["exit_code"] is not None


@pytest.mark.parametrize("mode", ["timeout", "cancel"])
def test_real_stalled_worker_timeout_or_cancel_joins_before_pins_release(
    native_job, monkeypatch, mode
):
    """Exercise a real sleeping namespace with a disclosed shorter parent budget or actual cooperative cancellation."""
    fixture_source(
        native_job[0],
        "import ctypes, os, time\nctypes.CDLL(None).prctl(1,0,0,0,0)\ntry:os.setsid()\nexcept OSError:pass\ntime.sleep(10)",
    )
    stop = threading.Event()
    timer = None
    if mode == "timeout":
        monkeypatch.setattr(module, "WALL_SECONDS", 0.2)
    else:
        timer = threading.Timer(0.15, stop.set)
        timer.start()
    attempt = runner(native_job, stop=stop)
    try:
        with pytest.raises(WorkspaceAccessError) as caught:
            attempt.run()
        assert caught.value.code == (
            "checks_timeout" if mode == "timeout" else "checks_cancelled"
        )
        assert attempt.observation["started_acknowledged"]
        assert attempt.observation["exit_code"] is not None
    finally:
        if timer is not None:
            timer.join()


def test_prelaunch_stop_and_overlapping_native_pins_never_spawn(native_job):
    """Reject cancellation and an accidentally widened root capability before acknowledging any child launch."""
    stop = threading.Event()
    stop.set()
    attempt = runner(native_job, stop=stop)
    with pytest.raises(WorkspaceAccessError):
        attempt.run()
    assert not attempt.observation["started_acknowledged"] and not native_job[3]
    stop.clear()
    with pytest.raises(WorkspaceAccessError) as caught:
        attempt.run()
    assert caught.value.code == "checks_attempt_replayed" and not native_job[3]
    attempt = NativeChecks(
        native_job[2][0],
        native_job[2][0],
        "python_unittest",
        min(os.sched_getaffinity(0)),
        uuid4(),
    )
    with pytest.raises(WorkspaceAccessError) as caught:
        attempt.run()
    assert caught.value.code == "checks_runner_pin_overlap" and not native_job[3]


def test_actual_timeout_uses_owned_process_kill_if_group_signal_fails(
    native_job, monkeypatch
):
    """Join the real stalled process through its retained handle even when process-group signaling reports a controlled fault."""
    fixture_source(
        native_job[0],
        "import ctypes, os, time\nctypes.CDLL(None).prctl(1,0,0,0,0)\ntry:os.setsid()\nexcept OSError:pass\ntime.sleep(10)",
    )
    monkeypatch.setattr(module, "WALL_SECONDS", 0.15)

    def group_fault(*arguments):
        """Inject only group signaling failure while preserving real owned-handle termination."""
        raise OSError("controlled group signal fault")

    monkeypatch.setattr(module.os, "killpg", group_fault)
    attempt = runner(native_job)
    with pytest.raises(WorkspaceAccessError) as caught:
        attempt.run()
    assert caught.value.code == "checks_timeout"
    assert attempt.observation["cleanup_uncertain"]
    assert attempt.observation["exit_code"] is not None


@pytest.mark.parametrize(
    "body,expected_errno",
    [
        (
            'import mmap\ntry:mmap.mmap(-1,600*1024*1024);raise AssertionError("address space escaped")\nexcept OSError as error:print(error.errno)',
            12,
        ),
        (
            'import os\nwith open("/tmp/file","wb") as output:\n    try:os.ftruncate(output.fileno(),1048577);raise AssertionError("file ceiling escaped")\n    except OSError as error:print(error.errno)',
            27,
        ),
        (
            'import os\nopened=[]\ntry:\n    for index in range(100):opened.append(os.open("/dev/null",os.O_RDONLY))\n    raise AssertionError("FD ceiling escaped")\nexcept OSError as error:print(error.errno)\nfinally:\n    for descriptor in opened:os.close(descriptor)',
            24,
        ),
        (
            "import ctypes\nlibrary=ctypes.CDLL(None,use_errno=True)\nassert library.unshare(0x10000000)==-1\nprint(ctypes.get_errno())",
            28,
        ),
        (
            'import os\ntry:\n    for index in range(17):\n        descriptor=os.open("/tmp/file"+str(index),os.O_WRONLY|os.O_CREAT,0o600)\n        try:\n            data=b"x"*1048576\n            while data:data=data[os.write(descriptor,data):]\n        finally:os.close(descriptor)\n    raise AssertionError("scratch ceiling escaped")\nexcept OSError as error:print(error.errno)',
            28,
        ),
    ],
)
def test_actual_memory_file_fd_userns_and_tmpfs_limits(
    native_job, body, expected_errno
):
    """Attempt real bounded resource violations and require native denial under the unchanged production limits."""
    fixture_source(native_job[0], body)
    result = runner(native_job).run()
    assert result["exit_code"] == 0, base64.b64decode(result["stderr_base64"])
    assert int(base64.b64decode(result["stdout_base64"])) == expected_errno


def test_actual_hard_cpu_limit_terminates_a_soft_signal_ignoring_program(native_job):
    """Exercise the real three-second hard CPU ceiling rather than interpreting a declared resource limit as enforcement."""
    fixture_source(
        native_job[0],
        "import signal\nsignal.signal(signal.SIGXCPU,signal.SIG_IGN)\nwhile True:pass",
    )
    result = runner(native_job).run()
    assert result["outcome"] == "exited" and result["exit_code"] != 0
    assert result["elapsed_seconds"] < 6
    assert not result["quality_evaluated"]


def test_native_readonly_root_pins_env_network_and_scratch_policy(
    native_job, tmp_path, monkeypatch
):
    """Probe actual filesystem/FD authority, affinity, resources and namespace denial rather than inspecting only argv."""
    host = tmp_path / "host-canary"
    host.write_text("PRIVATE-CONTROLLED-CANARY")
    monkeypatch.setenv("CHECKS_PRIVATE_CREDENTIAL_CANARY", "MUST-NOT-ENTER")
    body = f"""import errno, json, os, resource, socket
report=dict(uid=os.getuid(),env=list(os.environ),affinity=sorted(os.sched_getaffinity(0)),host=os.path.exists({str(host)!r}),root_readonly=bool(os.statvfs("/").f_flag & os.ST_RDONLY),snapshot_readonly=bool(os.statvfs("/snapshot").f_flag & os.ST_RDONLY),runtime_readonly=bool(os.statvfs("/runtime").f_flag & os.ST_RDONLY),scratch_bytes=os.statvfs("/tmp").f_blocks*os.statvfs("/tmp").f_frsize,as_limit=resource.getrlimit(resource.RLIMIT_AS))
for descriptor in {native_job[2]!r}:
    try:os.fstat(descriptor);report["fd_"+str(descriptor)]="open"
    except OSError as error:report["fd_"+str(descriptor)]=error.errno
for key,path in [("root_write","/forbidden"),("source_write","/snapshot/test_fixture.py"),("runtime_write","/runtime/bin/python3.12")]:
    try:
        fd=os.open(path,os.O_WRONLY|os.O_CREAT,0o600);os.close(fd);report[key]="unexpected"
    except OSError as error:report[key]=error.errno
with open("/tmp/allowed","w") as output:output.write("bounded scratch")
try:socket.create_connection(("127.0.0.1",8080),timeout=.1);report["network"]=True
except OSError:report["network"]=False
print(json.dumps(report))"""
    fixture_source(native_job[0], body)
    result = runner(native_job).run()
    assert result["exit_code"] == 0, base64.b64decode(result["stderr_base64"])
    report = json.loads(base64.b64decode(result["stdout_base64"]))
    assert report["uid"] == os.getuid() != 0
    assert report["affinity"] == [min(os.sched_getaffinity(0))]
    assert (
        report["root_readonly"]
        and report["snapshot_readonly"]
        and report["runtime_readonly"]
    )
    assert report["root_write"] == report["source_write"] == 30
    assert report["runtime_write"] in {13, 30}
    assert report["scratch_bytes"] == 16777216 and report["as_limit"] == [536870912] * 2
    assert not report["host"] and not report["network"]
    assert "CHECKS_PRIVATE_CREDENTIAL_CANARY" not in report["env"]
    assert all(report["fd_" + str(descriptor)] == 9 for descriptor in native_job[2])
    assert host.read_text() == "PRIVATE-CONTROLLED-CANARY"


def test_actual_pinned_ruff_works_with_thread_only_filter_and_ignores_noqa(native_job):
    """Run the existing pinned static analyzer under the exact native policy and deny source suppression/fix authority."""
    expected = "20cf97c5db04ca9c51249dec1a54cbc96c24462df280334ada04b8f3c877b746"
    existing = next(
        (
            path
            for path in (Path.home() / ".cache/uv/archive-v0").glob("*/bin/ruff")
            if hashlib.sha256(path.read_bytes()).hexdigest() == expected
        ),
        None,
    )
    assert existing is not None, (
        "Existing pinned Ruff executable is required; no download fallback"
    )
    target = native_job[1] / "bin/ruff"
    shutil.copyfile(existing, target)
    target.chmod(0o500)
    raw = b'"""Controlled lint failure with ignored suppression."""\nprint(UNDEFINED_CANARY)  # noqa: F821\n'
    (native_job[0] / "fixture.py").write_bytes(raw)
    result = runner(native_job, "ruff_check").run()
    assert result["exit_code"] == 1, base64.b64decode(result["stderr_base64"])
    diagnostics = json.loads(base64.b64decode(result["stdout_base64"]))
    assert diagnostics[0]["code"] == "F821"
    assert not result["quality_evaluated"]
    assert (native_job[0] / "fixture.py").read_bytes() == raw


def test_native_source_cannot_widen_its_fixed_cpu_affinity(native_job):
    """Reject an actual source attempt to replace the reviewed single-CPU binding with the caller's full CPU set."""
    available = sorted(os.sched_getaffinity(0))
    fixture_source(
        native_job[0],
        f'import json,os\nreport={{}}\ntry:os.sched_setaffinity(0,{available!r});report["reset"]="unexpected"\nexcept OSError as error:report["errno"]=error.errno\nreport["affinity"]=sorted(os.sched_getaffinity(0))\nprint(json.dumps(report))',
    )
    result = runner(native_job).run()
    assert result["exit_code"] == 0
    report = json.loads(base64.b64decode(result["stdout_base64"]))
    assert report == dict(errno=1, affinity=[min(available)])


@pytest.mark.parametrize("phase", ["before_start", "lost_start_ack"])
def test_launcher_creation_or_lost_ack_failure_joins_any_started_native_work(
    native_job, monkeypatch, phase
):
    """Keep source pins until any actually started launcher/native attempt joins even if thread startup acknowledgement fails."""
    fixture_source(native_job[0], "import time\ntime.sleep(10)")
    original = module.threading.Thread.start

    def fault_start(thread):
        """Inject before launch or after real startup while retaining actual thread ownership."""
        if phase == "lost_start_ack":
            original(thread)
        raise RuntimeError("controlled launcher acknowledgement failure")

    monkeypatch.setattr(module.threading.Thread, "start", fault_start)
    attempt = runner(native_job)
    with pytest.raises(RuntimeError):
        attempt.run()
    assert attempt.launcher is None
    assert not any(
        thread.name.startswith("checks-native-") for thread in threading.enumerate()
    )
    assert all(process.poll() is not None for process in native_job[3])


def test_direct_execution_cannot_pin_a_reusable_caller_thread(native_job):
    """Refuse bypass of the owned launcher entry point before changing caller affinity or starting a child."""
    attempt = runner(native_job)
    original = os.sched_getaffinity(0)
    with pytest.raises(WorkspaceAccessError) as caught:
        attempt.execute()
    assert caught.value.code == "checks_launcher_scope_invalid"
    assert os.sched_getaffinity(0) == original and not native_job[3]
