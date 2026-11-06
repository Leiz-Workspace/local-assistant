"""Capture exact scoped source proposals and replace one approved existing file through native owned directory descriptors."""

import fcntl
import hashlib
import hmac
import json
import logging
import os
import stat
import threading
from contextlib import contextmanager
from copy import deepcopy
from time import monotonic
from uuid import UUID, uuid4

from src.application.services.approvals import MAX_ARTIFACT_BYTES, scope_for
from src.application.services.patch_policy import (
    FILE_SECONDS,
    MAX_SOURCE_BYTES,
    PROPOSAL_SECONDS,
    patch_input,
    unified_patch,
)
from src.application.services.workspace_policy import WorkspaceAccessError
from src.infrastructure.workspace_reader import fingerprint

logger = logging.getLogger(__name__)


class NativePatch:
    """Own one exact source snapshot/root pin and record the authoritative single-file commit outcome."""

    def __init__(
        self,
        catalog,
        owner,
        workspace,
        path,
        expected_sha256,
        replacement,
        stop=None,
        *,
        clock=monotonic,
    ):
        """Authorize native reads only and build an immutable complete review without writing source or temporary files."""
        self.replacement = patch_input(path, expected_sha256, replacement)
        self.owner, self.workspace, self.path = owner, workspace, path
        self.identifier = uuid4()
        self.clock = clock
        self.lock = threading.RLock()
        self.closed = False
        self.context = None
        self.handle = None
        self.state = "proposed"
        self.receipt = None
        self.error_code = None
        self.uncertainties = []
        self.rename_ack_reconciled = False
        self.approval_id = None
        self.scope_digest = None
        self.expires = None
        if os.getuid() == 0 or os.getuid() != os.geteuid():
            raise WorkspaceAccessError("patch_writer_identity_unsupported", 503)
        try:
            self.context = catalog.open(owner, workspace)
            self.handle = self.context.__enter__()
            self.original, self.metadata = self.inspect(
                stop, self.clock() + FILE_SECONDS
            )
            self.base_sha256 = hashlib.sha256(self.original).hexdigest()
            if not hmac.compare_digest(self.base_sha256, expected_sha256):
                raise WorkspaceAccessError("patch_source_changed", 409)
            if self.original == self.replacement:
                raise WorkspaceAccessError("patch_no_changes", 422)
            self.new_sha256 = hashlib.sha256(self.replacement).hexdigest()
            self.diff = unified_patch(path, self.original.decode("utf-8"), replacement)
            artifact = dict(
                description="Replace one existing source file after exact scoped approval.",
                proposal_id=str(self.identifier),
                path=path,
                source_version=self.metadata["version"],
                base_sha256=self.base_sha256,
                new_sha256=self.new_sha256,
                mode=format(self.metadata["mode"], "04o"),
                gid=self.metadata["gid"],
                diff=self.diff,
                replacement=replacement,
            )
            self.artifact = json.dumps(
                artifact, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ).encode("utf-8")
            if len(self.artifact) > MAX_ARTIFACT_BYTES:
                raise WorkspaceAccessError("patch_review_limit", 413)
            self.expires = self.clock() + PROPOSAL_SECONDS
            logger.info("patch_proposal_captured proposal_id=%s", self.identifier)
        except BaseException:
            self.close()
            raise

    def check(self, stop, deadline):
        """Refuse closed/cancelled/expired work before another bounded native filesystem stage."""
        if self.closed:
            raise WorkspaceAccessError("patch_closed", 409)
        if stop is not None and stop.is_set():
            raise WorkspaceAccessError("patch_cancelled", 503)
        now = self.clock()
        if now >= deadline:
            raise WorkspaceAccessError("patch_deadline", 504)
        if self.expires is not None and now >= self.expires:
            raise WorkspaceAccessError("patch_expired", 409)

    @contextmanager
    def parent(self):
        """Admit only the current relative parent directory through the unchanged D33 kernel scope guard."""
        directory = self.path.rpartition("/")[0]
        if directory:
            with self.handle.entry(directory) as descriptor:
                yield descriptor
        else:
            self.handle.validate_root()
            yield self.handle.fd

    def eligible(self, descriptor, *, directory=False):
        """Reject unsupported owner/write/set-ID/group/ACL metadata rather than dropping it during replacement."""
        info = os.fstat(descriptor)
        kind = stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)
        if (
            not kind
            or info.st_uid != os.getuid()
            or info.st_mode & 0o7022
            or not info.st_mode & stat.S_IWUSR
        ):
            raise WorkspaceAccessError("patch_metadata_unsupported", 422)
        if not directory and (
            info.st_nlink != 1 or info.st_gid not in {*os.getgroups(), os.getgid()}
        ):
            raise WorkspaceAccessError("patch_metadata_unsupported", 422)
        if os.listxattr(descriptor):
            raise WorkspaceAccessError("patch_metadata_unsupported", 422)
        return info

    def inspect(self, stop, deadline):
        """Read exact source bytes and derive root/parent/native stat/hash version under strict size and identity fences."""
        self.check(stop, deadline)
        with self.parent() as parent:
            parent_info = self.eligible(parent, directory=True)
            parent_identity = (
                parent_info.st_dev,
                parent_info.st_ino,
                parent_info.st_mode,
                parent_info.st_uid,
                parent_info.st_gid,
            )
            with self.handle.entry(self.path) as descriptor:
                before = self.eligible(descriptor)
                if before.st_size > MAX_SOURCE_BYTES:
                    raise WorkspaceAccessError("patch_source_limit", 413)
                chunks, length = [], 0
                while True:
                    self.check(stop, deadline)
                    chunk = os.read(
                        descriptor, min(4096, MAX_SOURCE_BYTES + 1 - length)
                    )
                    if not chunk:
                        break
                    chunks.append(chunk)
                    length += len(chunk)
                    if length > MAX_SOURCE_BYTES:
                        raise WorkspaceAccessError("patch_source_limit", 413)
                after = self.eligible(descriptor)
                raw = b"".join(chunks)
                if (
                    fingerprint(before) != fingerprint(after)
                    or length != before.st_size
                ):
                    raise WorkspaceAccessError("patch_source_changed", 409)
            current_parent = self.eligible(parent, directory=True)
            if parent_identity != (
                current_parent.st_dev,
                current_parent.st_ino,
                current_parent.st_mode,
                current_parent.st_uid,
                current_parent.st_gid,
            ):
                raise WorkspaceAccessError("patch_parent_changed", 409)
        self.handle.validate_root()
        try:
            if b"\x00" in raw:
                raise UnicodeError()
            raw.decode("utf-8")
        except UnicodeError:
            raise WorkspaceAccessError("patch_text_required", 422) from None
        metadata = dict(
            root=(self.handle.identity.st_dev, self.handle.identity.st_ino),
            parent=parent_identity,
            source=fingerprint(after),
            source_sha256=hashlib.sha256(raw).hexdigest(),
            uid=after.st_uid,
            gid=after.st_gid,
            mode=stat.S_IMODE(after.st_mode),
        )
        metadata["version"] = hashlib.sha256(
            json.dumps(metadata, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        return raw, metadata

    def register_approval(self, store):
        """Create one trusted review request for the exact immutable proposal artifact without approving it."""
        self.check(None, self.clock() + FILE_SECONDS)
        if self.approval_id is not None:
            raise WorkspaceAccessError("patch_approval_already_registered", 409)
        self.approval_id = store.create(
            self.owner, self.workspace, "patch", self.artifact
        )
        self.scope_digest = scope_for(
            self.owner, self.workspace, "patch", self.artifact
        )[0].digest
        logger.info(
            "patch_approval_registered proposal_id=%s request_id=%s",
            self.identifier,
            self.approval_id,
        )
        return self.approval_id

    def require_approval(self, store, identifier):
        """Require an already-approved exact unexpired linked review before any temporary workspace write."""
        if type(identifier) is not UUID or identifier != self.approval_id:
            raise WorkspaceAccessError("patch_approval_changed", 409)
        review = store.review(self.owner, identifier)
        if (
            review["state"] != "approved"
            or review["scope_digest"] != self.scope_digest
            or review["artifact"].encode("utf-8") != self.artifact
        ):
            raise WorkspaceAccessError("patch_approval_required", 409)

    def verify_version(self, stop, deadline):
        """Reject any changed current source/root/parent metadata or raw bytes after the original proposal was captured."""
        raw, metadata = self.inspect(stop, deadline)
        if raw != self.original or metadata["version"] != self.metadata["version"]:
            raise WorkspaceAccessError("patch_source_changed", 409)

    def record_commit(self, state, *, applied):
        """Publish an authoritative immutable-by-copy action receipt without treating a committed rename as cancelled."""
        with self.lock:
            self.state = state
            if state != "applied" and state not in self.uncertainties:
                self.uncertainties.append(state)
            self.receipt = dict(
                proposal_id=str(self.identifier),
                approval_id=str(self.approval_id),
                state=state,
                applied=applied,
                path=self.path,
                base_sha256=self.base_sha256,
                new_sha256=self.new_sha256,
                uncertainties=list(self.uncertainties),
                rename_ack_reconciled=self.rename_ack_reconciled,
            )
        logger.info(
            "patch_commit_recorded proposal_id=%s state=%s", self.identifier, state
        )
        return deepcopy(self.receipt)

    def validate_prepared(self, parent, name, descriptor, identity):
        """Verify exact prepared bytes/metadata and the named temporary inode immediately before consuming approval."""
        before = self.eligible(descriptor)
        raw = os.pread(descriptor, MAX_SOURCE_BYTES + 1, 0)
        after = self.eligible(descriptor)
        named = os.stat(name, dir_fd=parent, follow_symlinks=False)
        if (
            (named.st_dev, named.st_ino) != identity
            or fingerprint(before) != fingerprint(after)
            or raw != self.replacement
            or after.st_gid != self.metadata["gid"]
            or stat.S_IMODE(after.st_mode) != self.metadata["mode"]
        ):
            raise WorkspaceAccessError("patch_prepared_changed", 409)
        logger.info("patch_prepared_validated proposal_id=%s", self.identifier)

    def cleanup_temporary(self, parent, name, identity, descriptor):
        """Close once and unlink only the acknowledged-owned temporary inode, preserving unrelated directory entries."""
        success = not (descriptor is not None and identity is None)
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError:
                success = False
        if name is not None and identity is not None:
            try:
                info = os.stat(name, dir_fd=parent, follow_symlinks=False)
                if (info.st_dev, info.st_ino) != identity:
                    success = False
                else:
                    os.unlink(name, dir_fd=parent)
            except FileNotFoundError:
                pass
            except OSError:
                success = False
        logger.info(
            "patch_temporary_cleanup proposal_id=%s completed=%s",
            self.identifier,
            success,
        )
        return success

    def rename_prepared(self, parent, name, identity):
        """Record atomic rename or reconcile its acknowledgement without falsely reporting an uncertain commit as unapplied."""
        leaf = self.path.rsplit("/", 1)[-1]
        try:
            os.replace(name, leaf, src_dir_fd=parent, dst_dir_fd=parent)
        except OSError as error:
            try:
                current = os.stat(leaf, dir_fd=parent, follow_symlinks=False)
                target = (current.st_dev, current.st_ino)
                if target == identity:
                    self.rename_ack_reconciled = True
                    logger.warning(
                        "patch_rename_ack_reconciled proposal_id=%s", self.identifier
                    )
                    return self.record_commit("applied", applied=True)
                temporary = os.stat(name, dir_fd=parent, follow_symlinks=False)
                still_owned = (temporary.st_dev, temporary.st_ino) == identity
            except OSError:
                return self.record_commit("outcome_unknown", applied=None)
            if target == tuple(self.metadata["source"][:2]) and still_owned:
                raise error
            return self.record_commit("outcome_unknown", applied=None)
        return self.record_commit("applied", applied=True)

    def apply(self, store, identifier, stop=None):
        """Replace one exact approved source through a prepared same-directory inode and retain authoritative commit status."""
        deadline = self.clock() + FILE_SECONDS
        self.check(stop, deadline)
        self.require_approval(store, identifier)
        with self.lock:
            if self.state != "proposed":
                raise WorkspaceAccessError("patch_state_conflict", 409)
            self.state = "applying"
        try:
            with self.parent() as parent:
                with self.handle.entry(self.path) as source:
                    try:
                        fcntl.flock(source, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    except BlockingIOError:
                        raise WorkspaceAccessError("patch_busy", 429) from None
                    held = os.fstat(source)
                    if (held.st_dev, held.st_ino) != tuple(self.metadata["source"][:2]):
                        raise WorkspaceAccessError("patch_source_changed", 409)
                    parent_info = self.eligible(parent, directory=True)
                    parent_identity = (
                        parent_info.st_dev,
                        parent_info.st_ino,
                        parent_info.st_mode,
                        parent_info.st_uid,
                        parent_info.st_gid,
                    )
                    if parent_identity != tuple(self.metadata["parent"]):
                        raise WorkspaceAccessError("patch_parent_changed", 409)
                    self.verify_version(stop, deadline)
                    descriptor, name, identity = None, None, None
                    try:
                        self.check(stop, deadline)
                        name = ".assistant-patch-" + uuid4().hex + ".tmp"
                        descriptor = os.open(
                            name,
                            os.O_RDWR
                            | os.O_CREAT
                            | os.O_EXCL
                            | os.O_NOFOLLOW
                            | os.O_CLOEXEC,
                            0o600,
                            dir_fd=parent,
                        )
                        temporary = os.fstat(descriptor)
                        identity = (temporary.st_dev, temporary.st_ino)
                        offset = 0
                        while offset < len(self.replacement):
                            self.check(stop, deadline)
                            written = os.write(descriptor, self.replacement[offset:])
                            if written <= 0:
                                raise OSError("patch_write_failed")
                            offset += written
                        os.fchown(descriptor, -1, self.metadata["gid"])
                        os.fchmod(descriptor, self.metadata["mode"])
                        prepared = self.eligible(descriptor)
                        if (
                            prepared.st_gid != self.metadata["gid"]
                            or stat.S_IMODE(prepared.st_mode) != self.metadata["mode"]
                        ):
                            raise WorkspaceAccessError("patch_metadata_changed", 409)
                        os.fsync(descriptor)
                        self.verify_version(stop, deadline)
                        self.validate_prepared(parent, name, descriptor, identity)
                        self.check(stop, deadline)
                        store.consume(
                            self.owner,
                            identifier,
                            self.workspace,
                            "patch",
                            self.artifact,
                        )
                        self.check(stop, deadline)
                        self.rename_prepared(parent, name, identity)
                        if self.receipt["applied"] is True:
                            try:
                                os.fsync(parent)
                            except OSError:
                                self.record_commit(
                                    "applied_durability_uncertain", applied=True
                                )
                    finally:
                        clean = self.cleanup_temporary(
                            parent, name, identity, descriptor
                        )
                        if not clean:
                            if self.receipt is not None:
                                self.record_commit(
                                    "applied_cleanup_uncertain"
                                    if self.receipt["applied"] is True
                                    else "outcome_unknown",
                                    applied=self.receipt["applied"],
                                )
                            else:
                                raise WorkspaceAccessError(
                                    "patch_cleanup_uncertain", 503
                                )
        except BaseException as error:
            if self.receipt is not None:
                return self.record_commit(
                    "applied_cleanup_uncertain"
                    if self.receipt["applied"] is True
                    else "outcome_unknown",
                    applied=self.receipt["applied"],
                )
            with self.lock:
                self.state = "failed"
                self.error_code = getattr(error, "code", "patch_io_failed")
            logger.warning(
                "patch_apply_failed proposal_id=%s code=%s",
                self.identifier,
                self.error_code,
            )
            raise
        return deepcopy(self.receipt)

    def public(self):
        """Return an owner-filtered caller's complete historical proposal/status without private root paths or handles."""
        with self.lock:
            return dict(
                proposal_id=str(self.identifier),
                approval_id=str(self.approval_id)
                if self.approval_id is not None
                else None,
                state=self.state,
                path=self.path,
                base_sha256=self.base_sha256,
                new_sha256=self.new_sha256,
                source_version=self.metadata["version"],
                original=self.original.decode("utf-8"),
                replacement=self.replacement.decode("utf-8"),
                diff=self.diff,
                scope_digest=self.scope_digest,
                remaining_seconds=max(0, self.expires - self.clock()),
                receipt=deepcopy(self.receipt),
                error_code=self.error_code,
            )

    def close(self):
        """Release the retained root pin once after joined native ownership without changing source or deleting artifacts."""
        if not self.closed:
            self.closed = True
            if self.context is not None and self.handle is not None:
                self.context.__exit__(None, None, None)
            logger.info("patch_proposal_pin_closed proposal_id=%s", self.identifier)
