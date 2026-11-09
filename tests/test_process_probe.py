"""Verify the bounded process probe reports real survivors, clears early when teardown finishes, and cleans up leaks."""

import subprocess
import sys
import threading
import time
from uuid import uuid4

from process_probe import (
    marked_processes,
    reap_survivors,
    surviving_processes,
    wait_until_marked,
)


def spawn(marker):
    """Start a sleeping child whose command line carries the marker, once exec has completed."""
    child = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(30)", marker],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    assert wait_until_marked(marker, child.pid)
    return child


def stop(child):
    """Kill and reap a probe child so no test leaks a sleeping process."""
    if child.poll() is None:
        child.kill()
    child.wait()


def test_live_process_is_reported_after_the_window():
    """A process that is never killed must still be reported once the window ends."""
    marker = "probe-live-" + uuid4().hex
    child = spawn(marker)
    try:
        started = time.monotonic()
        assert surviving_processes(marker, timeout=0.3) == [child.pid]
        assert time.monotonic() - started >= 0.3
    finally:
        stop(child)


def test_process_killed_during_the_window_clears_early():
    """A process that disappears partway through the window ends the wait early with no survivors."""
    marker = "probe-midway-" + uuid4().hex
    child = spawn(marker)
    timer = threading.Timer(0.2, stop, args=(child,))
    try:
        timer.start()
        started = time.monotonic()
        assert surviving_processes(marker, timeout=5) == []
        elapsed = time.monotonic() - started
        assert 0.15 <= elapsed < 4
    finally:
        timer.cancel()
        stop(child)


def test_killed_process_clears_within_the_window():
    """A killed and reaped process disappears, so the probe returns no survivors."""
    marker = "probe-killed-" + uuid4().hex
    child = spawn(marker)
    try:
        assert marked_processes(marker) == [child.pid]
    finally:
        stop(child)
    assert surviving_processes(marker) == []


def test_unknown_marker_returns_immediately():
    """With nothing to wait for, the probe returns at once instead of using the window."""
    started = time.monotonic()
    assert surviving_processes("probe-absent-" + uuid4().hex, timeout=5) == []
    assert time.monotonic() - started < 1


def test_leak_is_killed_and_described():
    """A survivor is SIGKILLed and reported with its command line so a real leak fails fast and readably."""
    marker = "probe-leak-" + uuid4().hex
    child = spawn(marker)
    try:
        started = time.monotonic()
        leaked = reap_survivors(marker)
        assert [pid for pid, _ in leaked] == [child.pid]
        assert marker in leaked[0][1]
        assert time.monotonic() - started >= 4.9
        child.wait(timeout=5)
        assert marked_processes(marker) == []
    finally:
        stop(child)
