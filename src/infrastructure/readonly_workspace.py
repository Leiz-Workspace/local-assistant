"""Discover explicit owned workspaces through Linux read-only descriptor capabilities without git execution."""

import ctypes
import errno
import logging
import os
import platform
import stat
import sys
from contextlib import contextmanager

from src.application.services.workspace_policy import (
    MAX_WORKSPACES,
    WorkspaceAccessError,
    WorkspaceSpec,
    clean_parts,
)

logger = logging.getLogger(__name__)
READ_FLAGS = os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK
ROOT_FLAGS = READ_FLAGS | os.O_DIRECTORY
RESOLVE_NO_XDEV = 0x01
RESOLVE_NO_MAGICLINKS = 0x02
RESOLVE_NO_SYMLINKS = 0x04
RESOLVE_BENEATH = 0x08
ROOT_RESOLVE = RESOLVE_BENEATH | RESOLVE_NO_MAGICLINKS | RESOLVE_NO_SYMLINKS
ENTRY_RESOLVE = ROOT_RESOLVE | RESOLVE_NO_XDEV
OPENAT2_SYSCALL = 437


class OpenHow(ctypes.Structure):
    """Represent the verified local Linux openat2 unsigned64 ABI."""

    _fields_ = [
        ("flags", ctypes.c_uint64),
        ("mode", ctypes.c_uint64),
        ("resolve", ctypes.c_uint64),
    ]


def open_beneath(directory, path, *, flags=READ_FLAGS, resolve=ENTRY_RESOLVE):
    """Ask the kernel to resolve a read-only relative target beneath an existing directory capability."""
    if sys.platform != "linux" or platform.machine() != "x86_64":
        raise WorkspaceAccessError("workspace_platform_unsupported", 503)
    library = ctypes.CDLL(None, use_errno=True)
    library.syscall.restype = ctypes.c_long
    how = OpenHow(flags=flags, mode=0, resolve=resolve)
    result = library.syscall(
        ctypes.c_long(OPENAT2_SYSCALL),
        ctypes.c_int(directory),
        ctypes.c_char_p(path.encode("utf-8")),
        ctypes.byref(how),
        ctypes.c_size_t(ctypes.sizeof(how)),
    )
    if result < 0:
        number = ctypes.get_errno()
        if number in {errno.ENOSYS, errno.E2BIG, errno.EINVAL}:
            raise WorkspaceAccessError("workspace_platform_unsupported", 503)
        raise OSError(number, "workspace_entry_unavailable")
    return int(result)


def open_root(spec):
    """Open only the explicit absolute root without following any symlink ancestor."""
    clean_parts(spec.root, absolute=True)
    anchor = os.open("/", ROOT_FLAGS)
    try:
        return open_beneath(
            anchor, spec.root[1:], flags=ROOT_FLAGS, resolve=ROOT_RESOLVE
        )
    except OSError:
        raise WorkspaceAccessError("workspace_root_unavailable", 503) from None
    finally:
        os.close(anchor)


class ReadonlyWorkspace:
    """Own one pinned root FD and admit only read-only relative regular files/directories."""

    def __init__(self, spec):
        """Pin an already owner-authorized configured root and retain its admission identity."""
        self.spec = spec
        self.fd = open_root(spec)
        try:
            self.identity = os.fstat(self.fd)
        except OSError:
            os.close(self.fd)
            self.fd = None
            raise WorkspaceAccessError("workspace_root_unavailable", 503) from None
        logger.info("workspace_root_opened workspace_id=%s", spec.workspace_id)

    def close(self):
        """Release the root descriptor idempotently without modifying repository contents."""
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None
            logger.info("workspace_root_closed workspace_id=%s", self.spec.workspace_id)

    def validate_root(self):
        """Reject closed handles or a replaced/moved configured root before any target admission."""
        if self.fd is None:
            raise WorkspaceAccessError("workspace_closed", 503)
        current = open_root(self.spec)
        try:
            info = os.fstat(current)
            if (info.st_dev, info.st_ino) != (
                self.identity.st_dev,
                self.identity.st_ino,
            ):
                raise WorkspaceAccessError("workspace_root_changed", 409)
        finally:
            os.close(current)

    @contextmanager
    def _entry(self, relative):
        """Retain an internally validated kernel-scoped entry FD and join it on every exit path."""
        self.validate_root()
        descriptor = None
        try:
            descriptor = open_beneath(self.fd, relative)
            info = os.fstat(descriptor)
            if not (stat.S_ISREG(info.st_mode) or stat.S_ISDIR(info.st_mode)):
                raise WorkspaceAccessError("workspace_entry_unsafe")
            if stat.S_ISREG(info.st_mode) and info.st_nlink != 1:
                raise WorkspaceAccessError("workspace_entry_unsafe")
            logger.info(
                "workspace_entry_admitted workspace_id=%s", self.spec.workspace_id
            )
            yield descriptor
        except OSError:
            raise WorkspaceAccessError("workspace_entry_unavailable") from None
        finally:
            if descriptor is not None:
                os.close(descriptor)
                logger.info(
                    "workspace_entry_closed workspace_id=%s", self.spec.workspace_id
                )

    @contextmanager
    def entry(self, relative):
        """Admit only a clean nonhidden caller path without traversal, links or mount crossings."""
        clean_parts(relative)
        with self._entry(relative) as descriptor:
            yield descriptor

    def discover(self):
        """Classify only the root's git marker without reading pointers, configs, hooks or parent repositories."""
        self.validate_root()
        try:
            with self._entry(".git") as descriptor:
                marker = (
                    "git_directory"
                    if stat.S_ISDIR(os.fstat(descriptor).st_mode)
                    else "git_pointer_unresolved"
                )
        except WorkspaceAccessError as error:
            if error.code != "workspace_entry_unavailable":
                raise
            # Distinguish an absent marker without following links or reading its content.
            try:
                os.stat(".git", dir_fd=self.fd, follow_symlinks=False)
            except FileNotFoundError:
                marker = "directory"
            except OSError:
                raise WorkspaceAccessError("workspace_repository_unsafe") from None
            else:
                raise WorkspaceAccessError("workspace_repository_unsafe") from None
        logger.info(
            "workspace_discovered workspace_id=%s kind=%s",
            self.spec.workspace_id,
            marker,
        )
        return dict(
            workspace_id=str(self.spec.workspace_id),
            name=self.spec.name,
            repository_kind=marker,
            read_only=True,
        )


class WorkspaceCatalog:
    """Authorize explicit per-owner workspace UUIDs before filesystem capability creation."""

    def __init__(self, specifications=()):
        """Validate a bounded immutable explicit catalog with no cwd inference or startup opens."""
        if (
            not isinstance(specifications, (list, tuple))
            or len(specifications) > MAX_WORKSPACES
        ):
            raise WorkspaceAccessError("workspace_catalog_invalid", 422)
        if any(not isinstance(spec, WorkspaceSpec) for spec in specifications):
            raise WorkspaceAccessError("workspace_catalog_invalid", 422)
        identifiers = [spec.workspace_id for spec in specifications]
        if len(identifiers) != len(set(identifiers)):
            raise WorkspaceAccessError("workspace_catalog_invalid", 422)
        self.specifications = tuple(specifications)
        logger.info("workspace_catalog_created count=%d", len(self.specifications))

    @contextmanager
    def open(self, owner_id, workspace_id):
        """Authorize exact typed identities before opening one configured root, then always release it."""
        spec = next(
            (
                item
                for item in self.specifications
                if item.owner_id == owner_id and item.workspace_id == workspace_id
            ),
            None,
        )
        if spec is None:
            raise WorkspaceAccessError("workspace_not_found")
        workspace = ReadonlyWorkspace(spec)
        try:
            yield workspace
        finally:
            workspace.close()
