"""Supervise fixed complete report exports in credential-free private namespaces with bounded pipes and joined async/thread/process cleanup."""

import asyncio
import hashlib
import logging
import os
import selectors
import subprocess
import threading
import time

from src.application.services.report_export_policy import (
    MAX_STDERR,
    MAX_STDOUT,
    ReportExportError,
    parse_native,
    parse_payload,
)
from src.application.services.web_fetch_tasks import finish_owned, spawn_owned
from src.infrastructure.file_verifier import sandbox_command
from src.infrastructure.sandbox_process import Sandbox

logger = logging.getLogger(__name__)
NATIVE_SECONDS = 20


def export_command():
    """Derive a new fixed readonly-root/nonroot command with only private bounded tmpfs and public Office/font configuration added."""
    command = sandbox_command(
        ["/venv/bin/python", "-m", "src.infrastructure.report_export_worker"]
    )
    index = command.index("--tmpfs")
    assert command[index + 1] == "/tmp"
    command[index:index] = ["--size", str(64 * 1024**2), "--perms", "1777"]
    index = command.index("--remount-ro")
    assert command[index + 1] == "/tmp"
    del command[index : index + 2]
    index = command.index("--remount-ro")
    assert command[index + 1] == "/"
    command[index:index] = [
        "--dir",
        "/etc",
        "--ro-bind",
        "/etc/fonts",
        "/etc/fonts",
        "--ro-bind",
        "/etc/libreoffice",
        "/etc/libreoffice",
        "--uid",
        "65534",
        "--gid",
        "65534",
        "--setenv",
        "SAL_USE_VCLPLUGIN",
        "svp",
        "--setenv",
        "XDG_CACHE_HOME",
        "/tmp/cache",
        "--setenv",
        "XDG_CONFIG_HOME",
        "/tmp/config",
        "--setenv",
        "TMPDIR",
        "/tmp",
    ]
    logger.info("report_export_private_namespace_command_prepared")
    return command


def supervise(payload, stop):
    """Own one fixed batch's process/session/pipes/selector until actual namespace retirement, retaining only bounded output and finite failures."""
    parse_payload(payload)
    deadline = time.monotonic() + NATIVE_SECONDS
    sandbox = None
    selector = selectors.DefaultSelector()
    stdout, stderr = bytearray(), bytearray()
    status = "export_native_failed"
    try:
        if stop.is_set():
            raise ReportExportError("export_timeout")
        sandbox = Sandbox(
            export_command(),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env={},
            close_fds=True,
            start_new_session=True,
        )
        process = sandbox.process
        for stream, event, label in [
            (process.stdin, selectors.EVENT_WRITE, "stdin"),
            (process.stdout, selectors.EVENT_READ, "stdout"),
            (process.stderr, selectors.EVENT_READ, "stderr"),
        ]:
            os.set_blocking(stream.fileno(), False)
            selector.register(stream, event, label)
        offset = 0
        while selector.get_map():
            if stop.is_set() or time.monotonic() >= deadline:
                raise ReportExportError("export_timeout")
            for key, _ in selector.select(
                min(0.05, max(0, deadline - time.monotonic()))
            ):
                if key.data == "stdin":
                    try:
                        offset += os.write(key.fd, payload[offset : offset + 4096])
                        finished = offset == len(payload)
                    except BrokenPipeError:
                        finished = True
                    if finished:
                        selector.unregister(key.fileobj)
                        key.fileobj.close()
                else:
                    data = os.read(key.fd, 65536)
                    if not data:
                        selector.unregister(key.fileobj)
                        key.fileobj.close()
                        continue
                    output = stdout if key.data == "stdout" else stderr
                    limit = MAX_STDOUT if key.data == "stdout" else MAX_STDERR
                    if len(output) + len(data) > limit:
                        raise ReportExportError("export_result_limit")
                    output.extend(data)
        try:
            code = process.wait(timeout=max(0.001, deadline - time.monotonic()))
        except subprocess.TimeoutExpired:
            raise ReportExportError("export_timeout") from None
        if code != 0:
            raise ReportExportError("export_native_failed")
        if stop.is_set() or time.monotonic() >= deadline:
            raise ReportExportError("export_timeout")
        status = "completed"
    except ReportExportError as error:
        status = error.code
        raise
    except (OSError, ValueError, RuntimeError):
        raise ReportExportError("export_unavailable") from None
    finally:
        retired = True
        if sandbox is not None:
            retired = sandbox.retire("exit" if status == "completed" else "abort")
            process = sandbox.process
            for stream in [process.stdin, process.stdout, process.stderr]:
                if not stream.closed:
                    stream.close()
        selector.close()
        if not retired:
            status = "export_cleanup_uncertain"
        logger.info(
            "report_export_native_namespace_joined status=%s stderr_bytes=%d stderr_sha256=%s",
            status,
            len(stderr),
            hashlib.sha256(stderr).hexdigest(),
        )
        if not retired:
            # Fail closed: the exporter closes its admission on this code instead of starting another namespace.
            raise ReportExportError("export_cleanup_uncertain") from None
    result = parse_native(bytes(stdout), payload, bytes(stderr))
    if stop.is_set() or time.monotonic() >= deadline:
        raise ReportExportError("export_timeout")
    return result


class NativeReportExporter:
    """Hold nonqueued native admission through synchronous supervisor/thread cleanup under repeated async cancellation."""

    def __init__(self):
        """Initialize inert native ownership counters without processes, models, file writes, credentials or Office profiles."""
        self.admission = asyncio.Lock()
        self.operations = set()
        self.closing = False
        logger.info("native_report_exporter_initialized")

    async def render(self, payload):
        """Join one owned supervisor thread instead of cancelling its future while a late native process can still exist."""
        parse_payload(payload)
        if self.closing or self.admission.locked():
            raise ReportExportError("export_closed" if self.closing else "export_busy")
        await self.admission.acquire()
        caller, task, stop = asyncio.current_task(), None, threading.Event()
        try:
            self.operations.add(caller)
            task = spawn_owned(asyncio.to_thread(supervise, payload, stop))
            try:
                return await asyncio.shield(task)
            except asyncio.CancelledError:
                stop.set()
                try:
                    await finish_owned(task)
                except BaseException as error:
                    if (
                        not isinstance(error, ReportExportError)
                        or error.code == "export_cleanup_uncertain"
                    ):
                        self.closing = True
                    logger.info("native_report_cancelled_thread_joined")
                raise
        except asyncio.CancelledError:
            raise
        except ReportExportError as error:
            if error.code == "export_cleanup_uncertain":
                self.closing = True
            raise
        except Exception:
            self.closing = True
            raise ReportExportError("export_cleanup_uncertain") from None
        finally:
            stop.set()
            self.operations.discard(caller)
            self.admission.release()
            logger.info("native_report_export_operation_closed")
