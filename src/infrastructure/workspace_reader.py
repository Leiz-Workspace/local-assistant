"""Build bounded owner-authorized workspace snapshots with exact source-line provenance and final byte fences."""

import hashlib
import logging
import os
import re
import stat
import threading
import time
from contextlib import nullcontext

from src.application.services.workspace_policy import WorkspaceAccessError, clean_parts
from src.application.services.workspace_requests import validate_workspace_request

logger = logging.getLogger(__name__)
MAX_ENTRIES = 1000
MAX_FILES = 256
MAX_DEPTH = 16
MAX_FILE_BYTES = 256 * 1024
MAX_TOTAL_BYTES = 4 * 1024 * 1024
MAX_LINE_BYTES = 8192
MAX_RESULTS = 100
MAX_SECONDS = 5
DEFINITION = re.compile(
    r"^[ \t]*(?:async[ \t]+)?(def|class)[ \t]+([A-Za-z_][A-Za-z_0-9]*)"
)


def fingerprint(info):
    """Bind a source snapshot to native identity, type, link count, size and nanosecond change times."""
    return (
        info.st_dev,
        info.st_ino,
        info.st_mode,
        info.st_nlink,
        info.st_size,
        info.st_mtime_ns,
        info.st_ctime_ns,
    )


class WorkspaceSnapshot:
    """Retain one authorized root and bounded per-source receipts through response delivery."""

    def __init__(self, catalog, owner, identifier, stop=None):
        """Authorize before root access and establish cancellation/deadline/counter ownership."""
        self.stop = stop or threading.Event()
        self.deadline = time.monotonic() + MAX_SECONDS
        self.context = catalog.open(owner, identifier)
        self.handle = self.context.__enter__()
        self.receipts = {}
        self.bytes = 0
        self.entries = 0
        self.files = 0
        self.omitted = dict(hidden=0, unsafe=0, non_text=0, non_python=0)
        self.payload = None
        self.discovery = None
        self.closed = False

    def check(self):
        """Refuse cancellation or elapsed cooperative wall budget before further bounded I/O."""
        if self.stop.is_set():
            raise WorkspaceAccessError("workspace_cancelled", 503)
        if time.monotonic() > self.deadline:
            raise WorkspaceAccessError("workspace_deadline", 504)

    def close(self):
        """Release the retained root exactly once after joined work or response delivery."""
        if not self.closed:
            self.context.__exit__(None, None, None)
            self.closed = True
            logger.info("workspace_snapshot_closed")

    def read_source(self, path, *, receipt=True):
        """Read bounded exact bytes from a single admitted regular file without accepting mutation during I/O."""
        self.check()
        with self.handle.entry(path) as descriptor:
            before = os.fstat(descriptor)
            if not stat.S_ISREG(before.st_mode):
                raise WorkspaceAccessError("workspace_file_required", 422)
            if before.st_size > MAX_FILE_BYTES:
                raise WorkspaceAccessError("workspace_file_limit", 413)
            if receipt and self.bytes + before.st_size > MAX_TOTAL_BYTES:
                raise WorkspaceAccessError("workspace_total_limit", 413)
            chunks, length = [], 0
            while True:
                self.check()
                chunk = os.read(descriptor, min(65536, MAX_FILE_BYTES + 1 - length))
                if not chunk:
                    break
                chunks.append(chunk)
                length += len(chunk)
                if length > MAX_FILE_BYTES:
                    raise WorkspaceAccessError("workspace_file_limit", 413)
            after = os.fstat(descriptor)
            if fingerprint(before) != fingerprint(after) or length != before.st_size:
                raise WorkspaceAccessError("workspace_source_changed", 409)
            raw = b"".join(chunks)
        if receipt:
            self.bytes += len(raw)
            if self.bytes > MAX_TOTAL_BYTES:
                raise WorkspaceAccessError("workspace_total_limit", 413)
            self.receipts[path] = dict(
                fingerprint=fingerprint(after), sha256=hashlib.sha256(raw).hexdigest()
            )
        return raw, after

    def source_lines(self, path):
        """Decode exact UTF-8 and expose LF-based lines with only native CRLF terminators excluded."""
        raw, _ = self.read_source(path)
        try:
            if b"\x00" in raw:
                raise UnicodeError()
            text = raw.decode("utf-8")
        except UnicodeError:
            raise WorkspaceAccessError("workspace_text_required", 422) from None
        parts = text.split("\n")
        lines = [
            line.removesuffix("\r") if index < len(parts) - 1 else line
            for index, line in enumerate(parts)
        ]
        if lines and lines[-1] == "":
            lines.pop()
        if any(len(line.encode()) > MAX_LINE_BYTES for line in lines):
            raise WorkspaceAccessError("workspace_line_limit", 413)
        return lines, hashlib.sha256(raw).hexdigest()

    def walk(self, directory=None):
        """Yield only admitted regular files while bounding every listed name, directory and unsafe omission."""
        if directory is not None:
            clean_parts(directory)
        pending = [directory]
        while pending:
            self.check()
            path = pending.pop()
            if path is not None and len(clean_parts(path)) > MAX_DEPTH:
                raise WorkspaceAccessError("workspace_depth_limit", 413)
            context = (
                self.handle.entry(path)
                if path is not None
                else nullcontext(self.handle.fd)
            )
            with context as descriptor:
                if not stat.S_ISDIR(os.fstat(descriptor).st_mode):
                    raise WorkspaceAccessError("workspace_directory_required", 422)
                names = []
                with os.scandir(descriptor) as iterator:
                    for entry in iterator:
                        self.check()
                        self.entries += 1
                        if self.entries > MAX_ENTRIES:
                            raise WorkspaceAccessError("workspace_entry_limit", 413)
                        if entry.name.startswith("."):
                            self.omitted["hidden"] += 1
                            continue
                        candidate = (
                            entry.name if path is None else path + "/" + entry.name
                        )
                        try:
                            clean_parts(candidate)
                        except WorkspaceAccessError:
                            self.omitted["unsafe"] += 1
                            continue
                        names.append(candidate)
                for candidate in sorted(names):
                    self.check()
                    try:
                        with self.handle.entry(candidate) as child:
                            info = os.fstat(child)
                    except WorkspaceAccessError as error:
                        if error.code in {
                            "workspace_entry_unavailable",
                            "workspace_entry_unsafe",
                        }:
                            self.omitted["unsafe"] += 1
                            continue
                        raise
                    if stat.S_ISDIR(info.st_mode):
                        pending.append(candidate)
                    else:
                        self.files += 1
                        if self.files > MAX_FILES:
                            raise WorkspaceAccessError(
                                "workspace_file_count_limit", 413
                            )
                        yield candidate, info

    def validate(self):
        """Re-open each returned source beneath the retained root and reject changed identity or bytes before headers."""
        self.check()
        self.handle.validate_root()
        if self.discovery is not None and self.handle.discover() != self.discovery:
            raise WorkspaceAccessError("workspace_source_changed", 409)
        for path, expected in self.receipts.items():
            self.check()
            if expected["sha256"] is not None:
                raw, info = self.read_source(path, receipt=False)
                digest = hashlib.sha256(raw).hexdigest()
            else:
                with self.handle.entry(path) as descriptor:
                    info = os.fstat(descriptor)
                digest = None
            if (
                fingerprint(info) != expected["fingerprint"]
                or digest != expected["sha256"]
            ):
                raise WorkspaceAccessError("workspace_source_changed", 409)
        self.handle.validate_root()
        self.check()
        logger.info("workspace_snapshot_validated sources=%d", len(self.receipts))


def build_snapshot(catalog, owner, identifier, operation, parameters, stop=None):
    """Build one bounded inventory/read/search/hint result and retain only authorized provenance for delivery."""
    parameters = validate_workspace_request(operation, parameters)
    snapshot = WorkspaceSnapshot(catalog, owner, identifier, stop)
    try:
        results = []
        if operation == "discover":
            payload = snapshot.handle.discover()
            snapshot.discovery = dict(payload)
        elif operation == "read":
            lines, digest = snapshot.source_lines(parameters["path"])
            start, end = parameters["start_line"], parameters["end_line"]
            if start > len(lines):
                raise WorkspaceAccessError("workspace_line_range", 422)
            for number in range(start, min(end, len(lines)) + 1):
                results.append(
                    dict(
                        path=parameters["path"],
                        source_sha256=digest,
                        line_number=number,
                        line_text=lines[number - 1],
                        content_trust="untrusted",
                    )
                )
            payload = dict(lines=results)
        else:
            for path, info in snapshot.walk(parameters.get("directory")):
                if operation == "inventory":
                    snapshot.receipts[path] = dict(
                        fingerprint=fingerprint(info), sha256=None
                    )
                    results.append(
                        dict(path=path, size_bytes=info.st_size, kind="file")
                    )
                    continue
                if operation == "symbols" and not path.endswith(".py"):
                    snapshot.omitted["non_python"] += 1
                    continue
                try:
                    lines, digest = snapshot.source_lines(path)
                except WorkspaceAccessError as error:
                    if error.code == "workspace_text_required":
                        snapshot.omitted["non_text"] += 1
                        continue
                    raise
                for number, text in enumerate(lines, 1):
                    snapshot.check()
                    base = dict(
                        path=path,
                        source_sha256=digest,
                        line_number=number,
                        line_text=text,
                        content_trust="untrusted",
                    )
                    if operation == "symbols":
                        match = DEFINITION.match(text)
                        if match:
                            results.append(
                                dict(base, kind="lexical_" + match[1], name=match[2])
                            )
                    elif operation == "search":
                        query = parameters["query"]
                        offset = 0
                        while True:
                            position = text.find(query, offset)
                            if position < 0:
                                break
                            results.append(
                                dict(
                                    base,
                                    column_start=position,
                                    column_end=position + len(query),
                                    column_unit="unicode_code_points",
                                )
                            )
                            offset = position + len(query)
                            if len(results) > MAX_RESULTS:
                                raise WorkspaceAccessError(
                                    "workspace_result_limit", 413
                                )
                    else:
                        raise WorkspaceAccessError("workspace_operation_invalid", 422)
                    if len(results) > MAX_RESULTS:
                        raise WorkspaceAccessError("workspace_result_limit", 413)
            results.sort(
                key=lambda row: (
                    row["path"],
                    row.get("line_number", 0),
                    row.get("column_start", 0),
                )
            )
            payload = {
                "inventory": dict(files=results),
                "search": dict(matches=results),
                "symbols": dict(hints=results),
            }[operation]
        snapshot.check()
        snapshot.payload = dict(
            payload,
            workspace_id=str(identifier),
            content_trust="untrusted",
            omitted=snapshot.omitted,
        )
        logger.info(
            "workspace_snapshot_prepared operation=%s files=%d results=%d",
            operation,
            snapshot.files,
            len(results),
        )
        return snapshot
    except BaseException:
        snapshot.close()
        raise
