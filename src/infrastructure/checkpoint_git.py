"""Run finite private Git plumbing under non-root filesystem/network namespaces, hard resources and joined bounded pipes."""

import logging
import os
import re
import selectors
import signal
import stat
import subprocess
import threading
from time import monotonic

from src.application.services.workspace_policy import WorkspaceAccessError

logger = logging.getLogger(__name__)
MAX_SECONDS = 5
MAX_STDOUT = 65536
MAX_STDERR = 4096
OBJECT_ID = re.compile(r"^[a-f0-9]{40}$")


class CheckpointGit:
    """Borrow pinned private directory descriptors for finite byte-only checkpoint commands without workspace Git access."""

    def __init__(self, repository, template, *, stop=None, deadline=None):
        """Bind only trusted retained capabilities and a shared cancellation/deadline without taking descriptor ownership."""
        self.repository = repository
        self.template = template
        self.stop = stop if stop is not None else threading.Event()
        self.deadline = deadline if deadline is not None else monotonic() + 20
        logger.info("checkpoint_git_bound")

    def arguments(self, operation, data, identifiers):
        """Translate a finite internal operation into fixed Git plumbing and validate every object identifier/input size."""
        if (
            type(data) is not bytes
            or len(data) > 8192
            or type(identifiers) is not tuple
            or any(
                type(value) is not str or not OBJECT_ID.fullmatch(value)
                for value in identifiers
            )
        ):
            raise WorkspaceAccessError("checkpoint_git_input_invalid", 422)
        if operation == "init" and not data and not identifiers:
            return [
                "init",
                "--quiet",
                "--bare",
                "--initial-branch=checkpoint",
                "--object-format=sha1",
                "--template=/template",
                "/repo",
            ], b""
        if operation == "blob" and not identifiers:
            return ["hash-object", "--no-filters", "-w", "--stdin"], data
        if operation == "tree" and not data and len(identifiers) == 2:
            metadata, source = identifiers
            raw = f"100644 blob {metadata}\tmetadata.json\n100644 blob {source}\tsource.bin\n".encode()
            return ["mktree"], raw
        if operation == "commit" and not data and len(identifiers) == 1:
            return [
                "commit-tree",
                identifiers[0],
                "-m",
                "Capture admitted source checkpoint",
            ], b""
        if (
            operation in {"read_blob", "read_commit", "read_tree"}
            and not data
            and len(identifiers) == 1
        ):
            kind = {"read_blob": "blob", "read_commit": "commit", "read_tree": "tree"}[
                operation
            ]
            return ["cat-file", kind, identifiers[0]], b""
        raise WorkspaceAccessError("checkpoint_git_operation_invalid", 422)

    def command(self, arguments):
        """Expose only trusted runtime and pinned private mounts inside fresh namespaces under the actual unprivileged UID/GID."""
        if (
            os.getuid() == 0
            or os.getuid() != os.geteuid()
            or os.getgid() != os.getegid()
        ):
            raise WorkspaceAccessError("checkpoint_git_identity_unsupported", 503)
        for descriptor in (self.repository, self.template):
            info = os.fstat(descriptor)
            if (
                not stat.S_ISDIR(info.st_mode)
                or info.st_uid != os.getuid()
                or stat.S_IMODE(info.st_mode) != 0o700
            ):
                raise WorkspaceAccessError("checkpoint_git_directory_unsafe", 503)
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
            "--bind-fd",
            str(self.repository),
            "/repo",
            "--ro-bind-fd",
            str(self.template),
            "/template",
            "--proc",
            "/proc",
            "--dev",
            "/dev",
            "--tmpfs",
            "/tmp",
            "--remount-ro",
            "/tmp",
            "--remount-ro",
            "/",
            "--chdir",
            "/",
            "--uid",
            str(os.getuid()),
            "--gid",
            str(os.getgid()),
            "--setenv",
            "PATH",
            "/usr/bin:/bin",
            "--setenv",
            "LANG",
            "C.UTF-8",
            "--setenv",
            "GIT_CONFIG_NOSYSTEM",
            "1",
            "--setenv",
            "GIT_CONFIG_GLOBAL",
            "/dev/null",
            "--setenv",
            "GIT_CONFIG_SYSTEM",
            "/dev/null",
            "--setenv",
            "GIT_TERMINAL_PROMPT",
            "0",
            "--setenv",
            "GIT_OPTIONAL_LOCKS",
            "0",
            "--",
            "/usr/bin/prlimit",
            "--as=268435456",
            "--cpu=2:3",
            "--fsize=262144",
            "--nofile=32",
            "--nproc=16",
            "--core=0",
            "--",
            "/usr/bin/git",
            "--no-pager",
            "-c",
            "core.hooksPath=/dev/null",
            "-c",
            "core.fsmonitor=false",
            "-c",
            "commit.gpgsign=false",
            "-c",
            "core.autocrlf=false",
            "-c",
            "core.attributesFile=/dev/null",
            "-c",
            "gc.auto=0",
            "-c",
            "user.name=Local checkpoint",
            "-c",
            "user.email=checkpoint@localhost",
            "--git-dir=/repo",
            *arguments,
        ]

    def execute(self, operation, data=b"", identifiers=()):
        """Pump bounded pipes and kill/join the owned process group before returning bytes or sanitized failure."""
        arguments, raw = self.arguments(operation, data, identifiers)
        command = self.command(arguments)
        deadline = min(self.deadline, monotonic() + MAX_SECONDS)
        process, selector = None, selectors.DefaultSelector()
        stdout, stderr, offset = bytearray(), bytearray(), 0
        try:
            if self.stop.is_set():
                raise WorkspaceAccessError("checkpoint_cancelled", 503)
            if monotonic() >= deadline:
                raise WorkspaceAccessError("checkpoint_git_timeout", 504)
            if operation == "init" and os.listdir(self.template):
                raise WorkspaceAccessError("checkpoint_template_not_empty", 503)
            process = subprocess.Popen(
                command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd="/",
                env={
                    "PATH": "/usr/bin:/bin",
                    "LANG": "C.UTF-8",
                    "GIT_CONFIG_NOSYSTEM": "1",
                    "GIT_CONFIG_GLOBAL": "/dev/null",
                    "GIT_CONFIG_SYSTEM": "/dev/null",
                    "GIT_TERMINAL_PROMPT": "0",
                    "GIT_OPTIONAL_LOCKS": "0",
                },
                pass_fds=(self.repository, self.template),
                start_new_session=True,
                umask=0o077,
            )
            for stream, event, label in [
                (process.stdin, selectors.EVENT_WRITE, "stdin"),
                (process.stdout, selectors.EVENT_READ, "stdout"),
                (process.stderr, selectors.EVENT_READ, "stderr"),
            ]:
                os.set_blocking(stream.fileno(), False)
                selector.register(stream, event, label)
            while selector.get_map():
                if self.stop.is_set():
                    raise WorkspaceAccessError("checkpoint_cancelled", 503)
                if monotonic() >= deadline:
                    raise WorkspaceAccessError("checkpoint_git_timeout", 504)
                for key, _ in selector.select(
                    min(0.05, max(0, deadline - monotonic()))
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
                        chunk = os.read(key.fd, 4096)
                        if not chunk:
                            selector.unregister(key.fileobj)
                            key.fileobj.close()
                            continue
                        output = stdout if key.data == "stdout" else stderr
                        output.extend(chunk)
                        if len(output) > (
                            MAX_STDOUT if key.data == "stdout" else MAX_STDERR
                        ):
                            raise WorkspaceAccessError(
                                "checkpoint_git_output_limit", 503
                            )
            try:
                code = process.wait(timeout=max(0.001, deadline - monotonic()))
            except subprocess.TimeoutExpired:
                raise WorkspaceAccessError("checkpoint_git_timeout", 504) from None
            if code:
                raise WorkspaceAccessError("checkpoint_git_failed", 503)
            result = bytes(stdout)
            if operation in {"blob", "tree", "commit"} and not re.fullmatch(
                rb"[a-f0-9]{40}\n", result
            ):
                raise WorkspaceAccessError("checkpoint_git_protocol", 503)
            logger.info(
                "checkpoint_git_completed operation=%s output_bytes=%d",
                operation,
                len(result),
            )
            return result
        except (OSError, ValueError):
            raise WorkspaceAccessError("checkpoint_git_unavailable", 503) from None
        finally:
            if process is not None:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait()
                for stream in (process.stdin, process.stdout, process.stderr):
                    if not stream.closed:
                        stream.close()
            selector.close()
            logger.info("checkpoint_git_joined operation=%s", operation)
