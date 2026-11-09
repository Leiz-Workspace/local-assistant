"""Verify that sandbox runs give control back only after the PID namespace is gone, on exit, timeout and interruption."""

import errno
import logging
import os
import resource
import signal
import subprocess
import tempfile
import threading
import time
from uuid import uuid4

import pytest
from process_probe import (
    all_exited,
    hold_namespace,
    reap_survivors,
    surviving_processes,
    watch_teardown,
)

from src.infrastructure import sandbox_process as module
from src.infrastructure.file_verifier import sandbox_command
from src.infrastructure.sandbox_process import Sandbox, run_sandbox

# A worker and a nested child that each touch 256 MiB, so their exit takes long enough
# that returning before the namespace teardown would be observable.
HEAVY = 'import subprocess,sys,time; b=b"x"*(256<<20); subprocess.Popen([sys.executable,"-c","import time; b=b\\"x\\"*(256<<20); time.sleep(30)",sys.argv[1]]); time.sleep(30)'
LEFTOVER = 'import subprocess,sys,time; subprocess.Popen([sys.executable,"-c","import time; b=b\\"x\\"*(256<<20); time.sleep(30)",sys.argv[1]], start_new_session=True); time.sleep(2)'
STREAMS = {
    "stdout": subprocess.DEVNULL,
    "stderr": subprocess.DEVNULL,
    "env": {},
    "close_fds": True,
    "start_new_session": True,
}


def run(command, timeout):
    """Run a sandbox with an empty payload and discarded output, as the document callers do."""
    with tempfile.TemporaryFile() as source:
        return run_sandbox(command, stdin=source, timeout=timeout, **STREAMS)


def test_normal_exit_returns_status_and_output():
    """A finished sandbox reports the worker's exit status and output like subprocess.run."""
    command = sandbox_command(
        [
            "/venv/bin/python",
            "-c",
            "import sys; sys.stdout.write(sys.stdin.read()); raise SystemExit(3)",
        ]
    )
    with tempfile.TemporaryFile() as source, tempfile.TemporaryFile() as output:
        source.write(b"payload-bytes")
        source.seek(0)
        result = run_sandbox(
            command,
            stdin=source,
            stdout=output,
            stderr=subprocess.DEVNULL,
            timeout=10,
            env={},
            close_fds=True,
            start_new_session=True,
        )
        output.seek(0)
        assert (result.returncode, output.read()) == (3, b"payload-bytes")
    assert result.args == command


def test_normal_exit_waits_for_the_namespace_init_and_leftovers():
    """The launcher exits with the worker, before the init; a leftover descendant must be gone on return."""
    marker = "sandbox-leftover-" + uuid4().hex
    command = sandbox_command(["/venv/bin/python", "-c", LEFTOVER, marker])
    try:
        # Init, worker and the detached leftover all carry the marker inside the namespace.
        report = watch_teardown(lambda: run(command, 30), marker, 3)
        assert report.error is None and report.result.returncode == 0
        assert report.held == 3 and report.exited_at_return is True
    finally:
        reap_survivors(marker, timeout=0)


@pytest.mark.parametrize("attempt", range(3))
def test_timeout_returns_only_after_the_namespace_is_gone(attempt):
    """Init, worker and nested child, all seen alive first, have exited when the timeout reaches the caller."""
    marker = "sandbox-timeout-" + uuid4().hex
    command = sandbox_command(["/venv/bin/python", "-c", HEAVY, marker])
    try:
        started = time.monotonic()
        report = watch_teardown(lambda: run(command, 2.5), marker, 3)
        assert isinstance(report.error, subprocess.TimeoutExpired)
        assert (report.error.cmd, report.error.timeout) == (command, 2.5)
        assert report.held == 3 and report.exited_at_return is True
        assert time.monotonic() - started < 10
    finally:
        reap_survivors(marker, timeout=0)


def test_interruption_retires_the_namespace_before_propagating():
    """An exception raised in the waiting thread (as on cancellation) still tears the namespace down first."""
    marker = "sandbox-interrupt-" + uuid4().hex
    command = sandbox_command(["/venv/bin/python", "-c", HEAVY, marker])
    main = threading.main_thread().ident
    lock = threading.Lock()
    held, done = [], []

    class Interrupted(Exception):
        """Stand in for an asynchronous interruption delivered during the wait."""

    def interrupt(signum, frame):
        """Raise inside the waiting main thread."""
        raise Interrupted

    def trigger():
        """Interrupt once, only after the whole tree is up and only while the call is still running."""
        found = hold_namespace(marker, 3)
        with lock:
            held.extend(found)
            if len(found) == 3 and not done:
                signal.pthread_kill(main, signal.SIGALRM)

    previous = signal.signal(signal.SIGALRM, interrupt)
    watcher = threading.Thread(target=trigger, daemon=True)
    try:
        watcher.start()
        try:
            with pytest.raises(Interrupted):
                run(command, 60)
        finally:
            with lock:
                done.append(True)
        assert len(held) == 3 and all_exited(held)
    finally:
        watcher.join()
        signal.signal(signal.SIGALRM, previous)
        for descriptor in held:
            os.close(descriptor)
        reap_survivors(marker, timeout=0)


def test_interruption_before_the_report_is_read_still_retires_the_namespace(
    monkeypatch,
):
    """An interruption inside the constructor, before the report is adopted, still finds and tears down the namespace."""
    marker = "sandbox-pending-" + uuid4().hex
    command = sandbox_command(["/venv/bin/python", "-c", HEAVY, marker])
    original = Sandbox.read_info
    held, calls = [], []

    class Interrupted(Exception):
        """Stand in for an interruption delivered while the constructor waits for the report."""

    def interrupted_once(self, deadline, eof_means_absent=False):
        """Let the tree come up with its report still unread, then interrupt the constructor's read."""
        if not calls:
            calls.append(True)
            held.extend(hold_namespace(marker, 3))
            raise Interrupted
        return original(self, deadline, eof_means_absent)

    monkeypatch.setattr(module.Sandbox, "read_info", interrupted_once)
    try:
        with pytest.raises(Interrupted):
            run(command, 30)
        assert len(held) == 3 and all_exited(held)
    finally:
        for descriptor in held:
            os.close(descriptor)
        reap_survivors(marker, timeout=0)


def test_descriptor_numbers_beyond_the_select_limit_work(caplog):
    """Descriptor numbers of 1024 and above, normal in a busy service, must not break the launch or the waits."""
    soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
    wanted = 1400
    if hard != resource.RLIM_INFINITY and hard < wanted:
        pytest.skip("the hard descriptor limit is below what this test needs")
    if soft != resource.RLIM_INFINITY and soft < wanted:
        resource.setrlimit(resource.RLIMIT_NOFILE, (wanted, hard))
    fillers = []
    try:
        # open() returns the lowest free number, so this fills every slot below 1100.
        while not fillers or fillers[-1] < 1100:
            fillers.append(os.open("/dev/null", os.O_RDONLY | os.O_CLOEXEC))
        with caplog.at_level(logging.WARNING):
            result = run(sandbox_command(["/venv/bin/python", "-c", "pass"]), 10)
        assert result.returncode == 0
        assert "sandbox_namespace_retirement_unconfirmed" not in caplog.text
    finally:
        for descriptor in fillers:
            os.close(descriptor)
        resource.setrlimit(resource.RLIMIT_NOFILE, (soft, hard))


def fake_launcher(tmp_path, body):
    """Write a stand-in launcher named bwrap that runs the given bash body (dash cannot redirect to fd 10 and above)."""
    path = tmp_path / "bwrap"
    path.write_text("#!/bin/bash\n" + body + "\n")
    path.chmod(0o755)
    return [str(path)]


@pytest.mark.parametrize(
    "body,returncode,warned",
    [
        ("exit 1", 1, False),
        ("kill -9 $$", -9, True),
        ('printf \'{"child-pid": 12\' >&"$2"; exit 0', 0, True),
    ],
)
def test_reportless_launcher_counts_as_no_namespace_only_after_failing_by_itself(
    tmp_path, caplog, body, returncode, warned
):
    """No report means no namespace only when the launcher exited on its own; a killed launcher or a partial report stays unconfirmed."""
    with caplog.at_level(logging.WARNING):
        result = run_sandbox(fake_launcher(tmp_path, body), timeout=10, **STREAMS)
    assert result.returncode == returncode
    assert (
        "sandbox_namespace_retirement_unconfirmed reason=exit state=unknown"
        in caplog.text
    ) is warned


def test_launcher_failure_before_any_namespace_is_not_reported(caplog):
    """A bwrap that fails before cloning reports nothing and leaves no namespace to wait for."""
    with caplog.at_level(logging.WARNING):
        result = run_sandbox(
            ["/usr/bin/bwrap", "--no-such-option"], timeout=10, **STREAMS
        )
    assert result.returncode != 0
    assert "sandbox_namespace_retirement_unconfirmed" not in caplog.text


def test_unconfirmed_teardown_is_bounded_and_reported(monkeypatch, caplog):
    """If the init outlives the window, retirement stops at the bound and logs it without private detail."""
    marker = "sandbox-unconfirmed-" + uuid4().hex
    # Without --die-with-parent and without the pidfd kill, the init survives the launcher.
    command = [
        part
        for part in sandbox_command(["/venv/bin/python", "-c", HEAVY, marker])
        if part != "--die-with-parent"
    ]
    monkeypatch.setattr(module.signal, "pidfd_send_signal", lambda *args: None)
    monkeypatch.setattr(module, "TEARDOWN_SECONDS", 0.3)
    try:
        started = time.monotonic()
        with caplog.at_level(logging.WARNING):
            with pytest.raises(subprocess.TimeoutExpired):
                run(command, 1)
        assert 1.25 <= time.monotonic() - started < 5
        assert (
            "sandbox_namespace_retirement_unconfirmed reason=timeout state=running"
            in caplog.text
        )
        assert marker not in caplog.text
    finally:
        leaked = reap_survivors(marker, timeout=0)
    assert leaked, "the surviving init should have been found and killed by the test"
    assert surviving_processes(marker) == []


def test_pidfd_failure_is_reported_unconfirmed(monkeypatch, caplog):
    """A pidfd error other than a missing process must not be mistaken for a finished namespace."""

    def exhausted(pid):
        """Fail like a process that has run out of descriptors."""
        raise OSError(errno.EMFILE, "Too many open files")

    monkeypatch.setattr(module.os, "pidfd_open", exhausted)
    with caplog.at_level(logging.WARNING):
        result = run(sandbox_command(["/venv/bin/python", "-c", "pass"]), 10)
    assert result.returncode == 0
    assert (
        "sandbox_namespace_retirement_unconfirmed reason=exit state=unknown"
        in caplog.text
    )


def detached():
    """Build a Sandbox shell without a launcher, to exercise the report checks directly."""
    sandbox = Sandbox.__new__(Sandbox)
    sandbox.init, sandbox.state, sandbox.reader = None, "pending", None
    return sandbox


@pytest.mark.parametrize(
    "info",
    [
        [],
        {},
        {"child-pid": True, "pid-namespace": 1},
        {"child-pid": 0, "pid-namespace": 1},
        {"child-pid": 1, "pid-namespace": "1"},
        {"child-pid": 1},
    ],
)
def test_malformed_launcher_report_is_unknown(info):
    """A report without a usable init PID and namespace never counts as a finished namespace."""
    sandbox = detached()
    sandbox.adopt(info)
    assert (sandbox.state, sandbox.init) == ("unknown", None)


def test_recycled_or_reaped_init_counts_as_exited():
    """A PID now owned by a process in another namespace, or no process at all, means the init is gone."""
    sandbox = detached()
    sandbox.adopt({"child-pid": os.getpid(), "pid-namespace": 1})
    assert (sandbox.state, sandbox.init) == ("absent", None)
    finished = subprocess.Popen(["/bin/true"])
    finished.wait()
    sandbox = detached()
    sandbox.adopt({"child-pid": finished.pid, "pid-namespace": 1})
    assert sandbox.state == "absent" and sandbox.init is None


def test_retire_is_idempotent_after_a_normal_exit():
    """Retiring twice returns the first outcome without touching closed descriptors."""
    with tempfile.TemporaryFile() as source:
        sandbox = Sandbox(
            sandbox_command(["/venv/bin/python", "-c", "pass"]),
            stdin=source,
            **STREAMS,
        )
    sandbox.process.wait()
    assert sandbox.retire("exit") is True
    assert sandbox.retire("exit") is True
    assert sandbox.init is None and sandbox.reader is None


@pytest.mark.parametrize("stream", ["stdin", "stdout", "stderr"])
def test_pipes_are_refused_before_launch(stream, monkeypatch):
    """Waiting without draining a pipe could deadlock, so pipes are refused before any process starts."""

    def forbidden(*args, **kwargs):
        """Fail if a process is launched for a refused configuration."""
        pytest.fail("process launched")

    monkeypatch.setattr(module.subprocess, "Popen", forbidden)
    with pytest.raises(ValueError):
        run_sandbox(["/usr/bin/bwrap"], timeout=1, **{stream: subprocess.PIPE})


def test_non_bwrap_launcher_is_refused(monkeypatch):
    """Only a bwrap launcher can report its namespace init, so anything else is refused before launch."""

    def forbidden(*args, **kwargs):
        """Fail if a process is launched for a refused launcher."""
        pytest.fail("process launched")

    monkeypatch.setattr(module.subprocess, "Popen", forbidden)
    with pytest.raises(ValueError):
        run_sandbox(["/bin/true"], timeout=1, **STREAMS)
