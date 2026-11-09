"""Find processes that carry a probe marker and check, through pidfds, that sandboxed ones are gone when a call returns."""

import os
import select
import signal
import threading
import time
from pathlib import Path
from types import SimpleNamespace

TEARDOWN_SECONDS = 5.0


def command_line(pid):
    """Return the raw command line of a PID, or None once it is gone or unreadable."""
    try:
        return (Path("/proc") / str(pid) / "cmdline").read_bytes()
    except (FileNotFoundError, PermissionError, ProcessLookupError):
        return None


def marked_processes(marker):
    """Return the PIDs whose command line currently contains the marker."""
    needle = marker.encode()
    found = []
    for process in Path("/proc").iterdir():
        if process.name.isdecimal():
            line = command_line(process.name)
            if line is not None and needle in line:
                found.append(int(process.name))
    return found


def surviving_processes(marker, timeout=TEARDOWN_SECONDS, interval=0.02):
    """Poll until no process carries the marker or the window ends, and return the survivors."""
    deadline = time.monotonic() + timeout
    while True:
        survivors = marked_processes(marker)
        if not survivors or time.monotonic() >= deadline:
            return survivors
        time.sleep(interval)


def wait_until_marked(marker, pid, timeout=TEARDOWN_SECONDS, interval=0.01):
    """Wait until a just-started PID shows the marker, since its command line is empty until exec completes."""
    deadline = time.monotonic() + timeout
    while pid not in marked_processes(marker):
        if time.monotonic() >= deadline:
            return False
        time.sleep(interval)
    return True


def reap_survivors(marker, timeout=TEARDOWN_SECONDS):
    """Wait up to the window for teardown, then SIGKILL anything left and describe it so a leak fails fast and readably."""
    survivors = surviving_processes(marker, timeout)
    described = []
    for pid in survivors:
        line = command_line(pid) or b""
        described.append(
            (pid, line.replace(b"\0", b" ").decode(errors="replace")[:160])
        )
        try:
            os.kill(pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
    return described


def namespace_processes(marker):
    """Return the marked PIDs that run in another PID namespace than this process, that is, inside a sandbox."""
    own = os.readlink("/proc/self/ns/pid")
    found = []
    for pid in marked_processes(marker):
        try:
            if os.readlink(f"/proc/{pid}/ns/pid") != own:
                found.append(pid)
        except OSError:
            continue
    return found


def hold_namespace(marker, count, timeout=TEARDOWN_SECONDS * 2, interval=0.005):
    """Wait until count sandboxed processes carry the marker, then return a pidfd for each one still present."""
    deadline = time.monotonic() + timeout
    while len(pids := namespace_processes(marker)) < count:
        if time.monotonic() >= deadline:
            return []
        time.sleep(interval)
    held = []
    for pid in pids:
        try:
            held.append(os.pidfd_open(pid))
        except ProcessLookupError:
            continue
    return held


def all_exited(descriptors):
    """Return whether every pidfd reports, at this moment, that its process has exited (zombies included)."""
    poller = select.poll()
    for descriptor in descriptors:
        poller.register(descriptor, select.POLLIN)
    return len(poller.poll(0)) == len(descriptors)


def watch_teardown(call, marker, count, timeout=TEARDOWN_SECONDS * 2):
    """Run call in a thread, hold pidfds on its sandboxed marked processes once count are up, and record
    whether all of them had exited at the moment call returned or raised."""
    lock = threading.Lock()
    held = []
    report = SimpleNamespace(result=None, error=None, held=0, exited_at_return=None)

    def target():
        """Run the call and check the held pidfds before anything else can happen."""
        try:
            report.result = call()
        except BaseException as error:
            report.error = error
        with lock:
            report.held = len(held)
            if held:
                report.exited_at_return = all_exited(held)

    thread = threading.Thread(target=target, daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + timeout
        while thread.is_alive() and time.monotonic() < deadline:
            if len(namespace_processes(marker)) >= count:
                with lock:
                    if thread.is_alive():
                        held.extend(hold_namespace(marker, count, timeout=0))
                break
            time.sleep(0.005)
        thread.join()
    finally:
        for descriptor in held:
            os.close(descriptor)
    return report
