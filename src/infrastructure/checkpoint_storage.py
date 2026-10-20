"""Guard explicit private checkpoint storage with native identities, exclusive ownership, bounded files and durable journal publication."""

import fcntl
import hashlib
import json
import logging
import os
import stat
import threading
from contextlib import contextmanager
from types import SimpleNamespace
from uuid import uuid4

from src.application.services.workspace_policy import WorkspaceAccessError
from src.infrastructure.readonly_workspace import ROOT_FLAGS, open_beneath, open_root
from src.infrastructure.workspace_reader import fingerprint

logger = logging.getLogger(__name__)
RESERVATION_BYTES = 262144
MAX_RECORD_BYTES = 32768


def canonical(value):
    """Encode bounded deterministic private metadata without nonfinite values or implicit text conversion."""
    raw = json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    if len(raw) > MAX_RECORD_BYTES:
        raise WorkspaceAccessError("checkpoint_record_limit", 413)
    return raw


def decode_record(raw):
    """Reject duplicate/nonfinite/malformed private JSON instead of accepting ambiguous journal authority."""

    def pairs(items):
        """Require one unambiguous value for every private metadata object key."""
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError()
            result[key] = value
        return result

    def constant(value):
        """Reject nonfinite JSON tokens without preserving private malformed source diagnostics."""
        raise ValueError()

    try:
        if len(raw) > MAX_RECORD_BYTES:
            raise ValueError()
        value = json.loads(raw, object_pairs_hook=pairs, parse_constant=constant)
        if type(value) is not dict:
            raise ValueError()
    except (ValueError, UnicodeError, RecursionError, TypeError):
        raise WorkspaceAccessError("checkpoint_record_invalid", 503) from None
    return value


def ancestor_identities(descriptor):
    """Compare native directory ancestry for configured-root separation without relying on path-prefix strings."""
    current = os.dup(descriptor)
    result = set()
    try:
        for _ in range(66):
            info = os.fstat(current)
            identity = (info.st_dev, info.st_ino)
            if identity in result:
                return result
            result.add(identity)
            parent = os.open("..", ROOT_FLAGS, dir_fd=current)
            os.close(current)
            current = parent
        raise WorkspaceAccessError("checkpoint_ancestry_limit", 503)
    finally:
        os.close(current)


class PrivateCheckpointRoot:
    """Own one explicitly configured private root and nonqueued process/thread locks outside registered workspaces."""

    def __init__(self, root, catalog):
        """Open existing nonsymlink owned0700 storage, reject native workspace overlap and lock a validated private inode."""
        self.spec = SimpleNamespace(root=os.fspath(root))
        self.fd = self.lock_fd = None
        self.closing = False
        self.admission = threading.Lock()
        try:
            if os.getuid() == 0 or os.getuid() != os.geteuid():
                raise WorkspaceAccessError("checkpoint_identity_unsupported", 503)
            self.fd = open_root(self.spec)
            self.identity = self.directory_info(self.fd)
            ancestors = ancestor_identities(self.fd)
            for spec in catalog.specifications:
                workspace = open_root(spec)
                try:
                    info = os.fstat(workspace)
                    if (info.st_dev, info.st_ino) in ancestors or (
                        self.identity.st_dev,
                        self.identity.st_ino,
                    ) in ancestor_identities(workspace):
                        raise WorkspaceAccessError("checkpoint_workspace_overlap", 422)
                finally:
                    os.close(workspace)
            self.lock_fd = os.open(
                ".store.lock",
                os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC,
                0o600,
                dir_fd=self.fd,
            )
            self.lock_identity = self.file_info(self.lock_fd)
            try:
                fcntl.flock(self.lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise WorkspaceAccessError("checkpoint_store_busy", 429) from None
            os.fsync(self.lock_fd)
            os.fsync(self.fd)
            logger.info("checkpoint_root_opened")
        except BaseException:
            self.close()
            raise

    def directory_info(self, descriptor):
        """Require an owned private directory on the anchored filesystem without following aliases."""
        info = os.fstat(descriptor)
        if (
            not stat.S_ISDIR(info.st_mode)
            or info.st_uid != os.getuid()
            or stat.S_IMODE(info.st_mode) != 0o700
        ):
            raise WorkspaceAccessError("checkpoint_directory_unsafe", 503)
        if hasattr(self, "identity") and info.st_dev != self.identity.st_dev:
            raise WorkspaceAccessError("checkpoint_device_changed", 503)
        return info

    def file_info(self, descriptor):
        """Require a private owned single-link regular file before reading, replacing or trusting storage bytes."""
        info = os.fstat(descriptor)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.getuid()
            or stat.S_IMODE(info.st_mode) != 0o600
            or info.st_nlink != 1
            or info.st_dev != self.identity.st_dev
        ):
            raise WorkspaceAccessError("checkpoint_file_unsafe", 503)
        return info

    def validate(self):
        """Reject closed/replaced storage or lock entry before another native operation on retained capabilities."""
        if self.closing or self.fd is None:
            raise WorkspaceAccessError("checkpoint_unavailable", 503)
        current = open_root(self.spec)
        try:
            info = self.directory_info(current)
            if (info.st_dev, info.st_ino) != (
                self.identity.st_dev,
                self.identity.st_ino,
            ):
                raise WorkspaceAccessError("checkpoint_root_changed", 409)
        finally:
            os.close(current)
        named = os.stat(".store.lock", dir_fd=self.fd, follow_symlinks=False)
        held = self.file_info(self.lock_fd)
        if (named.st_dev, named.st_ino) != (held.st_dev, held.st_ino):
            raise WorkspaceAccessError("checkpoint_lock_changed", 409)

    @contextmanager
    def operation(self):
        """Reject overlapping storage work immediately and validate native root/lock identity before admission."""
        if not self.admission.acquire(blocking=False):
            raise WorkspaceAccessError("checkpoint_store_busy", 429)
        try:
            self.validate()
            yield
        finally:
            self.admission.release()
            logger.info("checkpoint_storage_operation_closed")

    @contextmanager
    def directory(self, parent, name):
        """Borrow a kernel-scoped private directory descriptor and close it on every caller outcome."""
        descriptor = open_beneath(parent, name, flags=ROOT_FLAGS)
        try:
            self.directory_info(descriptor)
            yield descriptor
        finally:
            os.close(descriptor)

    def read(self, directory, name, limit=MAX_RECORD_BYTES):
        """Read one bounded stable private regular file through an admitted directory descriptor."""
        descriptor = open_beneath(directory, name)
        try:
            before = self.file_info(descriptor)
            if before.st_size > limit:
                raise WorkspaceAccessError("checkpoint_record_limit", 413)
            raw = bytearray()
            while len(raw) <= limit:
                chunk = os.read(descriptor, min(4096, limit + 1 - len(raw)))
                if not chunk:
                    break
                raw.extend(chunk)
            after = self.file_info(descriptor)
            if (
                len(raw) > limit
                or len(raw) != before.st_size
                or fingerprint(before) != fingerprint(after)
            ):
                raise WorkspaceAccessError("checkpoint_file_changed", 409)
            return bytes(raw)
        finally:
            os.close(descriptor)

    def create_file(self, directory, name, raw):
        """Write/fsync a new bounded private file without truncating an existing or unowned directory entry."""
        if type(raw) is not bytes or len(raw) > MAX_RECORD_BYTES:
            raise WorkspaceAccessError("checkpoint_record_limit", 413)
        descriptor = os.open(
            name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
            0o600,
            dir_fd=directory,
        )
        try:
            self.file_info(descriptor)
            offset = 0
            while offset < len(raw):
                count = os.write(descriptor, raw[offset:])
                if count <= 0:
                    raise OSError("checkpoint_write_failed")
                offset += count
            os.fsync(descriptor)
            info = self.file_info(descriptor)
        finally:
            os.close(descriptor)
        os.fsync(directory)
        logger.info("checkpoint_private_file_created bytes=%d", len(raw))
        return info.st_dev, info.st_ino

    def replace_journal(self, directory, value):
        """Publish a complete fsynced journal atomically and only clean an acknowledged-owned temporary inode."""
        raw = canonical(value)
        name = ".journal-" + uuid4().hex + ".tmp"
        identity = None
        try:
            identity = self.create_file(directory, name, raw)
            self.validate()
            os.replace(name, "journal.json", src_dir_fd=directory, dst_dir_fd=directory)
            os.fsync(directory)
            logger.info("checkpoint_journal_published state=%s", value["state"])
        finally:
            if identity is not None:
                try:
                    info = os.stat(name, dir_fd=directory, follow_symlinks=False)
                    if (info.st_dev, info.st_ino) != identity:
                        raise WorkspaceAccessError(
                            "checkpoint_journal_cleanup_uncertain", 503
                        )
                    os.unlink(name, dir_fd=directory)
                except FileNotFoundError:
                    pass

    def scan_git(self, directory, *, normalize=False):
        """Bound/hash every private Git inode, reject aliases and fsync newly normalized files/directories before publication."""
        manifest, allocated, entries = {}, 0, 0

        def visit(descriptor, prefix, depth):
            """Walk only bounded kernel-admitted private directories without following links or mount aliases."""
            nonlocal allocated, entries
            info = self.directory_info(descriptor)
            allocated += info.st_blocks * 512
            names = os.listdir(descriptor)
            entries += len(names)
            if entries > 64 or depth > 8 or allocated > RESERVATION_BYTES:
                raise WorkspaceAccessError("checkpoint_storage_limit", 413)
            for name in sorted(names):
                child = open_beneath(descriptor, name)
                try:
                    info = os.fstat(child)
                    if stat.S_ISDIR(info.st_mode):
                        visit(child, prefix + name + "/", depth + 1)
                    else:
                        if (
                            normalize
                            and stat.S_ISREG(info.st_mode)
                            and info.st_uid == os.getuid()
                            and info.st_nlink == 1
                        ):
                            os.fchmod(child, 0o600)
                        before = self.file_info(child)
                        allocated += before.st_blocks * 512
                        if (
                            allocated > RESERVATION_BYTES
                            or before.st_size > RESERVATION_BYTES
                        ):
                            raise WorkspaceAccessError("checkpoint_storage_limit", 413)
                        digest, length = hashlib.sha256(), 0
                        while True:
                            chunk = os.read(child, 4096)
                            if not chunk:
                                break
                            length += len(chunk)
                            if length > RESERVATION_BYTES:
                                raise WorkspaceAccessError(
                                    "checkpoint_storage_limit", 413
                                )
                            digest.update(chunk)
                        if length != before.st_size or fingerprint(
                            before
                        ) != fingerprint(self.file_info(child)):
                            raise WorkspaceAccessError("checkpoint_file_changed", 409)
                        manifest[prefix + name] = digest.hexdigest()
                        if normalize:
                            os.fsync(child)
                finally:
                    os.close(child)
            if normalize:
                os.fsync(descriptor)

        visit(directory, "", 0)
        logger.info(
            "checkpoint_git_files_verified files=%d allocated_bytes=%d",
            len(manifest),
            allocated,
        )
        return manifest, allocated

    def close(self):
        """Reject premature concurrent close and release held lock/root once after owned work joins, retaining all backups."""
        if not self.admission.acquire(blocking=False):
            raise WorkspaceAccessError("checkpoint_store_busy", 429)
        try:
            self.closing = True
            lock, root = self.lock_fd, self.fd
            self.lock_fd = self.fd = None
            try:
                if lock is not None:
                    os.close(lock)
            finally:
                if root is not None:
                    os.close(root)
        finally:
            self.admission.release()
        logger.info("checkpoint_root_closed")
