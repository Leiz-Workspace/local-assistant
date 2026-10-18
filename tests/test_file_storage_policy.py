"""Test Day 16 policy boundaries, replay identity, safe key derivation and private audit logs."""

import logging
from dataclasses import replace
from pathlib import PurePosixPath
from uuid import uuid4

import pytest

from src.application.services.file_storage_policy import (
    DEFAULT_POLICY,
    GIB,
    MEDIA_BY_EXTENSION,
    MIB,
    StoragePolicyError,
    UsageSnapshot,
    check_capacity,
    normalize_filename,
    plan_reservation,
    storage_key,
    validate_archive_bounds,
    validate_detected_media,
    validate_size,
)


@pytest.mark.parametrize(
    "name",
    [
        "../secret.pdf",
        "/etc/passwd.pdf",
        "C:\\secret.pdf",
        "a/b.txt",
        "a%2fb.pdf",
        "a:stream.txt",
        ".env",
        " report.pdf",
        "report.pdf ",
        "report.pdf.",
        "CON.txt",
        "lpt1.pdf",
        "bad\x00.pdf",
        "bad\n.pdf",
        "bad\u202e.pdf",
        "\ud800.pdf",
        "a" * 252 + ".pdf",
    ],
)
def test_unsafe_labels_rejected(name):
    """Reject path/encoding/control/portable-name ambiguity without using labels as disk keys."""
    with pytest.raises(StoragePolicyError) as error:
        normalize_filename(name)
    assert error.value.code == "invalid_filename"


@pytest.mark.parametrize(
    "name",
    [
        "payload.exe",
        "active.html",
        "image.svg",
        "macro.docm",
        "macro.xlsm",
        "bundle.zip",
        "no-extension",
        "movie.mp4",
    ],
)
def test_unsupported_types_rejected(name):
    """Keep executable, generic archive, macro and future media types out of the V1 allowlist."""
    with pytest.raises(StoragePolicyError) as error:
        normalize_filename(name)
    assert error.value.status_code == 415


def test_names_are_normalized_and_fingerprints_ignore_generated_ids():
    """Match equivalent retry metadata while keeping file IDs and opaque request keys separate."""
    owner = uuid4()
    values = {
        "owner_id": owner,
        "filename": "Ba\u0301o ca\u0301o.PDF",
        "size_bytes": 1,
        "expected_sha256": "A" * 64,
    }
    first = plan_reservation(file_id=uuid4(), request_key="first", **values)
    second = plan_reservation(file_id=uuid4(), request_key="other", **values)
    assert first.display_name == "Báo cáo.PDF"
    assert first.expected_sha256 == "a" * 64
    assert first.fingerprint == second.fingerprint
    assert first.storage_key != second.storage_key
    assert PurePosixPath(first.storage_key).parts[:2] == ("objects", str(owner))
    assert ".." not in PurePosixPath(first.storage_key).parts
    assert first.display_name not in first.storage_key
    changed = plan_reservation(file_id=uuid4(), **{**values, "owner_id": uuid4()})
    assert changed.fingerprint != first.fingerprint
    changed = plan_reservation(file_id=uuid4(), **{**values, "size_bytes": 2})
    assert changed.fingerprint != first.fingerprint


@pytest.mark.parametrize("key", ["", "a b", "x" * 129, "private\nkey", "khóa"])
def test_invalid_idempotency_keys(key):
    """Reject ambiguous or control-bearing request keys before metadata reservation."""
    with pytest.raises(StoragePolicyError) as error:
        plan_reservation(
            owner_id=uuid4(),
            file_id=uuid4(),
            filename="file.pdf",
            size_bytes=1,
            expected_sha256="a" * 64,
            request_key=key,
        )
    assert error.value.code == "invalid_request_key"


@pytest.mark.parametrize("digest", ["", "a" * 63, "g" * 64, None])
def test_invalid_digests(digest):
    """Require a full SHA-256 declaration without accepting a truncated or malformed digest."""
    with pytest.raises(StoragePolicyError) as error:
        plan_reservation(
            owner_id=uuid4(),
            file_id=uuid4(),
            filename="file.pdf",
            size_bytes=1,
            expected_sha256=digest,
        )
    assert error.value.code == "invalid_sha256"


@pytest.mark.parametrize("size", [0, -1, True, 1.5, "1"])
def test_invalid_sizes(size):
    """Keep malformed/empty declarations out of quota calculations."""
    with pytest.raises(StoragePolicyError) as error:
        validate_size(size)
    assert error.value.code == "invalid_file_size"


def test_file_size_boundary():
    """Accept exactly the configured byte cap and reject the first byte beyond it."""
    validate_size(25 * MIB)
    with pytest.raises(StoragePolicyError) as error:
        validate_size(25 * MIB + 1)
    assert error.value.status_code == 413


@pytest.mark.parametrize(
    "changes",
    [
        {"owner_bytes": MIB},
        {"global_files": 1},
        {"global_uploads": 1},
        {"heartbeat_seconds": 60},
        {"chunk_bytes": 30 * MIB},
        {"owner_uploads": True},
    ],
)
def test_inconsistent_policy_rejected(changes):
    """Fail invalid configuration instead of silently changing enforcement bounds."""
    with pytest.raises(ValueError):
        replace(DEFAULT_POLICY, **changes)


@pytest.mark.parametrize(
    "changes",
    [{"allocated_bytes": -1}, {"allocated_files": True}, {"active_uploads": 0.5}],
)
def test_invalid_usage_snapshots(changes):
    """Reject corrupt usage snapshots rather than allowing excess allocation."""
    with pytest.raises(ValueError):
        UsageSnapshot(**changes)


def test_quota_and_free_space_exact_boundary():
    """Allow the last permitted reservation while including pending/purge allocations."""
    check_capacity(
        size_bytes=1,
        owner=UsageSnapshot(GIB - 1, 999, 1),
        global_usage=UsageSnapshot(10 * GIB - 1, 9999, 3),
        free_bytes=2 * GIB + 1,
    )


@pytest.mark.parametrize(
    "owner,global_usage,free,code,status",
    [
        (
            UsageSnapshot(GIB, 1),
            UsageSnapshot(GIB, 1),
            10 * GIB,
            "owner_quota_exceeded",
            413,
        ),
        (
            UsageSnapshot(1000, 1000),
            UsageSnapshot(1000, 1000),
            10 * GIB,
            "owner_quota_exceeded",
            413,
        ),
        (
            UsageSnapshot(),
            UsageSnapshot(10 * GIB, 1),
            10 * GIB,
            "global_quota_exceeded",
            507,
        ),
        (
            UsageSnapshot(),
            UsageSnapshot(10000, 10000),
            10 * GIB,
            "global_quota_exceeded",
            507,
        ),
        (
            UsageSnapshot(2, 2, 2),
            UsageSnapshot(2, 2, 2),
            10 * GIB,
            "upload_concurrency_exceeded",
            429,
        ),
        (
            UsageSnapshot(),
            UsageSnapshot(4, 4, 4),
            10 * GIB,
            "upload_concurrency_exceeded",
            429,
        ),
        (UsageSnapshot(), UsageSnapshot(), 2 * GIB, "insufficient_disk_space", 507),
        (UsageSnapshot(), UsageSnapshot(), -1, "invalid_disk_capacity", 507),
    ],
)
def test_capacity_rejection(owner, global_usage, free, code, status):
    """Reject each owner/global/concurrency/disk limit with a distinct safe error contract."""
    with pytest.raises(StoragePolicyError) as error:
        check_capacity(
            size_bytes=1, owner=owner, global_usage=global_usage, free_bytes=free
        )
    assert (error.value.code, error.value.status_code) == (code, status)


@pytest.mark.parametrize(
    "extension,media",
    [
        (extension, media)
        for extension, values in MEDIA_BY_EXTENSION.items()
        for media in values
    ],
)
def test_allowed_media_contract(extension, media):
    """Accept canonical verifier media only when it matches the filename's allowed family."""
    validate_detected_media(
        "document." + extension, media, declared_media="application/octet-stream"
    )


@pytest.mark.parametrize(
    "filename,detected,declared",
    [
        ("file.pdf", "image/png", None),
        ("file.docx", "application/zip", None),
        ("file.xlsx", "application/zip", None),
        ("file.png", "image/png", "text/html"),
        ("file.pdf", None, None),
    ],
)
def test_media_spoofing_rejected(filename, detected, declared):
    """Do not promote an extension/header or generic ZIP marker into verified format evidence."""
    with pytest.raises(StoragePolicyError) as error:
        validate_detected_media(filename, detected, declared_media=declared)
    assert error.value.code == "file_type_mismatch"


@pytest.mark.parametrize(
    "changes",
    [
        {"entries": 1001},
        {"expanded_bytes": 100 * MIB + 1},
        {"compressed_bytes": 0, "expanded_bytes": 1},
        {"entries": -1},
    ],
)
def test_archive_bounds(changes):
    """Reject excess entries, expansion, ratio and malformed totals before OOXML verification."""
    values = {"entries": 1000, "compressed_bytes": MIB, "expanded_bytes": 100 * MIB}
    validate_archive_bounds(**values)
    with pytest.raises(StoragePolicyError):
        validate_archive_bounds(**{**values, **changes})


def test_storage_keys_are_owner_scoped_and_require_uuid():
    """Prevent caller-supplied path strings from entering internal key generation."""
    file_id = uuid4()
    assert storage_key(uuid4(), file_id) != storage_key(uuid4(), file_id)
    with pytest.raises(StoragePolicyError):
        storage_key("../escape", file_id)


def test_audit_omits_private_labels_and_keys(caplog):
    """Log decisions and IDs while omitting original names, digests and idempotency secrets."""
    with caplog.at_level(logging.INFO):
        plan_reservation(
            owner_id=uuid4(),
            file_id=uuid4(),
            filename="private-medical-record.pdf",
            size_bytes=1,
            expected_sha256="b" * 64,
            request_key="private-replay-key",
        )
        with pytest.raises(StoragePolicyError):
            normalize_filename("../private-label.pdf")
    assert "file_reservation_planned" in caplog.text
    assert all(
        value not in caplog.text
        for value in (
            "private-medical-record",
            "private-replay-key",
            "private-label",
            "b" * 64,
        )
    )


@pytest.mark.parametrize(
    "changes", [{"active_uploads": 1}, {"allocated_files": 1}, {"allocated_bytes": 1}]
)
def test_inconsistent_allocation_counters(changes):
    """Require nonempty files, bytes and in-flight allocation counts to agree."""
    with pytest.raises(ValueError):
        UsageSnapshot(**changes)


def test_owner_cannot_exceed_global_snapshot():
    """Reject contradictory snapshots before claiming capacity is available."""
    with pytest.raises(StoragePolicyError) as error:
        check_capacity(
            size_bytes=1,
            owner=UsageSnapshot(1, 1),
            global_usage=UsageSnapshot(),
            free_bytes=10 * GIB,
        )
    assert error.value.code == "invalid_usage_snapshot"
