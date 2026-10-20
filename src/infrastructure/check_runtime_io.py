"""Copy bounded trusted runtime bytes through native descriptors and verify private immutable capsule metadata without host execution."""

import hashlib
import json
import logging
import os
import stat
from time import monotonic

from src.application.services.workspace_policy import WorkspaceAccessError
from src.infrastructure.readonly_workspace import open_beneath
from src.infrastructure.workspace_reader import fingerprint

logger = logging.getLogger(__name__)


def check_capture(stop, deadline):
    """Refuse cooperative cancellation or elapsed capture budget before another bounded native file stage."""
    if stop.is_set():
        raise WorkspaceAccessError("checks_capture_cancelled", 503)
    if monotonic() >= deadline:
        raise WorkspaceAccessError("checks_capture_timeout", 504)


def private_directory(descriptor, device):
    """Require an owned0700 private directory on the retained filesystem before trusting capsule entries."""
    info = os.fstat(descriptor)
    if (
        not stat.S_ISDIR(info.st_mode)
        or info.st_uid != os.getuid()
        or stat.S_IMODE(info.st_mode) != 0o700
        or info.st_dev != device
    ):
        raise WorkspaceAccessError("checks_runtime_directory_invalid", 503)
    return info


def private_file(descriptor, device, mode):
    """Require one owned private regular inode with the exact captured mode and anchored device."""
    info = os.fstat(descriptor)
    if (
        not stat.S_ISREG(info.st_mode)
        or info.st_uid != os.getuid()
        or info.st_nlink != 1
        or stat.S_IMODE(info.st_mode) != mode
        or info.st_dev != device
    ):
        raise WorkspaceAccessError("checks_runtime_file_invalid", 503)
    return info


def source_info(descriptor, limit, root_owned, *, allow_seed_links=False):
    """Admit only bounded regular trusted source bytes, never symlinks, devices or writable system-runtime files."""
    info = os.fstat(descriptor)
    if (
        not stat.S_ISREG(info.st_mode)
        or (info.st_nlink != 1 and not allow_seed_links)
        or info.st_nlink < 1
        or (allow_seed_links and root_owned)
        or info.st_size > limit
        or info.st_uid not in ({0} if root_owned else {0, os.getuid()})
        or (root_owned and info.st_mode & 0o22)
    ):
        raise WorkspaceAccessError("checks_runtime_source_invalid", 503)
    return info


def hash_source(
    directory, name, limit, stop, deadline, *, root_owned=True, allow_seed_links=False
):
    """Preflight bounded trusted tool bytes before creating a private capsule so a wrong configured digest leaves no partial runtime."""
    check_capture(stop, deadline)
    descriptor = open_beneath(directory, name)
    try:
        before = source_info(
            descriptor, limit, root_owned, allow_seed_links=allow_seed_links
        )
        digest, length = hashlib.sha256(), 0
        while True:
            check_capture(stop, deadline)
            chunk = os.read(descriptor, min(65536, limit + 1 - length))
            if not chunk:
                break
            length += len(chunk)
            if length > limit:
                raise WorkspaceAccessError("checks_runtime_source_limit", 413)
            digest.update(chunk)
        after = source_info(
            descriptor, limit, root_owned, allow_seed_links=allow_seed_links
        )
        if fingerprint(before) != fingerprint(after) or length != before.st_size:
            raise WorkspaceAccessError("checks_runtime_source_changed", 409)
        named = os.stat(name, dir_fd=directory, follow_symlinks=False)
        if fingerprint(named) != fingerprint(after):
            raise WorkspaceAccessError("checks_runtime_source_changed", 409)
        logger.debug("checks_runtime_source_preflighted bytes=%d", length)
        return digest.hexdigest()
    finally:
        os.close(descriptor)


def copy_source(
    source_directory,
    source_name,
    destination,
    destination_name,
    mode,
    limit,
    stop,
    deadline,
    *,
    expected_sha256=None,
    root_owned=True,
    allow_seed_links=False,
):
    """Stream/fsync one fresh private runtime file and preserve incomplete entries on any uncertain capture outcome."""
    if (
        mode not in {0o400, 0o500}
        or type(destination_name) is not str
        or destination_name in {"", ".", ".."}
        or any(value in destination_name for value in ("/", "\\", "\x00"))
        or (allow_seed_links and (root_owned or expected_sha256 is None))
    ):
        raise WorkspaceAccessError("checks_runtime_mode_invalid", 503)
    check_capture(stop, deadline)
    private_directory(destination, os.fstat(destination).st_dev)
    source = open_beneath(source_directory, source_name)
    target = None
    try:
        before = source_info(
            source, limit, root_owned, allow_seed_links=allow_seed_links
        )
        target = os.open(
            destination_name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
            0o600,
            dir_fd=destination,
        )
        private_file(target, os.fstat(destination).st_dev, 0o600)
        digest, length = hashlib.sha256(), 0
        while True:
            check_capture(stop, deadline)
            chunk = os.read(source, min(65536, limit + 1 - length))
            if not chunk:
                break
            length += len(chunk)
            if length > limit:
                raise WorkspaceAccessError("checks_runtime_source_limit", 413)
            digest.update(chunk)
            offset = 0
            while offset < len(chunk):
                check_capture(stop, deadline)
                count = os.write(target, chunk[offset:])
                if count <= 0:
                    raise OSError("checks_runtime_write_stalled")
                offset += count
        after = source_info(
            source, limit, root_owned, allow_seed_links=allow_seed_links
        )
        named = os.stat(source_name, dir_fd=source_directory, follow_symlinks=False)
        if (
            length != before.st_size
            or fingerprint(before) != fingerprint(after)
            or fingerprint(named) != fingerprint(after)
        ):
            raise WorkspaceAccessError("checks_runtime_source_changed", 409)
        sha = digest.hexdigest()
        if expected_sha256 is not None and sha != expected_sha256:
            raise WorkspaceAccessError("checks_runtime_digest_mismatch", 409)
        os.fchmod(target, mode)
        os.fsync(target)
        private_file(target, os.fstat(destination).st_dev, mode)
        os.fsync(destination)
        logger.debug("checks_runtime_file_captured bytes=%d", length)
        return dict(sha256=sha, size=length, mode=mode)
    finally:
        try:
            if target is not None:
                os.close(target)
        finally:
            os.close(source)


def read_private(directory, name, limit, device, *, mode=0o400):
    """Read exact bounded private metadata/content under inode/size/time fences without following links."""
    descriptor = open_beneath(directory, name)
    try:
        before = private_file(descriptor, device, mode)
        if before.st_size > limit:
            raise WorkspaceAccessError("checks_runtime_metadata_limit", 413)
        raw = bytearray()
        while len(raw) <= limit:
            chunk = os.read(descriptor, min(65536, limit + 1 - len(raw)))
            if not chunk:
                break
            raw.extend(chunk)
        after = private_file(descriptor, device, mode)
        named = os.stat(name, dir_fd=directory, follow_symlinks=False)
        if (
            len(raw) > limit
            or len(raw) != before.st_size
            or fingerprint(before) != fingerprint(after)
            or fingerprint(named) != fingerprint(after)
        ):
            raise WorkspaceAccessError("checks_runtime_file_changed", 409)
        logger.debug("checks_runtime_private_bytes_verified bytes=%d", len(raw))
        return bytes(raw), fingerprint(after)
    finally:
        os.close(descriptor)


def canonical_manifest(value, limit):
    """Encode one finite canonical bounded runtime manifest without accepting nonfinite or implicit values."""
    raw = json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    if len(raw) > limit:
        raise WorkspaceAccessError("checks_runtime_metadata_limit", 413)
    logger.debug("checks_runtime_manifest_encoded bytes=%d", len(raw))
    return raw


def decode_manifest(raw, limit):
    """Reject duplicate/nonfinite/malformed runtime metadata before using its file inventory as authority."""

    def pairs(items):
        """Require unique canonical object keys rather than accepting ambiguous runtime entries."""
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError()
            result[key] = value
        return result

    def constant(value):
        """Reject all nonfinite JSON tokens without preserving untrusted private diagnostics."""
        raise ValueError()

    try:
        if type(raw) is not bytes or len(raw) > limit:
            raise ValueError()
        value = json.loads(raw, object_pairs_hook=pairs, parse_constant=constant)
        if type(value) is not dict:
            raise ValueError()
        return value
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise WorkspaceAccessError("checks_runtime_manifest_invalid", 503) from None
