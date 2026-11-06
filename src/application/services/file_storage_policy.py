"""Define executable Day 16 upload policy contracts without persistence or filesystem writes."""

import hashlib
import json
import logging
import re
import unicodedata
from dataclasses import dataclass, fields
from types import MappingProxyType
from uuid import UUID

logger = logging.getLogger(__name__)
MIB = 1024 * 1024
GIB = 1024 * MIB
MEDIA_BY_EXTENSION = MappingProxyType(
    {
        "pdf": frozenset({"application/pdf"}),
        "docx": frozenset(
            {"application/vnd.openxmlformats-officedocument.wordprocessingml.document"}
        ),
        "xlsx": frozenset(
            {"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}
        ),
        "txt": frozenset({"text/plain"}),
        "md": frozenset({"text/plain", "text/markdown"}),
        "csv": frozenset({"text/plain", "text/csv"}),
        "png": frozenset({"image/png"}),
        "jpg": frozenset({"image/jpeg"}),
        "jpeg": frozenset({"image/jpeg"}),
        "webp": frozenset({"image/webp"}),
    }
)
RESERVED_NAMES = frozenset(
    {
        "CON",
        "PRN",
        "AUX",
        "NUL",
        *(f"COM{number}" for number in range(1, 10)),
        *(f"LPT{number}" for number in range(1, 10)),
    }
)


class StoragePolicyError(Exception):
    """Report stable file-policy failures without including untrusted names or paths."""

    def __init__(self, code: str, status_code: int):
        """Attach a safe machine code and proposed HTTP status to policy rejection."""
        super().__init__(code)
        self.code = code
        self.status_code = status_code
        logger.warning("file_policy_rejected code=%s status=%d", code, status_code)


@dataclass(frozen=True, slots=True)
class StoragePolicy:
    """Bound upload allocation, concurrency, stream lifetime and archive expansion."""

    max_metadata_bytes: int = 8 * 1024
    max_file_bytes: int = 25 * MIB
    owner_bytes: int = GIB
    global_bytes: int = 10 * GIB
    owner_files: int = 1000
    global_files: int = 10000
    owner_uploads: int = 2
    global_uploads: int = 4
    min_free_bytes: int = 2 * GIB
    chunk_bytes: int = 64 * 1024
    reservation_seconds: int = 300
    upload_seconds: int = 300
    idle_seconds: int = 30
    lease_seconds: int = 60
    heartbeat_seconds: int = 15
    max_archive_bytes: int = 100 * MIB
    max_archive_entries: int = 1000
    max_archive_ratio: int = 100

    def __post_init__(self):
        """Reject inconsistent or non-integer limits before they can admit a reservation."""
        if any(
            type(getattr(self, item.name)) is not int or getattr(self, item.name) <= 0
            for item in fields(self)
        ):
            raise ValueError("Storage limits must be positive integers")
        if not self.max_file_bytes <= self.owner_bytes <= self.global_bytes:
            raise ValueError("File and owner byte limits must fit the global limit")
        if (
            self.owner_files > self.global_files
            or self.owner_uploads > self.global_uploads
        ):
            raise ValueError("Owner limits must fit their global limits")
        if (
            not self.heartbeat_seconds < self.lease_seconds <= self.upload_seconds
            or self.idle_seconds > self.upload_seconds
        ):
            raise ValueError("Upload heartbeat and deadlines are inconsistent")
        if self.chunk_bytes > self.max_file_bytes:
            raise ValueError("Stream chunks must fit the file size cap")


DEFAULT_POLICY = StoragePolicy()


@dataclass(frozen=True, slots=True)
class UsageSnapshot:
    """Represent allocated resources that include staged, ready and pending-purge files."""

    allocated_bytes: int = 0
    allocated_files: int = 0
    active_uploads: int = 0

    def __post_init__(self):
        """Reject corrupt counters rather than treating unknown usage as available capacity."""
        if any(
            type(getattr(self, item.name)) is not int or getattr(self, item.name) < 0
            for item in fields(self)
        ):
            raise ValueError("Usage counters must be nonnegative integers")
        if (
            self.active_uploads > self.allocated_files
            or self.allocated_bytes < self.allocated_files
            or (self.allocated_files == 0 and self.allocated_bytes != 0)
        ):
            raise ValueError("Usage allocation counters are inconsistent")


@dataclass(frozen=True, slots=True)
class FileReservationPlan:
    """Carry validated metadata and internal key derivation for a future atomic reservation."""

    owner_id: UUID
    file_id: UUID
    display_name: str
    size_bytes: int
    expected_sha256: str
    request_key: str | None
    storage_key: str
    fingerprint: str


def normalize_filename(value: str) -> str:
    """Validate a display label while refusing path syntax and ambiguous portable names."""
    if not isinstance(value, str):
        raise StoragePolicyError("invalid_filename", 422)
    name = unicodedata.normalize("NFC", value)
    if not name or name != name.strip() or name.startswith(".") or name.endswith("."):
        raise StoragePolicyError("invalid_filename", 422)
    if any(
        character in '/\\:%*?"<>|' or unicodedata.category(character).startswith("C")
        for character in name
    ):
        raise StoragePolicyError("invalid_filename", 422)
    if (
        len(name.encode("utf-8")) > 255
        or name.split(".", 1)[0].upper() in RESERVED_NAMES
    ):
        raise StoragePolicyError("invalid_filename", 422)
    if name.rsplit(".", 1)[-1].lower() not in MEDIA_BY_EXTENSION or "." not in name:
        raise StoragePolicyError("unsupported_file_type", 415)
    return name


def validate_size(size_bytes: int, policy: StoragePolicy = DEFAULT_POLICY) -> None:
    """Reject empty, malformed or oversized declarations before body streaming begins."""
    if type(size_bytes) is not int or size_bytes <= 0:
        raise StoragePolicyError("invalid_file_size", 422)
    if size_bytes > policy.max_file_bytes:
        raise StoragePolicyError("file_too_large", 413)


def storage_key(owner_id: UUID, file_id: UUID) -> str:
    """Derive an owner-prefixed relative blob key exclusively from server-side UUID values."""
    if not isinstance(owner_id, UUID) or not isinstance(file_id, UUID):
        raise StoragePolicyError("invalid_storage_identity", 422)
    return f"objects/{owner_id}/{file_id.hex[:2]}/{file_id}.blob"


def plan_reservation(
    *,
    owner_id: UUID,
    file_id: UUID,
    filename: str,
    size_bytes: int,
    expected_sha256: str,
    request_key: str | None = None,
    policy: StoragePolicy = DEFAULT_POLICY,
) -> FileReservationPlan:
    """Validate reservation metadata and compute a stable owner-scoped replay fingerprint."""
    key = storage_key(owner_id, file_id)
    name = normalize_filename(filename)
    validate_size(size_bytes, policy)
    if (
        not isinstance(expected_sha256, str)
        or re.fullmatch("[0-9a-fA-F]{64}", expected_sha256) is None
    ):
        raise StoragePolicyError("invalid_sha256", 422)
    if request_key is not None and (
        not isinstance(request_key, str)
        or not 1 <= len(request_key) <= 128
        or any(not 33 <= ord(character) <= 126 for character in request_key)
    ):
        raise StoragePolicyError("invalid_request_key", 422)
    digest = expected_sha256.lower()
    payload = {
        "version": 1,
        "owner_id": str(owner_id),
        "display_name": name,
        "size_bytes": size_bytes,
        "expected_sha256": digest,
    }
    fingerprint = hashlib.sha256(
        json.dumps(
            payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode()
    ).hexdigest()
    logger.info(
        "file_reservation_planned owner_id=%s file_id=%s size_bytes=%d",
        owner_id,
        file_id,
        size_bytes,
    )
    return FileReservationPlan(
        owner_id, file_id, name, size_bytes, digest, request_key, key, fingerprint
    )


def check_capacity(
    *,
    size_bytes: int,
    owner: UsageSnapshot,
    global_usage: UsageSnapshot,
    free_bytes: int,
    policy: StoragePolicy = DEFAULT_POLICY,
) -> None:
    """Check snapshot bounds; callers must lock usage rows and reserve atomically in D17."""
    validate_size(size_bytes, policy)
    if type(free_bytes) is not int or free_bytes < 0:
        raise StoragePolicyError("invalid_disk_capacity", 507)
    if any(
        getattr(owner, item.name) > getattr(global_usage, item.name)
        for item in fields(owner)
    ):
        raise StoragePolicyError("invalid_usage_snapshot", 507)
    if (
        owner.active_uploads >= policy.owner_uploads
        or global_usage.active_uploads >= policy.global_uploads
    ):
        raise StoragePolicyError("upload_concurrency_exceeded", 429)
    if (
        owner.allocated_files >= policy.owner_files
        or owner.allocated_bytes + size_bytes > policy.owner_bytes
    ):
        raise StoragePolicyError("owner_quota_exceeded", 413)
    if (
        global_usage.allocated_files >= policy.global_files
        or global_usage.allocated_bytes + size_bytes > policy.global_bytes
    ):
        raise StoragePolicyError("global_quota_exceeded", 507)
    if free_bytes - size_bytes < policy.min_free_bytes:
        raise StoragePolicyError("insufficient_disk_space", 507)
    logger.info("file_capacity_snapshot_accepted size_bytes=%d", size_bytes)


def validate_detected_media(
    filename: str, detected_media: str, *, declared_media: str | None = None
) -> None:
    """Require an internal verifier's canonical media type to agree with the allowed extension."""
    name = normalize_filename(filename)
    allowed = MEDIA_BY_EXTENSION[name.rsplit(".", 1)[-1].lower()]
    if not isinstance(detected_media, str) or detected_media.lower() not in allowed:
        raise StoragePolicyError("file_type_mismatch", 415)
    if declared_media is not None:
        if not isinstance(declared_media, str):
            raise StoragePolicyError("file_type_mismatch", 415)
        declared = declared_media.partition(";")[0].strip().lower()
        if declared != "application/octet-stream" and declared not in allowed:
            raise StoragePolicyError("file_type_mismatch", 415)
    logger.info("file_media_contract_accepted media_type=%s", detected_media.lower())


def validate_archive_bounds(
    *,
    entries: int,
    compressed_bytes: int,
    expanded_bytes: int,
    policy: StoragePolicy = DEFAULT_POLICY,
) -> None:
    """Reject declared archive expansion that exceeds entry, total-byte or ratio limits."""
    if any(
        type(value) is not int or value < 0
        for value in (entries, compressed_bytes, expanded_bytes)
    ):
        raise StoragePolicyError("invalid_archive_totals", 422)
    if (
        entries > policy.max_archive_entries
        or expanded_bytes > policy.max_archive_bytes
        or expanded_bytes > compressed_bytes * policy.max_archive_ratio
    ):
        raise StoragePolicyError("archive_limits_exceeded", 413)
    logger.info(
        "file_archive_bounds_accepted entries=%d expanded_bytes=%d",
        entries,
        expanded_bytes,
    )
