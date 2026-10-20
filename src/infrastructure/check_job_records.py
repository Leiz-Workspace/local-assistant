"""Encode strict bounded check-job context, concrete approval reviews and truthful private native observation journals."""

import base64
import hashlib
import json
import logging
import math
import re
import stat
from uuid import UUID

from src.application.services.check_policy import (
    DIGEST,
    MAX_RECORD_BYTES,
    MAX_STDERR,
    MAX_STDOUT,
    PROFILES,
    execution_policy,
    selection_input,
)
from src.application.services.workspace_policy import WorkspaceAccessError
from src.infrastructure.check_runtime_io import decode_manifest

logger = logging.getLogger(__name__)
CORE_FIELDS = frozenset(
    {
        "description",
        "version",
        "job_id",
        "owner_id",
        "workspace_id",
        "profile",
        "source",
        "runtime",
        "snapshot",
        "private_root",
        "policy",
        "created_at_utc",
    }
)
SOURCE_FIELDS = frozenset(
    {
        "description",
        "version",
        "owner_id",
        "workspace_id",
        "profile",
        "root",
        "files",
        "total_bytes",
        "source_version",
    }
)
RUNTIME_FIELDS = frozenset(
    {
        "manifest_sha256",
        "native_version",
        "python_sha256",
        "ruff_sha256",
        "files",
        "allocated_bytes",
    }
)
STATES = frozenset(
    {"captured", "proposed", "starting", "observed", "failed", "cancelled", "expired"}
)


def encode_record(value):
    """Encode complete bounded canonical job/review/journal data without truncating source or action authority."""
    raw = json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    if len(raw) > MAX_RECORD_BYTES:
        raise WorkspaceAccessError("checks_record_limit", 413)
    return raw


def decode_record(raw):
    """Decode strict duplicate-free finite bounded private job JSON with stable audit-safe error codes."""
    try:
        return decode_manifest(raw, MAX_RECORD_BYTES)
    except WorkspaceAccessError:
        raise WorkspaceAccessError("checks_record_invalid", 503) from None


def sha256(raw):
    """Bind exact private canonical bytes independently of filenames, child output markers or caller digests."""
    return hashlib.sha256(raw).hexdigest()


def require_uuid(value):
    """Require one canonical persisted UUID string rather than accepting ambiguous or implicitly converted identity values."""
    if type(value) is not str or str(UUID(value)) != value:
        raise ValueError()


def native_values(value, length):
    """Require exact integer native metadata arrays and reject bool-as-integer private context corruption."""
    if (
        type(value) is not list
        or len(value) != length
        or any(type(item) is not int for item in value)
    ):
        raise ValueError()


def validate_core(core, identifier):
    """Validate complete source/runtime/private snapshot/policy scope before trusting a stored job or reconstructing its review."""
    try:
        if (
            type(core) is not dict
            or set(core) != CORE_FIELDS
            or core["job_id"] != str(identifier)
            or type(core["version"]) is not int
            or core["version"] != 1
            or type(core["description"]) is not str
            or len(core["description"]) > 256
        ):
            raise ValueError()
        for name in ("job_id", "owner_id", "workspace_id"):
            require_uuid(core[name])
        source = core["source"]
        if (
            type(source) is not dict
            or set(source) != SOURCE_FIELDS
            or type(source["version"]) is not int
            or source["version"] != 1
            or source["owner_id"] != core["owner_id"]
            or source["workspace_id"] != core["workspace_id"]
            or source["profile"] != core["profile"]
            or type(source["files"]) is not list
            or type(source["description"]) is not str
            or len(source["description"]) > 256
        ):
            raise ValueError()
        selected = [
            {"path": item["path"], "expected_sha256": item["sha256"]}
            for item in source["files"]
        ]
        selection_input(core["profile"], selected)
        native_values(source["root"], 5)
        total = 0
        source_files = {}
        for item in source["files"]:
            if (
                type(item) is not dict
                or set(item) != {"path", "sha256", "size", "native", "parent"}
                or type(item["size"]) is not int
                or not 0 <= item["size"] <= 8192
            ):
                raise ValueError()
            native_values(item["native"], 7)
            native_values(item["parent"], 5)
            if item["native"][3] != 1 or item["native"][4] != item["size"]:
                raise ValueError()
            if (
                stat.S_IFMT(item["native"][2]) != stat.S_IFREG
                or stat.S_IFMT(item["parent"][2]) != stat.S_IFDIR
            ):
                raise ValueError()
            total += item["size"]
            source_files[item["path"]] = item
        if (
            type(source["total_bytes"]) is not int
            or source["total_bytes"] != total
            or total > 131072
            or type(source["source_version"]) is not str
            or not DIGEST.fullmatch(source["source_version"])
        ):
            raise ValueError()
        original = {
            key: value for key, value in source.items() if key != "source_version"
        }
        if sha256(encode_record(original)) != source["source_version"]:
            raise ValueError()
        runtime = core["runtime"]
        if type(runtime) is not dict or set(runtime) != RUNTIME_FIELDS:
            raise ValueError()
        for name in (
            "manifest_sha256",
            "native_version",
            "python_sha256",
            "ruff_sha256",
        ):
            if type(runtime[name]) is not str or not DIGEST.fullmatch(runtime[name]):
                raise ValueError()
        if (
            type(runtime["files"]) is not int
            or not 1 <= runtime["files"] <= 800
            or type(runtime["allocated_bytes"]) is not int
            or not 0 <= runtime["allocated_bytes"] <= 67108864
        ):
            raise ValueError()
        native_values(core["private_root"], 2)
        snapshot = core["snapshot"]
        if (
            type(snapshot) is not dict
            or set(snapshot) != {"files", "directories"}
            or type(snapshot["files"]) is not dict
            or type(snapshot["directories"]) is not dict
            or set(snapshot["files"]) != set(source_files)
        ):
            raise ValueError()
        directories = {""}
        for path, source_item in source_files.items():
            parts = path.split("/")
            directories.update(
                "/".join(parts[:index]) for index in range(1, len(parts))
            )
            item = snapshot["files"][path]
            if (
                type(item) is not dict
                or set(item) != {"sha256", "size", "native"}
                or item["sha256"] != source_item["sha256"]
                or type(item["size"]) is not int
                or item["size"] != source_item["size"]
            ):
                raise ValueError()
            native_values(item["native"], 7)
            if item["native"][3] != 1 or item["native"][4] != item["size"]:
                raise ValueError()
            if item["native"][2] != stat.S_IFREG | 0o600:
                raise ValueError()
        if set(snapshot["directories"]) != directories:
            raise ValueError()
        for value in snapshot["directories"].values():
            native_values(value, 7)
            if value[2] != stat.S_IFDIR | 0o700:
                raise ValueError()
        policy = core["policy"]
        if (
            type(policy) is not dict
            or type(policy.get("cpu_affinity")) is not list
            or len(policy["cpu_affinity"]) != 1
            or encode_record(policy)
            != encode_record(execution_policy(policy["cpu_affinity"][0]))
        ):
            raise ValueError()
        if (
            type(core["created_at_utc"]) is not str
            or not 1 <= len(core["created_at_utc"]) <= 64
        ):
            raise ValueError()
        encode_record(core)
    except (ValueError, TypeError, KeyError, OverflowError, WorkspaceAccessError):
        raise WorkspaceAccessError("checks_job_manifest_invalid", 503) from None
    logger.info("checks_job_scope_verified job_id=%s", identifier)
    return core


def review_artifact(core):
    """Build the complete concrete owner review with opaque native context binding and fixed executable/resources, never raw host paths."""
    validate_core(core, UUID(core["job_id"]))
    return encode_record(
        dict(
            description="Run one selected readonly Python snapshot with a fixed isolated test/lint profile; output is untrusted and grants no source edit.",
            job_id=core["job_id"],
            owner_id=core["owner_id"],
            workspace_id=core["workspace_id"],
            context_sha256=sha256(encode_record(core)),
            profile=core["profile"],
            argv=list(PROFILES[core["profile"]].argv),
            selected_files=[
                dict(path=item["path"], sha256=item["sha256"], size=item["size"])
                for item in core["source"]["files"]
            ],
            source_version=core["source"]["source_version"],
            runtime=core["runtime"],
            policy=core["policy"],
        )
    )


def validate_observation(value, core):
    """Validate bounded exact native result bytes without interpreting a child marker or exit zero as functional quality authority."""
    required = {
        "description",
        "job_id",
        "profile",
        "started_acknowledged",
        "outcome",
        "exit_code",
        "elapsed_seconds",
        "stdout_base64",
        "stderr_base64",
        "stdout_bytes",
        "stderr_bytes",
        "stdout_sha256",
        "stderr_sha256",
        "stdout_complete",
        "stderr_complete",
        "output_encoding",
        "output_is_untrusted",
        "quality_evaluated",
        "host_source_write_capability",
        "cleanup_uncertain",
        "policy",
    }
    if (
        type(value) is not dict
        or set(value) != required
        or value["job_id"] != core["job_id"]
        or value["profile"] != core["profile"]
        or value["output_encoding"] != "base64"
        or value["output_is_untrusted"] is not True
        or value["quality_evaluated"] is not False
        or value["host_source_write_capability"] is not False
        or encode_record(value["policy"]) != encode_record(core["policy"])
    ):
        raise ValueError()
    if (
        type(value["description"]) is not str
        or len(value["description"]) > 256
        or type(value["elapsed_seconds"]) not in {int, float}
        or not math.isfinite(value["elapsed_seconds"])
        or value["elapsed_seconds"] < 0
    ):
        raise ValueError()
    for name in (
        "started_acknowledged",
        "stdout_complete",
        "stderr_complete",
        "cleanup_uncertain",
    ):
        if type(value[name]) is not bool:
            raise ValueError()
    if value["exit_code"] is not None and (
        type(value["exit_code"]) is not int or not -127 <= value["exit_code"] <= 255
    ):
        raise ValueError()
    if (
        value["outcome"]
        not in {
            "not_started",
            "supervisor_failed",
            "cancelled",
            "wall_timeout",
            "stdout_limit",
            "stderr_limit",
            "exited",
        }
        or (
            value["outcome"] == "exited"
            and (not value["started_acknowledged"] or value["exit_code"] is None)
        )
        or (not value["started_acknowledged"] and value["exit_code"] is not None)
    ):
        raise ValueError()
    for name, limit in (("stdout", MAX_STDOUT), ("stderr", MAX_STDERR)):
        encoded = value[name + "_base64"]
        if (
            type(encoded) is not str
            or len(encoded) > ((limit + 2) // 3) * 4
            or type(value[name + "_bytes"]) is not int
        ):
            raise ValueError()
        raw = base64.b64decode(encoded, validate=True)
        if (
            len(raw) > limit
            or len(raw) != value[name + "_bytes"]
            or sha256(raw) != value[name + "_sha256"]
            or base64.b64encode(raw).decode("ascii") != encoded
        ):
            raise ValueError()
    encode_record(value)


def validate_journal(value, core, manifest_sha256):
    """Bind every private journal to its exact manifest/job/grant and reject fake quality, malformed output or unknown state."""
    try:
        if (
            type(value) is not dict
            or set(value)
            != {
                "description",
                "job_id",
                "manifest_sha256",
                "state",
                "approval_id",
                "observation",
                "error_code",
            }
            or value["job_id"] != core["job_id"]
            or value["manifest_sha256"] != manifest_sha256
            or type(value["state"]) is not str
            or value["state"] not in STATES
            or type(value["description"]) is not str
            or len(value["description"]) > 256
        ):
            raise ValueError()
        if value["approval_id"] is not None:
            require_uuid(value["approval_id"])
        if (
            value["state"] in {"proposed", "starting", "observed"}
            and value["approval_id"] is None
        ):
            raise ValueError()
        if value["error_code"] is not None and (
            type(value["error_code"]) is not str
            or not re.fullmatch(r"[a-z0-9_]{1,128}", value["error_code"])
        ):
            raise ValueError()
        if value["observation"] is not None:
            validate_observation(value["observation"], core)
        if (
            value["state"] in {"captured", "proposed", "starting"}
            and value["observation"] is not None
        ):
            raise ValueError()
        if value["state"] == "observed" and value["observation"] is None:
            raise ValueError()
        encode_record(value)
    except (ValueError, TypeError, KeyError, OverflowError, WorkspaceAccessError):
        raise WorkspaceAccessError("checks_job_journal_invalid", 503) from None
    return value
