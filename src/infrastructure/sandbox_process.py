"""Run bubblewrap sandboxes so that the caller regains control only after the sandbox PID namespace is gone."""

import json
import logging
import math
import os
import select
import signal
import subprocess
import time

logger = logging.getLogger(__name__)
TEARDOWN_SECONDS = 5.0
INFO_SECONDS = 5.0
REPORT_GRACE_SECONDS = 0.5
MAX_INFO_BYTES = 4096


def poll_once(descriptor, deadline):
    """Wait until the descriptor is readable or the deadline passes; poll, unlike select, accepts any descriptor number."""
    poller = select.poll()
    poller.register(descriptor, select.POLLIN)
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return False
        if poller.poll(math.ceil(remaining * 1000)):
            return True


class Sandbox:
    """Own a bwrap launcher and a pidfd for the init of the PID namespace it reports through --info-fd.

    The launcher exits as soon as the sandboxed command exits, before the namespace init, and on
    a kill only the launcher dies at once. The kernel completes an init's exit only after every
    other process in its namespace has exited and been reaped, so waiting for the init's pidfd is
    what proves that no sandboxed process still holds the payload copy or the caller's streams.
    """

    def __init__(self, args, **options):
        """Start the launcher and wait (bounded) for the namespace init it reports."""
        if os.path.basename(args[0]) != "bwrap":
            raise ValueError("sandbox launcher must be bwrap")
        self.init = None
        self.state = "pending"
        self.outcome = None
        self.buffer = b""
        self.reader, writer = os.pipe2(os.O_CLOEXEC)
        try:
            try:
                self.process = subprocess.Popen(
                    [args[0], "--info-fd", str(writer), *args[1:]],
                    pass_fds=(*options.pop("pass_fds", ()), writer),
                    **options,
                )
            finally:
                os.close(writer)
        except BaseException:
            self.close_reader()
            raise
        try:
            self.read_info(time.monotonic() + INFO_SECONDS, eof_means_absent=True)
        except BaseException:
            self.retire("interrupted")
            raise

    def close_reader(self):
        """Close the info pipe once the report is complete or can no longer arrive."""
        if self.reader is not None:
            os.close(self.reader)
            self.reader = None

    def complete_report(self):
        """Return a 1-tuple with the parsed report once the buffer holds a complete JSON value, else None."""
        try:
            return (json.JSONDecoder().raw_decode(self.buffer.decode())[0],)
        except ValueError:
            return None

    def exited_by_itself(self):
        """Return whether the launcher exited on its own, as bwrap does when it fails before cloning."""
        try:
            return self.process.wait(timeout=1) >= 0
        except subprocess.TimeoutExpired:
            return False

    def read_info(self, deadline, eof_means_absent=False):
        """Read the launcher report until it parses, the pipe closes, or the deadline passes."""
        try:
            while self.reader is not None:
                report = self.complete_report()
                if report is not None:
                    self.adopt(report[0])
                    self.close_reader()
                    return
                if not poll_once(self.reader, deadline):
                    return
                chunk = os.read(self.reader, MAX_INFO_BYTES + 1 - len(self.buffer))
                if not chunk:
                    # Only an empty report from a launcher that exited by itself proves no namespace was created.
                    absent = (
                        eof_means_absent and not self.buffer and self.exited_by_itself()
                    )
                    self.state = "absent" if absent else "unknown"
                    self.close_reader()
                    return
                self.buffer += chunk
                if len(self.buffer) > MAX_INFO_BYTES:
                    self.state = "unknown"
                    self.close_reader()
                    return
        except (OSError, ValueError):
            self.state = "unknown"
            self.close_reader()

    def adopt(self, info):
        """Open a pidfd for the reported init, verifying it is still the process in the reported namespace."""
        pid = info.get("child-pid") if isinstance(info, dict) else None
        namespace = info.get("pid-namespace") if isinstance(info, dict) else None
        if type(pid) is not int or pid <= 0 or type(namespace) is not int:
            self.state = "unknown"
            return
        try:
            descriptor = os.pidfd_open(pid)
        except ProcessLookupError:
            # The init has already exited and been reaped, which implies an empty namespace.
            self.state = "absent"
            return
        except OSError:
            self.state = "unknown"
            return
        try:
            same = os.readlink(f"/proc/{pid}/ns/pid") == f"pid:[{namespace}]"
        except (FileNotFoundError, ProcessLookupError):
            same = None
        except OSError:
            os.close(descriptor)
            self.state = "unknown"
            return
        if same is False:
            # The PID was recycled, so the reported init had already exited and been reaped.
            os.close(descriptor)
            self.state = "absent"
            return
        # same is None: the opened process exited before its namespace could be read; its pidfd still tells.
        self.init = descriptor
        self.state = "running"

    def kill_init(self):
        """Send SIGKILL to the namespace init, which makes the kernel kill every other process in it."""
        if self.init is None:
            return True
        try:
            signal.pidfd_send_signal(self.init, signal.SIGKILL)
        except ProcessLookupError:
            pass
        except OSError:
            return False
        return True

    def wait_init(self, deadline):
        """Poll the init pidfd until it reports exit or the deadline passes."""
        if self.init is None:
            return self.state == "absent"
        try:
            return poll_once(self.init, deadline)
        except (OSError, ValueError):
            return False

    def retire(self, reason):
        """Kill the namespace init and the launcher, reap the launcher, and wait (bounded) until the init has exited.

        Returns whether the namespace was confirmed gone; never raises for operating-system errors.
        """
        if self.outcome is not None:
            return self.outcome
        started = time.monotonic()
        deadline = started + TEARDOWN_SECONDS
        signalled = True
        try:
            if self.state == "pending":
                # A live launcher reports within milliseconds of cloning. Read that before killing it,
                # because a child cloned but not yet reported would otherwise be left behind unnamed.
                self.read_info(min(deadline, time.monotonic() + REPORT_GRACE_SECONDS))
            signalled = self.kill_init()
        finally:
            try:
                self.process.kill()
            except OSError:
                pass
            self.process.wait()
        try:
            if self.state == "pending":
                self.read_info(deadline)
                if self.state == "pending":
                    self.state = "unknown"
                signalled = self.kill_init() and signalled
            # The init may also die through --die-with-parent, so its exit alone decides.
            confirmed = self.wait_init(deadline)
        finally:
            self.close_reader()
            if self.init is not None:
                os.close(self.init)
                self.init = None
        elapsed_ms = round((time.monotonic() - started) * 1000)
        if not confirmed:
            logger.warning(
                "sandbox_namespace_retirement_unconfirmed reason=%s state=%s signalled=%s elapsed_ms=%d",
                reason,
                self.state,
                signalled,
                elapsed_ms,
            )
        elif reason != "exit":
            logger.info(
                "sandbox_namespace_retired reason=%s state=%s elapsed_ms=%d",
                reason,
                self.state,
                elapsed_ms,
            )
        self.outcome = confirmed
        return confirmed


def wait_launcher(process, args, timeout, deadline):
    """Wait for the launcher to exit, waking on its pidfd instead of Popen's sleep-polling, and reap it."""
    if process.returncode is not None:
        return process.returncode
    try:
        # The launcher is an unreaped child, so its PID cannot be recycled before this opens.
        descriptor = os.pidfd_open(process.pid)
    except OSError:
        try:
            return process.wait(timeout=max(0, deadline - time.monotonic()))
        except subprocess.TimeoutExpired:
            raise subprocess.TimeoutExpired(args, timeout) from None
    try:
        if not poll_once(descriptor, deadline):
            raise subprocess.TimeoutExpired(args, timeout)
    finally:
        os.close(descriptor)
    return process.wait()


def run_sandbox(args, *, timeout, **options):
    """Run a bwrap sandbox like subprocess.run with file or DEVNULL streams, returning or raising only after its namespace is gone."""
    streams = (options.get("stdin"), options.get("stdout"), options.get("stderr"))
    if any(stream == subprocess.PIPE for stream in streams):
        raise ValueError("run_sandbox streams must be files or DEVNULL")
    deadline = time.monotonic() + timeout
    sandbox = Sandbox(args, **options)
    try:
        returncode = wait_launcher(sandbox.process, args, timeout, deadline)
    except subprocess.TimeoutExpired:
        sandbox.retire("timeout")
        raise
    except BaseException:
        sandbox.retire("interrupted")
        raise
    sandbox.retire("exit")
    return subprocess.CompletedProcess(args, returncode)
