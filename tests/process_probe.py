"""Find processes that still carry a probe marker, allowing a bounded window for asynchronous kernel teardown."""

import os
import signal
import time
from pathlib import Path

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


def reap_survivors(marker):
    """Wait for teardown, then SIGKILL anything left and describe it so a leak fails fast and readably."""
    survivors = surviving_processes(marker)
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
