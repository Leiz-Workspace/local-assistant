"""Store opaque local blobs with bounded writes, descriptor locks and durable cleanup.

This adapter does not authorize users or release quotas. Its caller must fence the
PostgreSQL journal before creation/publication/purge and keep allocation charged
until purge returns True. Runtime admission requires explicit operator enablement.
"""

from __future__ import annotations

import errno
import fcntl
import hashlib
import logging
import os
import stat
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Iterator
from uuid import UUID, uuid4

from src.application.services.file_storage_policy import (
    DEFAULT_POLICY,
    FileReservationPlan,
    StoragePolicy,
    StoragePolicyError,
    validate_size,
)

logger = logging.getLogger(__name__)
DIRECTORY_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
FILE_FLAGS = os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC


class BlobStorageError(Exception):
    """Expose stable storage failures without leaking paths, content or OS messages."""

    def __init__(self, code: str):
        """Record a safe error code for journal reconciliation and audit logs."""
        super().__init__(code)
        self.code = code
        logger.warning("blob_operation_failed code=%s", code)


@dataclass(frozen=True, slots=True)
class BlobIdentity:
    """Derive exact object and staging names from trusted journal UUIDs only."""

    owner_id: UUID
    file_id: UUID
    lease_id: UUID

    def __post_init__(self):
        """Reject arbitrary strings before any filesystem operation."""
        if any(
            not isinstance(value, UUID)
            for value in (self.owner_id, self.file_id, self.lease_id)
        ):
            raise BlobStorageError("invalid_identity")

    @property
    def object_parts(self) -> tuple[str, ...]:
        """Return the opaque destination components defined by ADR-019."""
        return (
            "objects",
            str(self.owner_id),
            self.file_id.hex[:2],
            f"{self.file_id}.blob",
        )

    @property
    def staging_parts(self) -> tuple[str, ...]:
        """Return the single staging name owned by the journal upload lease."""
        return (
            "staging",
            str(self.owner_id),
            str(self.file_id),
            f"{self.lease_id}.part",
        )


def _same_inode(left: os.stat_result, right: os.stat_result) -> bool:
    """Compare inode identity without trusting filenames or timestamps."""
    return (left.st_dev, left.st_ino) == (right.st_dev, right.st_ino)


def _validate_file(info: os.stat_result, device: int) -> None:
    """Require an owner-only regular file on the anchored root filesystem."""
    if (
        not stat.S_ISREG(info.st_mode)
        or info.st_uid != os.geteuid()
        or stat.S_IMODE(info.st_mode) != 0o600
        or info.st_dev != device
    ):
        raise BlobStorageError("unsafe_blob")


class BlobHandle:
    """Own a locked file and its parent descriptor until explicit or contextual close."""

    def __init__(self, fd: int, parent_fd: int, name: str, device: int):
        """Take ownership of descriptors already opened and validated by the adapter."""
        self._fd = fd
        self._parent_fd = parent_fd
        self._name = name
        self._device = device
        self._guard_fd = -1

    def __enter__(self):
        """Keep the payload lock held for the entire caller operation."""
        try:
            self._check()
        except BaseException:
            self.close()
            raise
        return self

    def __exit__(self, exc_type, exc, traceback):
        """Release file and directory descriptors even after failed caller work."""
        self.close()

    def close(self) -> None:
        """Release descriptors idempotently without unlinking or releasing DB quota."""
        if self._fd < 0:
            return
        descriptor, parent = self._fd, self._parent_fd
        self._fd = self._parent_fd = -1
        try:
            os.close(descriptor)
        finally:
            try:
                os.close(parent)
            finally:
                if self._guard_fd >= 0:
                    os.close(self._guard_fd)
                    self._guard_fd = -1
                logger.info("blob_handle_closed")

    def _check(self, *, links: int = 1) -> os.stat_result:
        """Check the locked FD still names the expected private, singly owned inode."""
        if self._fd < 0:
            raise BlobStorageError("handle_closed")
        info = os.fstat(self._fd)
        _validate_file(info, self._device)
        named = os.stat(self._name, dir_fd=self._parent_fd, follow_symlinks=False)
        if not _same_inode(info, named) or info.st_nlink != links:
            raise BlobStorageError("inode_changed")
        return info


class BlobReader(BlobHandle):
    """Read bounded chunks while keeping a shared inode lock against deletion."""

    def read(self, size: int = DEFAULT_POLICY.chunk_bytes) -> bytes:
        """Read a bounded amount from the locked FD without reopening its path."""
        if type(size) is not int or not 1 <= size <= DEFAULT_POLICY.chunk_bytes:
            raise BlobStorageError("invalid_read_size")
        self._check()
        result = os.read(self._fd, size)
        logger.debug("blob_chunk_read size_bytes=%d", len(result))
        return result

    def verify_integrity(
        self, size_bytes: int, expected_sha256: str, *, links: int = 1
    ) -> None:
        """Check immutable ready bytes through the locked FD before HTTP headers are sent."""
        info = self._check(links=links)
        if info.st_size != size_bytes:
            raise BlobStorageError("blob_integrity_mismatch")
        digest = hashlib.sha256()
        offset = 0
        while offset < size_bytes:
            chunk = os.pread(
                self._fd, min(DEFAULT_POLICY.chunk_bytes, size_bytes - offset), offset
            )
            if not chunk:
                break
            digest.update(chunk)
            offset += len(chunk)
        if offset != size_bytes or digest.hexdigest() != expected_sha256:
            raise BlobStorageError("blob_integrity_mismatch")
        logger.info("blob_integrity_verified size_bytes=%d", size_bytes)


class BlobResourceLock:
    """Fence file creation and cleanup through a persistent private directory inode."""

    def __init__(self, descriptor: int, identity: BlobIdentity):
        """Own a nonblocking exclusive directory lock for a journal resource."""
        self._fd = descriptor
        self.identity = identity

    def __enter__(self):
        """Keep the resource locked while the caller validates its DB lease/state."""
        if self._fd < 0:
            raise BlobStorageError("resource_lock_closed")
        return self

    def __exit__(self, exc_type, exc, traceback):
        """Release the directory FD; duplicates held by writers retain its lock."""
        self.close()

    def close(self) -> None:
        """Close the lock idempotently without unlinking the stable directory inode."""
        if self._fd >= 0:
            os.close(self._fd)
            self._fd = -1
            logger.info("blob_resource_lock_closed file_id=%s", self.identity.file_id)


class BlobWriter(BlobHandle):
    """Bound a single staged upload and retain its exclusive lock through publication."""

    def __init__(
        self,
        fd: int,
        parent_fd: int,
        name: str,
        device: int,
        plan: FileReservationPlan,
        identity: BlobIdentity,
        storage: LocalBlobStorage,
    ):
        """Initialize byte accounting without buffering any payload in memory."""
        super().__init__(fd, parent_fd, name, device)
        self.plan = plan
        self.identity = identity
        self.storage = storage
        self._hash = hashlib.sha256()
        self.bytes_written = 0
        self.sealed = False
        self.published = False
        self.failed = False
        self.policy = storage.policy

    def write(self, chunk: bytes) -> None:
        """Write one policy-bounded chunk, checking size and free space before allocation."""
        self._check()
        if self.sealed or self.failed:
            raise BlobStorageError("writer_not_writable")
        if (
            not isinstance(chunk, bytes)
            or not 0 < len(chunk) <= self.policy.chunk_bytes
        ):
            raise BlobStorageError("invalid_write_size")
        if self.bytes_written + len(chunk) > self.plan.size_bytes:
            self.failed = True
            raise StoragePolicyError("file_size_mismatch", 413)
        if self.storage.free_bytes() - len(chunk) < self.policy.min_free_bytes:
            self.failed = True
            raise BlobStorageError("insufficient_disk_space")
        try:
            view = memoryview(chunk)
            while view:
                written = os.write(self._fd, view)
                if written <= 0:
                    raise BlobStorageError("write_failed")
                self._hash.update(view[:written])
                self.bytes_written += written
                view = view[written:]
        except BaseException:
            self.failed = True
            logger.warning("blob_write_interrupted file_id=%s", self.identity.file_id)
            raise
        logger.debug("blob_chunk_written size_bytes=%d", len(chunk))

    def seal(self) -> None:
        """Check observed size/hash and fsync bytes before allowing publication."""
        info = self._check()
        if self.sealed or self.failed:
            raise BlobStorageError("writer_not_writable")
        if (
            info.st_size != self.bytes_written
            or self.bytes_written != self.plan.size_bytes
        ):
            self.failed = True
            raise StoragePolicyError("file_size_mismatch", 422)
        if self._hash.hexdigest() != self.plan.expected_sha256:
            self.failed = True
            raise StoragePolicyError("file_hash_mismatch", 422)
        try:
            os.fsync(self._fd)
        except OSError:
            self.failed = True
            raise BlobStorageError("file_sync_failed") from None
        self.sealed = True
        logger.info(
            "blob_sealed file_id=%s size_bytes=%d",
            self.identity.file_id,
            self.bytes_written,
        )

    @contextmanager
    def verification_reader(self) -> Iterator[BinaryIO]:
        """Lend a bounded-lifetime duplicate FD to a verifier while retaining the writer lock."""
        self._check()
        if not self.sealed or self.published or self.failed:
            raise BlobStorageError("writer_not_verifiable")
        with os.fdopen(os.dup(self._fd), "rb", closefd=True) as source:
            source.seek(0)
            try:
                yield source
            finally:
                source.seek(0)
                logger.info(
                    "blob_verification_reader_closed file_id=%s", self.identity.file_id
                )

    def publish(self) -> None:
        """Link bytes without replacement and fsync both names while retaining the inode lock.

        The caller must first verify media and fence the DB lease. This method does
        not make the DB row ready; failures leave charged names for reconciliation.
        """
        self._check()
        if not self.sealed or self.published or self.failed:
            raise BlobStorageError("writer_not_publishable")
        self._verify_sealed_bytes()
        destination = self.storage._directory(
            self.identity.object_parts[:-1], create=True
        )
        try:
            try:
                os.link(
                    self._name,
                    self.identity.object_parts[-1],
                    src_dir_fd=self._parent_fd,
                    dst_dir_fd=destination,
                    follow_symlinks=False,
                )
            except FileExistsError:
                raise BlobStorageError("object_exists") from None
            except OSError:
                raise BlobStorageError("publication_failed") from None
            self._check(links=2)
            final = os.stat(
                self.identity.object_parts[-1],
                dir_fd=destination,
                follow_symlinks=False,
            )
            if not _same_inode(final, os.fstat(self._fd)):
                raise BlobStorageError("inode_changed")
            os.fsync(destination)
            os.unlink(self._name, dir_fd=self._parent_fd)
            os.fsync(self._parent_fd)
            os.close(self._parent_fd)
            self._parent_fd = destination
            destination = -1
            self._name = self.identity.object_parts[-1]
            self.published = True
            self._check()
            logger.info("blob_published file_id=%s", self.identity.file_id)
        except BaseException:
            self.failed = True
            logger.warning(
                "blob_publication_incomplete file_id=%s", self.identity.file_id
            )
            raise
        finally:
            if destination >= 0:
                os.close(destination)

    def _verify_sealed_bytes(self) -> None:
        """Detect changes through a verifier FD before durably publishing its inode."""
        digest = hashlib.sha256()
        offset = 0
        while offset < self.plan.size_bytes:
            chunk = os.pread(
                self._fd,
                min(self.policy.chunk_bytes, self.plan.size_bytes - offset),
                offset,
            )
            if not chunk:
                break
            digest.update(chunk)
            offset += len(chunk)
        if (
            os.fstat(self._fd).st_size != self.plan.size_bytes
            or offset != self.plan.size_bytes
            or digest.hexdigest() != self.plan.expected_sha256
        ):
            self.failed = True
            raise BlobStorageError("sealed_blob_changed")


class LocalBlobStorage:
    """Anchor private local storage to a no-follow root descriptor on Linux."""

    def __init__(
        self,
        root: Path,
        policy: StoragePolicy = DEFAULT_POLICY,
        *,
        namespace_id: UUID | None = None,
    ):
        """Open or create only the final private root, refusing symlink ancestors."""
        self.policy = policy
        self._root_fd = -1
        path = Path(os.path.abspath(root))
        descriptor = os.open(path.anchor, DIRECTORY_FLAGS)
        try:
            for index, component in enumerate(path.parts[1:]):
                if index == len(path.parts) - 2:
                    try:
                        os.mkdir(component, 0o700, dir_fd=descriptor)
                    except FileExistsError:
                        pass
                    os.fsync(descriptor)
                child = os.open(component, DIRECTORY_FLAGS, dir_fd=descriptor)
                os.close(descriptor)
                descriptor = child
            info = os.fstat(descriptor)
            self._device = info.st_dev
            self._validate_directory(info)
            os.fsync(descriptor)
            self._root_fd, descriptor = descriptor, -1
        except (OSError, ValueError):
            raise BlobStorageError("unsafe_root") from None
        finally:
            if descriptor >= 0:
                os.close(descriptor)
        try:
            self.namespace_id = self._load_namespace(namespace_id)
        except BaseException:
            self.close()
            raise
        logger.info("blob_storage_opened namespace_id=%s", self.namespace_id)

    def _load_namespace(self, expected: UUID | None) -> UUID:
        """Read/create a durable private namespace marker without replacing an existing identity."""
        if expected is not None and not isinstance(expected, UUID):
            raise BlobStorageError("invalid_storage_namespace")
        name = ".storage-namespace"
        try:
            descriptor = os.open(name, os.O_RDONLY | FILE_FLAGS, dir_fd=self._root_fd)
        except FileNotFoundError:
            identifier = expected or uuid4()
            try:
                descriptor = os.open(
                    name,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL | FILE_FLAGS,
                    0o600,
                    dir_fd=self._root_fd,
                )
            except FileExistsError:
                return self._load_namespace(expected)
            try:
                data = memoryview((str(identifier) + "\n").encode("ascii"))
                while data:
                    written = os.write(descriptor, data)
                    if written <= 0:
                        raise BlobStorageError("namespace_write_failed")
                    data = data[written:]
                os.fsync(descriptor)
                os.fsync(self._root_fd)
            finally:
                os.close(descriptor)
            descriptor = os.open(name, os.O_RDONLY | FILE_FLAGS, dir_fd=self._root_fd)
        try:
            info = os.fstat(descriptor)
            _validate_file(info, self._device)
            if info.st_nlink != 1 or info.st_size != 37:
                raise BlobStorageError("invalid_storage_namespace")
            data = os.read(descriptor, 38)
            identifier = UUID(data[:36].decode("ascii"))
            if data != (str(identifier) + "\n").encode("ascii") or (
                expected is not None and identifier != expected
            ):
                raise BlobStorageError("storage_namespace_mismatch")
            return identifier
        except (ValueError, UnicodeError):
            raise BlobStorageError("invalid_storage_namespace") from None
        finally:
            os.close(descriptor)

    def __enter__(self):
        """Keep the trusted root anchored across a scoped adapter lifetime."""
        self._ensure_open()
        return self

    def __exit__(self, exc_type, exc, traceback):
        """Close the root descriptor without touching payload names."""
        self.close()

    def close(self) -> None:
        """Close the root idempotently; outstanding handles still own their locks."""
        if self._root_fd >= 0:
            os.close(self._root_fd)
            self._root_fd = -1
            logger.info("blob_storage_closed")

    def _ensure_open(self) -> None:
        """Refuse operations after close rather than using a recycled descriptor."""
        if self._root_fd < 0:
            raise BlobStorageError("storage_closed")
        self._validate_directory(os.fstat(self._root_fd))

    def _validate_directory(self, info: os.stat_result) -> None:
        """Require private directories on the same filesystem as the opened root."""
        if (
            not stat.S_ISDIR(info.st_mode)
            or info.st_uid != os.geteuid()
            or stat.S_IMODE(info.st_mode) != 0o700
            or info.st_dev != self._device
        ):
            raise BlobStorageError("unsafe_directory")

    def _directory(self, parts: tuple[str, ...], *, create: bool = False) -> int:
        """Walk generated components relative to the root without following links."""
        self._ensure_open()
        descriptor = os.dup(self._root_fd)
        try:
            for component in parts:
                if create:
                    try:
                        os.mkdir(component, 0o700, dir_fd=descriptor)
                    except FileExistsError:
                        pass
                    os.fsync(descriptor)
                child = os.open(component, DIRECTORY_FLAGS, dir_fd=descriptor)
                try:
                    self._validate_directory(os.fstat(child))
                except BaseException:
                    os.close(child)
                    raise
                os.close(descriptor)
                descriptor = child
            result, descriptor = descriptor, -1
            return result
        finally:
            if descriptor >= 0:
                os.close(descriptor)

    def free_bytes(self) -> int:
        """Measure available bytes for the current process through the anchored root."""
        self._ensure_open()
        info = os.fstatvfs(self._root_fd)
        return info.f_bavail * info.f_frsize

    def inventory(self, *, max_entries=100000) -> dict[str, int]:
        """Inventory private payload names through FDs without following links or adopting data."""
        self._ensure_open()
        if type(max_entries) is not int or max_entries <= 0:
            raise BlobStorageError("invalid_inventory_bound")
        result = {}
        visited = 0
        marker_seen = False

        def walk(directory, parts):
            """Traverse bounded private directory depth and close every child FD on failure."""
            nonlocal visited, marker_seen
            with os.scandir(directory) as entries:
                for entry in entries:
                    visited += 1
                    if visited > max_entries or len(parts) > 3:
                        raise BlobStorageError("inventory_limits_exceeded")
                    info = os.stat(entry.name, dir_fd=directory, follow_symlinks=False)
                    if stat.S_ISDIR(info.st_mode):
                        child = os.open(entry.name, DIRECTORY_FLAGS, dir_fd=directory)
                        try:
                            self._validate_directory(os.fstat(child))
                            walk(child, (*parts, entry.name))
                        finally:
                            os.close(child)
                    else:
                        _validate_file(info, self._device)
                        if info.st_nlink != 1:
                            raise BlobStorageError("unowned_blob_link")
                        if not parts and entry.name == ".storage-namespace":
                            marker_seen = True
                            descriptor = os.open(
                                entry.name, os.O_RDONLY | FILE_FLAGS, dir_fd=directory
                            )
                            try:
                                if os.read(descriptor, 38) != (
                                    str(self.namespace_id) + "\n"
                                ).encode("ascii"):
                                    raise BlobStorageError("storage_namespace_mismatch")
                            finally:
                                os.close(descriptor)
                        else:
                            result["/".join((*parts, entry.name))] = info.st_size

        walk(self._root_fd, ())
        if not marker_seen:
            raise BlobStorageError("missing_storage_namespace")
        logger.info("blob_inventory_completed payloads=%d", len(result))
        return result

    def reconcile_ready(
        self, identity: BlobIdentity, size_bytes: int, expected_sha256: str
    ) -> bool:
        """Remove only a proven redundant known staging link, retaining the ready blob and quota."""
        try:
            guard = self.lock_resource(identity)
        except BlockingIOError:
            return False
        with guard:
            self._check_staging_inventory(guard._fd, identity)
            parent = self._directory(identity.object_parts[:-1])
            descriptor = -1
            try:
                descriptor = os.open(
                    identity.object_parts[-1], os.O_RDONLY | FILE_FLAGS, dir_fd=parent
                )
                try:
                    stage = os.stat(
                        identity.staging_parts[-1],
                        dir_fd=guard._fd,
                        follow_symlinks=False,
                    )
                except FileNotFoundError:
                    info = os.fstat(descriptor)
                    _validate_file(info, self._device)
                    if info.st_size != size_bytes or info.st_nlink != 1:
                        raise BlobStorageError("blob_integrity_mismatch")
                    return True
                try:
                    fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    return False
                _validate_file(stage, self._device)
                if not _same_inode(stage, os.fstat(descriptor)):
                    raise BlobStorageError("object_collision")
                reader = BlobReader(
                    descriptor, parent, identity.object_parts[-1], self._device
                )
                reader.verify_integrity(size_bytes, expected_sha256, links=2)
                os.unlink(identity.staging_parts[-1], dir_fd=guard._fd)
                os.fsync(guard._fd)
                logger.info(
                    "blob_ready_staging_link_removed file_id=%s", identity.file_id
                )
                return True
            finally:
                if descriptor >= 0:
                    os.close(descriptor)
                os.close(parent)

    def _check_staging_inventory(self, directory: int, identity: BlobIdentity) -> None:
        """Quarantine unexpected lease names instead of treating their bytes as absent."""
        with os.scandir(directory) as entries:
            for entry in entries:
                if entry.name != identity.staging_parts[-1]:
                    raise BlobStorageError("untracked_staging_entry")

    def lock_resource(self, identity: BlobIdentity) -> BlobResourceLock:
        """Lock a stable file directory before DB admission, payload creation or purge.

        The service must recheck the journal while holding this lock, then pass it
        to create_writer. Never remove these directories or unlock explicitly:
        duplicated directory FDs retain the lock until the last writer closes.
        """
        parent = self._directory(identity.staging_parts[:-1], create=True)
        try:
            fcntl.flock(parent, fcntl.LOCK_EX | fcntl.LOCK_NB)
            logger.info("blob_resource_locked file_id=%s", identity.file_id)
            return BlobResourceLock(parent, identity)
        except BaseException:
            os.close(parent)
            raise

    def create_writer(
        self,
        plan: FileReservationPlan,
        lease_id: UUID,
        *,
        guard: BlobResourceLock | None = None,
        policy: StoragePolicy | None = None,
    ) -> BlobWriter:
        """Create a staged inode while retaining a resource lock through writer close.

        Standalone callers may omit the guard. Journal-integrated callers must
        acquire it first, validate/claim their DB lease under it, then pass it here.
        """
        identity = BlobIdentity(plan.owner_id, plan.file_id, lease_id)
        selected_policy = policy or self.policy
        validate_size(plan.size_bytes, selected_policy)
        if plan.storage_key != "/".join(identity.object_parts):
            raise BlobStorageError("invalid_storage_key")
        if guard is None:
            with self.lock_resource(identity) as acquired:
                return self.create_writer(
                    plan, lease_id, guard=acquired, policy=selected_policy
                )
        if guard._fd < 0 or guard.identity != identity:
            raise BlobStorageError("invalid_resource_lock")
        parent = self._directory(identity.staging_parts[:-1], create=True)
        descriptor = -1
        guard_fd = -1
        try:
            if not _same_inode(os.fstat(parent), os.fstat(guard._fd)):
                raise BlobStorageError("invalid_resource_lock")
            self._check_staging_inventory(parent, identity)
            guard_fd = os.dup(guard._fd)
            descriptor = os.open(
                identity.staging_parts[-1],
                os.O_RDWR | os.O_CREAT | os.O_EXCL | FILE_FLAGS,
                0o600,
                dir_fd=parent,
            )
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            handle = BlobWriter(
                descriptor,
                parent,
                identity.staging_parts[-1],
                self._device,
                plan,
                identity,
                self,
            )
            handle._guard_fd = guard_fd
            handle.policy = selected_policy
            handle._check()
            os.fsync(parent)
            logger.info("blob_writer_created file_id=%s", plan.file_id)
            return handle
        except BaseException:
            if descriptor >= 0:
                os.close(descriptor)
            if guard_fd >= 0:
                os.close(guard_fd)
            os.close(parent)
            logger.warning("blob_writer_creation_failed file_id=%s", plan.file_id)
            raise

    def open_reader(self, identity: BlobIdentity) -> BlobReader:
        """Lock a published inode; the caller must recheck owner/ready state before reading."""
        parent = self._directory(identity.object_parts[:-1])
        descriptor = -1
        try:
            descriptor = os.open(
                identity.object_parts[-1], os.O_RDONLY | FILE_FLAGS, dir_fd=parent
            )
            fcntl.flock(descriptor, fcntl.LOCK_SH | fcntl.LOCK_NB)
            handle = BlobReader(
                descriptor, parent, identity.object_parts[-1], self._device
            )
            handle._check()
            logger.info("blob_reader_opened file_id=%s", identity.file_id)
            return handle
        except BaseException:
            if descriptor >= 0:
                os.close(descriptor)
            os.close(parent)
            logger.warning("blob_reader_open_failed file_id=%s", identity.file_id)
            raise

    def purge(self, identity: BlobIdentity) -> bool:
        """Remove only the journal's exact names after locking every referenced inode.

        Return False on a held lock without unlinking anything. True means names
        are absent, directory removals are durable and local FDs have closed; only
        then may a fenced DB transaction release quota. Unknown staging names
        quarantine the resource; they are never deleted or treated as absent.
        """
        try:
            guard = self.lock_resource(identity)
        except BlockingIOError:
            logger.info("blob_purge_pending file_id=%s", identity.file_id)
            return False
        except OSError:
            raise BlobStorageError("purge_failed") from None
        with guard:
            self._check_staging_inventory(guard._fd, identity)
            return self._purge_locked(identity)

    def _purge_locked(self, identity: BlobIdentity) -> bool:
        """Purge exact names while the resource directory prevents late file creation."""
        self._ensure_open()
        opened: list[tuple[int, int, str]] = []
        locked: dict[tuple[int, int], int] = {}
        try:
            for parts in (identity.staging_parts, identity.object_parts):
                try:
                    parent = self._directory(parts[:-1])
                except FileNotFoundError:
                    continue
                try:
                    descriptor = os.open(
                        parts[-1], os.O_RDONLY | FILE_FLAGS, dir_fd=parent
                    )
                except FileNotFoundError:
                    try:
                        os.fsync(parent)
                    finally:
                        os.close(parent)
                    continue
                except BaseException:
                    os.close(parent)
                    raise
                opened.append((descriptor, parent, parts[-1]))
                info = os.fstat(descriptor)
                _validate_file(info, self._device)
                key = (info.st_dev, info.st_ino)
                if key not in locked:
                    try:
                        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    except BlockingIOError:
                        logger.info("blob_purge_pending file_id=%s", identity.file_id)
                        return False
                    locked[key] = descriptor
            if len(locked) > 1:
                raise BlobStorageError("object_collision")
            for descriptor, parent, name in opened:
                info = os.fstat(descriptor)
                named = os.stat(name, dir_fd=parent, follow_symlinks=False)
                links = sum(
                    _same_inode(info, os.fstat(other)) for other, _, _ in opened
                )
                if not _same_inode(info, named) or info.st_nlink != links:
                    raise BlobStorageError("unowned_blob_link")
            for _, parent, name in opened:
                os.unlink(name, dir_fd=parent)
                os.fsync(parent)
        except OSError as exc:
            code = (
                "insufficient_disk_space"
                if exc.errno == errno.ENOSPC
                else "purge_failed"
            )
            raise BlobStorageError(code) from None
        finally:
            for descriptor, parent, _ in reversed(opened):
                try:
                    os.close(descriptor)
                finally:
                    os.close(parent)
        logger.info("blob_purged file_id=%s names=%d", identity.file_id, len(opened))
        return True
