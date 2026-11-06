"""Own an exact-source offline read-only stdio MCP subprocess with finite framing, stderr, CPU, memory and joined cleanup."""

import asyncio
import hashlib
import logging
import os
import stat
import tempfile
from pathlib import Path

from src.application.services.mcp_adapter import McpError
from src.application.services.web_fetch_tasks import finish_owned, spawn_owned

logger = logging.getLogger(__name__)
MAX_FRAME = 16384


class PinnedPythonStdio:
    """Run only an approved local standard-library Python source snapshot without host roots, ambient credentials or network."""

    def __init__(self, script, expected_sha256):
        """Verify exact bounded source bytes before adopting a private execution snapshot; do not start a server yet."""
        try:
            descriptor = os.open(
                script, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC
            )
            with os.fdopen(descriptor, "rb") as stream:
                info = os.fstat(stream.fileno())
                raw = stream.read(65537)
        except (OSError, TypeError, ValueError):
            raise McpError("invalid_configuration") from None
        if (
            not stat.S_ISREG(info.st_mode)
            or not 1 <= len(raw) <= 65536
            or hashlib.sha256(raw).hexdigest() != expected_sha256
        ):
            raise McpError("invalid_configuration")
        self.directory = tempfile.TemporaryDirectory(prefix="assistant-mcp-")
        self.snapshot = Path(self.directory.name) / "server.py"
        self.snapshot.write_bytes(raw)
        self.snapshot.chmod(0o400)
        self.source_sha256 = expected_sha256
        self.process, self.stderr_task = None, None
        self.stderr_bytes = 0
        self.stderr_overflow = False
        self.closed = False
        self.admission, self.cleanup = asyncio.Lock(), asyncio.Lock()
        self.reaped = False
        logger.info("mcp_source_snapshot_verified sha256=%s", expected_sha256)

    def command(self):
        """Expose only stdlib and the immutable approved script inside fresh offline namespaces and fixed resource limits."""
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
            "--dir",
            "/app",
            "--ro-bind",
            str(self.snapshot),
            "/app/server.py",
            "--proc",
            "/proc",
            "--dev",
            "/dev",
            "--size",
            "16777216",
            "--tmpfs",
            "/tmp",
            "--setenv",
            "PATH",
            "/usr/bin:/bin",
            "--setenv",
            "LANG",
            "C.UTF-8",
            "--setenv",
            "PYTHONDONTWRITEBYTECODE",
            "1",
            "--chdir",
            "/app",
            "--remount-ro",
            "/",
            "--",
            "/usr/bin/prlimit",
            "--as=268435456",
            "--cpu=10:11",
            "--nofile=32",
            "--fsize=1048576",
            "--core=0",
            "--",
            "/usr/bin/python3",
            "/app/server.py",
        ]

    async def drain_stderr(self):
        """Drain bounded peer diagnostics without retaining or logging their potentially sensitive text."""
        while True:
            block = await self.process.stderr.read(4096)
            if not block:
                return
            self.stderr_bytes += len(block)
            if self.stderr_bytes > 32768:
                self.stderr_overflow = True
                if self.process.returncode is None:
                    self.process.kill()
                return

    async def start(self):
        """Start the approved isolated child once and own its stderr drainer for the whole connection lifetime."""
        if self.closed:
            raise McpError("closed")
        if self.process is None:
            launch = spawn_owned(
                asyncio.create_subprocess_exec(
                    *self.command(),
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    limit=MAX_FRAME + 1,
                    env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"},
                    start_new_session=True,
                )
            )
            try:
                self.process = await asyncio.shield(launch)
            except asyncio.CancelledError:
                self.process = await finish_owned(launch)
                self.stderr_task = spawn_owned(self.drain_stderr())
                raise
            self.stderr_task = spawn_owned(self.drain_stderr())
            logger.info("mcp_stdio_started pid=%d", self.process.pid)

    async def exchange(self, raw):
        """Serialize one bounded newline-delimited exchange and close the real process on failure or cancellation."""
        if self.closed:
            raise McpError("closed")
        if type(raw) is not bytes or not 1 <= len(raw) <= MAX_FRAME or b"\n" in raw:
            raise McpError("limit")
        if self.admission.locked():
            raise McpError("busy")
        async with self.admission:
            try:
                await self.start()
                async with asyncio.timeout(5):
                    self.process.stdin.write(raw + b"\n")
                    await self.process.stdin.drain()
                    line = await self.process.stdout.readline()
                if (
                    not line
                    or len(line) > MAX_FRAME
                    or not line.endswith(b"\n")
                    or self.stderr_overflow
                ):
                    raise McpError("invalid_response")
                return line[:-1]
            except BaseException:
                await self.close()
                raise

    async def close(self):
        """Pin teardown until actual child/drainer retirement even if the host cancels shutdown repeatedly."""
        task = spawn_owned(self.finish_close())
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            try:
                await finish_owned(task)
            except BaseException:
                logger.info("mcp_stdio_cancelled_close_joined")
            raise

    async def finish_close(self):
        """Close stdin, kill only the owned sandbox if necessary and join child/drainer before removing its source snapshot."""
        async with self.cleanup:
            self.closed = True
            if self.process is not None and not self.reaped:
                self.process.stdin.close()
                try:
                    await asyncio.wait_for(self.process.wait(), 0.5)
                except TimeoutError:
                    self.process.kill()
                    await asyncio.wait_for(self.process.wait(), 2)
                self.reaped = True
            if self.stderr_task is not None:
                try:
                    await finish_owned(self.stderr_task)
                except BaseException:
                    logger.info("mcp_stdio_stderr_retired")
            self.directory.cleanup()
            logger.info(
                "mcp_stdio_closed process_reaped=%s stderr_bytes=%d",
                self.reaped,
                self.stderr_bytes,
            )
