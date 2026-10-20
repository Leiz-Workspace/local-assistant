"""Supervise finite approved test/lint commands over borrowed readonly snapshots with sealed thread-only policy and bounded private observations."""

import base64
import hashlib
import logging
import os
import selectors
import signal
import stat
import subprocess
import threading
from copy import deepcopy
from time import monotonic
from uuid import UUID

from src.application.services.check_policy import (
    MAX_STDERR,
    MAX_STDOUT,
    PROFILES,
    WALL_SECONDS,
    execution_policy,
)
from src.application.services.workspace_policy import WorkspaceAccessError
from src.infrastructure.check_seccomp import thread_filter
from src.infrastructure.checkpoint_storage import ancestor_identities

logger = logging.getLogger(__name__)


class NativeChecks:
    """Borrow retained private directory capabilities for one nonretrying isolated attempt and preserve actual execution observations."""

    def __init__(self, snapshot, runtime, profile, cpu, identifier, stop=None):
        """Bind only finite trusted scope and borrowed pins without reading project code or launching a program."""
        if (
            type(profile) is not str
            or profile not in PROFILES
            or type(identifier) is not UUID
        ):
            raise WorkspaceAccessError("checks_runner_scope_invalid", 422)
        self.snapshot, self.runtime = snapshot, runtime
        self.profile, self.cpu, self.identifier = profile, cpu, identifier
        self.policy = execution_policy(cpu)
        self.stop = stop if stop is not None else threading.Event()
        self.attempted = False
        self.launcher = None
        self.observation = dict(
            description="Untrusted isolated command observations, not functional quality or source-edit approval.",
            job_id=str(identifier),
            profile=profile,
            started_acknowledged=False,
            outcome="not_started",
            exit_code=None,
            elapsed_seconds=0.0,
            stdout_base64="",
            stderr_base64="",
            stdout_bytes=0,
            stderr_bytes=0,
            stdout_sha256=hashlib.sha256(b"").hexdigest(),
            stderr_sha256=hashlib.sha256(b"").hexdigest(),
            stdout_complete=False,
            stderr_complete=False,
            output_encoding="base64",
            output_is_untrusted=True,
            quality_evaluated=False,
            host_source_write_capability=False,
            cleanup_uncertain=False,
            policy=self.policy,
        )
        logger.info("checks_runner_bound job_id=%s", identifier)

    def command(self, filter_descriptor):
        """Build only fixed namespace/resource/profile arguments after native private pin and affinity checks."""
        if self.policy != execution_policy(self.cpu):
            raise WorkspaceAccessError("checks_runner_policy_changed", 409)
        if (
            os.getuid() == 0
            or os.getuid() != os.geteuid()
            or os.getgid() != os.getegid()
            or self.cpu not in os.sched_getaffinity(0)
        ):
            raise WorkspaceAccessError("checks_runner_identity_or_cpu_invalid", 503)
        identities = []
        for descriptor in (self.snapshot, self.runtime):
            if type(descriptor) is not int or descriptor < 3:
                raise WorkspaceAccessError("checks_runner_pin_invalid", 503)
            info = os.fstat(descriptor)
            if (
                not stat.S_ISDIR(info.st_mode)
                or info.st_uid != os.getuid()
                or stat.S_IMODE(info.st_mode) != 0o700
            ):
                raise WorkspaceAccessError("checks_runner_pin_invalid", 503)
            identities.append((info.st_dev, info.st_ino))
        if identities[0] in ancestor_identities(self.runtime) or identities[
            1
        ] in ancestor_identities(self.snapshot):
            raise WorkspaceAccessError("checks_runner_pin_overlap", 503)
        return [
            "/usr/bin/bwrap",
            "--unshare-all",
            "--unshare-user",
            "--disable-userns",
            "--assert-userns-disabled",
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
            "--ro-bind-fd",
            str(self.snapshot),
            "/snapshot",
            "--ro-bind-fd",
            str(self.runtime),
            "/runtime",
            "--proc",
            "/proc",
            "--dev",
            "/dev",
            "--size",
            str(self.policy["scratch_bytes"]),
            "--tmpfs",
            "/tmp",
            "--remount-ro",
            "/",
            "--chdir",
            "/snapshot",
            "--uid",
            str(os.getuid()),
            "--gid",
            str(os.getgid()),
            "--setenv",
            "PATH",
            "/runtime/bin:/usr/bin:/bin",
            "--setenv",
            "LANG",
            "C.UTF-8",
            "--setenv",
            "TMPDIR",
            "/tmp",
            "--setenv",
            "MALLOC_ARENA_MAX",
            "1",
            "--setenv",
            "RAYON_NUM_THREADS",
            "1",
            "--seccomp",
            str(filter_descriptor),
            "--",
            "/usr/bin/prlimit",
            "--as=536870912",
            "--cpu=2:3",
            "--fsize=1048576",
            "--nofile=64",
            "--nproc=16",
            "--core=0",
            "--",
            *PROFILES[self.profile].argv,
        ]

    def check(self, deadline):
        """Refuse cancellation or elapsed wall budget before another child launch, pipe read or wait."""
        if self.stop.is_set():
            self.observation["outcome"] = "cancelled"
            raise WorkspaceAccessError("checks_cancelled", 503)
        if monotonic() >= deadline:
            self.observation["outcome"] = "wall_timeout"
            raise WorkspaceAccessError("checks_timeout", 504)

    def run(self):
        """Own one dedicated launcher thread so inherited affinity is enforceable without pinning a reusable caller thread."""
        if self.attempted:
            raise WorkspaceAccessError("checks_attempt_replayed", 409)
        self.attempted = True
        results, errors = [], []
        completed = threading.Event()

        def launch():
            """Retain actual native observations or failure until the controller joins this owned single-attempt thread."""
            try:
                results.append(self.execute())
            except BaseException as error:
                errors.append(error)
            finally:
                completed.set()

        thread = threading.Thread(
            target=launch, name="checks-native-" + self.identifier.hex
        )
        self.launcher = thread
        failure = None
        try:
            try:
                thread.start()
            except BaseException as error:
                self.stop.set()
                failure = error
            finally:
                if thread.ident is not None:
                    while not completed.is_set():
                        try:
                            completed.wait(0.05)
                        except BaseException as error:
                            self.stop.set()
                            failure = failure if failure is not None else error
                    try:
                        thread.join()
                    except BaseException as error:
                        failure = failure if failure is not None else error
                    logger.info(
                        "checks_launcher_thread_joined job_id=%s", self.identifier
                    )
                self.launcher = None
            if failure is not None:
                raise failure
            if errors:
                raise errors[0]
            return results[0]
        except BaseException:
            if self.observation["outcome"] == "not_started":
                self.observation["outcome"] = "supervisor_failed"
            raise

    def execute(self):
        """Pin only the owned launcher, pump bounded child output and join native work before its thread can end."""
        if not self.attempted or threading.current_thread() is not self.launcher:
            raise WorkspaceAccessError("checks_launcher_scope_invalid", 503)
        started = monotonic()
        deadline = started + WALL_SECONDS
        process = None
        stdout, stderr = bytearray(), bytearray()
        eof = set()
        selector = selectors.DefaultSelector()
        try:
            self.check(deadline)
            if self.cpu not in os.sched_getaffinity(0):
                raise WorkspaceAccessError("checks_runner_identity_or_cpu_invalid", 503)
            os.sched_setaffinity(0, {self.cpu})
            logger.info("checks_launcher_thread_pinned job_id=%s", self.identifier)
            with thread_filter() as filter_descriptor:
                try:
                    command = self.command(filter_descriptor)
                    self.check(deadline)
                    process = subprocess.Popen(
                        command,
                        stdin=subprocess.DEVNULL,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        cwd="/",
                        env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"},
                        pass_fds=(self.snapshot, self.runtime, filter_descriptor),
                        start_new_session=True,
                        umask=0o077,
                    )
                    self.observation.update(
                        started_acknowledged=True, outcome="running"
                    )
                    logger.info("checks_child_started job_id=%s", self.identifier)
                    for stream, label in (
                        (process.stdout, "stdout"),
                        (process.stderr, "stderr"),
                    ):
                        os.set_blocking(stream.fileno(), False)
                        selector.register(stream, selectors.EVENT_READ, label)
                    while selector.get_map():
                        self.check(deadline)
                        for key, _ in selector.select(
                            min(0.05, max(0, deadline - monotonic()))
                        ):
                            output = stdout if key.data == "stdout" else stderr
                            limit = MAX_STDOUT if key.data == "stdout" else MAX_STDERR
                            chunk = os.read(key.fd, min(4096, limit + 1 - len(output)))
                            if not chunk:
                                eof.add(key.data)
                                selector.unregister(key.fileobj)
                                key.fileobj.close()
                                continue
                            if len(output) + len(chunk) > limit:
                                output.extend(chunk[: limit - len(output)])
                                self.observation["outcome"] = key.data + "_limit"
                                raise WorkspaceAccessError("checks_output_limit", 503)
                            output.extend(chunk)
                    self.check(deadline)
                    try:
                        code = process.wait(timeout=max(0.001, deadline - monotonic()))
                    except subprocess.TimeoutExpired:
                        self.observation["outcome"] = "wall_timeout"
                        raise WorkspaceAccessError("checks_timeout", 504) from None
                    self.observation.update(outcome="exited", exit_code=code)
                finally:
                    if process is not None:
                        if process.poll() is None:
                            try:
                                os.killpg(process.pid, signal.SIGKILL)
                            except ProcessLookupError:
                                pass
                            except OSError:
                                self.observation["cleanup_uncertain"] = True
                                logger.warning(
                                    "checks_group_signal_fallback job_id=%s",
                                    self.identifier,
                                )
                                process.kill()
                        try:
                            process.wait()
                        finally:
                            self.observation["exit_code"] = process.poll()
                            for stream in (process.stdout, process.stderr):
                                if not stream.closed:
                                    try:
                                        stream.close()
                                    except OSError:
                                        self.observation["cleanup_uncertain"] = True
                                        logger.warning(
                                            "checks_pipe_cleanup_uncertain job_id=%s",
                                            self.identifier,
                                        )
                        logger.info("checks_child_joined job_id=%s", self.identifier)
        except WorkspaceAccessError as error:
            if self.observation["outcome"] in {"not_started", "running"}:
                self.observation["outcome"] = "supervisor_failed"
            logger.warning(
                "checks_attempt_rejected job_id=%s code=%s", self.identifier, error.code
            )
            raise
        except (OSError, ValueError):
            if self.observation["outcome"] == "exited":
                self.observation["cleanup_uncertain"] = True
            elif self.observation["outcome"] in {"not_started", "running"}:
                self.observation["outcome"] = "supervisor_failed"
            raise WorkspaceAccessError("checks_supervisor_unavailable", 503) from None
        finally:
            selector.close()
            self.observation.update(
                stdout_base64=base64.b64encode(stdout).decode("ascii"),
                stderr_base64=base64.b64encode(stderr).decode("ascii"),
                stdout_bytes=len(stdout),
                stderr_bytes=len(stderr),
                stdout_sha256=hashlib.sha256(stdout).hexdigest(),
                stderr_sha256=hashlib.sha256(stderr).hexdigest(),
                stdout_complete="stdout" in eof,
                stderr_complete="stderr" in eof,
                elapsed_seconds=round(monotonic() - started, 6),
            )
            logger.info(
                "checks_attempt_observed job_id=%s outcome=%s",
                self.identifier,
                self.observation["outcome"],
            )
        return deepcopy(self.observation)
