"""Provide one sealed x86_64 thread-only seccomp filter for approved snapshot checks without subprocess budget amplification."""

import errno
import fcntl
import hashlib
import logging
import os
import platform
import struct
import sys
from contextlib import contextmanager

from src.application.services.workspace_policy import WorkspaceAccessError

logger = logging.getLogger(__name__)
INSTRUCTIONS = (
    (0x20, 0, 0, 4),
    (0x15, 1, 0, 0xC000003E),
    (0x06, 0, 0, 0x80000000),
    (0x20, 0, 0, 0),
    (0x45, 0, 1, 0x40000000),
    (0x06, 0, 0, 0x50000 | errno.ENOSYS),
    (0x15, 0, 1, 203),
    (0x06, 0, 0, 0x50000 | errno.EPERM),
    (0x15, 0, 1, 57),
    (0x06, 0, 0, 0x50000 | errno.EPERM),
    (0x15, 0, 1, 58),
    (0x06, 0, 0, 0x50000 | errno.EPERM),
    (0x15, 0, 1, 435),
    (0x06, 0, 0, 0x50000 | errno.ENOSYS),
    (0x15, 0, 4, 56),
    (0x20, 0, 0, 16),
    (0x54, 0, 0, 0x10900),
    (0x15, 1, 0, 0x10900),
    (0x06, 0, 0, 0x50000 | errno.EPERM),
    (0x06, 0, 0, 0x7FFF0000),
)
# Check architecture/x32 before syscall dispatch; clone must share VM, handlers and thread group.
FILTER_BYTES = b"".join(struct.pack("<HBBI", *value) for value in INSTRUCTIONS)
FILTER_SHA256 = hashlib.sha256(FILTER_BYTES).hexdigest()
REQUIRED_SEALS = (
    fcntl.F_SEAL_SHRINK | fcntl.F_SEAL_GROW | fcntl.F_SEAL_WRITE | fcntl.F_SEAL_SEAL
)


@contextmanager
def thread_filter():
    """Own a sealed setup-only filter FD until native work joins, failing closed on unsupported platforms or sealing faults."""
    if sys.platform != "linux" or platform.machine() != "x86_64":
        raise WorkspaceAccessError("checks_seccomp_unsupported", 503)
    descriptor = None
    try:
        try:
            descriptor = os.memfd_create(
                "checks-thread-policy", os.MFD_CLOEXEC | os.MFD_ALLOW_SEALING
            )
            offset = 0
            while offset < len(FILTER_BYTES):
                count = os.write(descriptor, FILTER_BYTES[offset:])
                if count <= 0:
                    raise OSError("checks_filter_write_failed")
                offset += count
            os.lseek(descriptor, 0, os.SEEK_SET)
            fcntl.fcntl(descriptor, fcntl.F_ADD_SEALS, REQUIRED_SEALS)
            if fcntl.fcntl(descriptor, fcntl.F_GET_SEALS) != REQUIRED_SEALS:
                raise OSError("checks_filter_seals_missing")
        except OSError:
            raise WorkspaceAccessError("checks_seccomp_unavailable", 503) from None
        logger.info("checks_thread_filter_prepared")
        yield descriptor
    finally:
        if descriptor is not None:
            os.close(descriptor)
            logger.info("checks_thread_filter_closed")
