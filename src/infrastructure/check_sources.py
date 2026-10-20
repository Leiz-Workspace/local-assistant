"""Capture exact owner-authorized selected Python bytes and retain native source-version fences for freshly approved isolated checks."""

import hashlib
import json
import logging
import os
import stat
import threading
from contextlib import nullcontext
from dataclasses import dataclass
from time import monotonic
from types import MappingProxyType
from uuid import UUID

from src.application.services.check_policy import (
    CAPTURE_SECONDS,
    MAX_RECORD_BYTES,
    MAX_SOURCE_BYTES,
    MAX_SOURCE_TOTAL,
    selection_input,
    source_bytes,
)
from src.application.services.workspace_policy import WorkspaceAccessError
from src.infrastructure.check_runtime_io import check_capture
from src.infrastructure.workspace_reader import fingerprint

logger = logging.getLogger(__name__)


def directory_context(descriptor):
    """Bind native directory identity/mode/ownership without invalidating selected sources for unrelated entry changes."""
    info = os.fstat(descriptor)
    if not stat.S_ISDIR(info.st_mode):
        raise WorkspaceAccessError("checks_source_parent_invalid", 422)
    return info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid


@dataclass(frozen=True, slots=True)
class SourceReceipt:
    """Freeze one selected path's exact raw digest/size and native source/parent identities without exposing mutable approval context."""

    path: str
    sha256: str
    size: int
    native: tuple[int, ...]
    parent: tuple[int, ...]

    def record(self):
        """Return a fresh serializable source receipt without sharing mutable native-version fields."""
        return dict(
            path=self.path,
            sha256=self.sha256,
            size=self.size,
            native=list(self.native),
            parent=list(self.parent),
        )


class NativeCheckSources:
    """Own one explicit workspace root pin and immutable selected bytes until proposal expiry or joined execution completes."""

    def __init__(self, catalog, owner, workspace, profile, files, stop=None):
        """Authorize exact scope and capture bounded text bytes through kernel capabilities without executing/importing project code."""
        self.context, self.handle, self.closed = None, None, False
        if type(owner) is not UUID or type(workspace) is not UUID:
            raise WorkspaceAccessError("checks_sources_not_found", 404)
        self.owner, self.workspace = owner, workspace
        self.profile, self.selection = selection_input(profile, files)
        stop = stop if stop is not None else threading.Event()
        deadline = monotonic() + CAPTURE_SECONDS
        try:
            self.context = catalog.open(owner, workspace)
            self.handle = self.context.__enter__()
            self.root = directory_context(self.handle.fd)
            originals, receipts, total = {}, [], 0
            for path, expected in self.selection:
                raw, receipt = self.read(path, stop, deadline)
                if receipt.sha256 != expected:
                    raise WorkspaceAccessError("checks_source_changed", 409)
                total += len(raw)
                if total > MAX_SOURCE_TOTAL:
                    raise WorkspaceAccessError("checks_source_total_limit", 413)
                originals[path] = raw
                receipts.append(receipt)
            self.originals = MappingProxyType(originals)
            self.receipts = tuple(receipts)
            self.total_bytes = total
            raw = self.encode(self.core_metadata())
            self.version = hashlib.sha256(raw).hexdigest()
            self.validate(stop, deadline)
            logger.info(
                "checks_sources_captured workspace_id=%s files=%d bytes=%d",
                workspace,
                len(receipts),
                total,
            )
        except BaseException:
            self.close()
            raise

    def check(self, stop, deadline):
        """Reject released/cancelled/timed-out native source work before using a retained descriptor."""
        if self.closed:
            raise WorkspaceAccessError("checks_sources_closed", 409)
        check_capture(stop, deadline)

    def read(self, path, stop, deadline):
        """Read one kernel-admitted stable file and fence its current source/parent/root identities before returning exact bytes."""
        self.check(stop, deadline)
        if type(path) is not str or path not in {
            selected for selected, _ in self.selection
        }:
            raise WorkspaceAccessError("checks_source_path_invalid", 422)
        parent_path = path.rpartition("/")[0]
        parent_context = (
            self.handle.entry(parent_path)
            if parent_path
            else nullcontext(self.handle.fd)
        )
        with parent_context as parent:
            parent_version = directory_context(parent)
            with self.handle.entry(path) as descriptor:
                before = os.fstat(descriptor)
                if (
                    not stat.S_ISREG(before.st_mode)
                    or before.st_size > MAX_SOURCE_BYTES
                ):
                    raise WorkspaceAccessError("checks_source_limit", 413)
                chunks, length = [], 0
                while True:
                    self.check(stop, deadline)
                    chunk = os.read(
                        descriptor, min(4096, MAX_SOURCE_BYTES + 1 - length)
                    )
                    if not chunk:
                        break
                    length += len(chunk)
                    if length > MAX_SOURCE_BYTES:
                        raise WorkspaceAccessError("checks_source_limit", 413)
                    chunks.append(chunk)
                after = os.fstat(descriptor)
                if (
                    fingerprint(before) != fingerprint(after)
                    or length != before.st_size
                ):
                    raise WorkspaceAccessError("checks_source_changed", 409)
                raw = source_bytes(b"".join(chunks))
            self.check(stop, deadline)
            fresh_context = (
                self.handle.entry(parent_path)
                if parent_path
                else nullcontext(self.handle.fd)
            )
            with fresh_context as current:
                if directory_context(current) != parent_version:
                    raise WorkspaceAccessError("checks_source_changed", 409)
            with self.handle.entry(path) as current:
                if fingerprint(os.fstat(current)) != fingerprint(after):
                    raise WorkspaceAccessError("checks_source_changed", 409)
        return raw, SourceReceipt(
            path,
            hashlib.sha256(raw).hexdigest(),
            len(raw),
            fingerprint(after),
            parent_version,
        )

    def core_metadata(self):
        """Describe exact historical selected-source context without adding a self-referential version field or raw source payload."""
        return dict(
            description="Exact selected readonly Python source context for one isolated check proposal.",
            version=1,
            owner_id=str(self.owner),
            workspace_id=str(self.workspace),
            profile=self.profile.name,
            root=list(self.root),
            files=[receipt.record() for receipt in self.receipts],
            total_bytes=self.total_bytes,
        )

    def encode(self, value):
        """Encode complete bounded deterministic source metadata without truncating review authority or permitting nonfinite values."""
        raw = json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        if len(raw) > MAX_RECORD_BYTES:
            raise WorkspaceAccessError("checks_source_metadata_limit", 413)
        return raw

    def metadata(self):
        """Return copied historical source receipts/version without claiming that the current workspace still matches them."""
        value = self.core_metadata()
        value["source_version"] = self.version
        self.encode(value)
        return value

    def validate(self, stop=None, deadline=None):
        """Re-read every selected path and verify source bytes/native identities before launch without refreshing an approved version."""
        stop = stop if stop is not None else threading.Event()
        deadline = deadline if deadline is not None else monotonic() + CAPTURE_SECONDS
        self.check(stop, deadline)
        self.handle.validate_root()
        if directory_context(self.handle.fd) != self.root:
            raise WorkspaceAccessError("checks_source_changed", 409)
        for expected in self.receipts:
            raw, actual = self.read(expected.path, stop, deadline)
            if actual != expected or raw != self.originals[expected.path]:
                raise WorkspaceAccessError("checks_source_changed", 409)
        for expected in self.receipts:
            self.check(stop, deadline)
            parent = expected.path.rpartition("/")[0]
            context = (
                self.handle.entry(parent) if parent else nullcontext(self.handle.fd)
            )
            with context as descriptor:
                if directory_context(descriptor) != expected.parent:
                    raise WorkspaceAccessError("checks_source_changed", 409)
            with self.handle.entry(expected.path) as descriptor:
                if fingerprint(os.fstat(descriptor)) != expected.native:
                    raise WorkspaceAccessError("checks_source_changed", 409)
        self.handle.validate_root()
        if directory_context(self.handle.fd) != self.root:
            raise WorkspaceAccessError("checks_source_changed", 409)
        logger.info(
            "checks_sources_version_verified workspace_id=%s files=%d",
            self.workspace,
            len(self.receipts),
        )

    def close(self):
        """Release the original source root once after joined work while retaining immutable historical metadata and bytes."""
        if not self.closed:
            self.closed = True
            context, self.context = self.context, None
            if context is not None:
                try:
                    context.__exit__(None, None, None)
                except OSError:
                    logger.warning("checks_source_pin_close_uncertain")
                    raise
                logger.info("checks_source_pin_closed")
