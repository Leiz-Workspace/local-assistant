"""Persist signed bounded run metadata in a private locked directory without retaining execution authority or raw text."""

import fcntl
import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import stat
from pathlib import Path
from uuid import UUID, uuid4

LOGGER = logging.getLogger(__name__)
STATES = {"created", "running", "succeeded", "failed", "cancelled", "interrupted"}
ERRORS = {
    None,
    "run_failed",
    "run_timeout",
    "skill_revoked",
    "history_unavailable",
    "restart_interrupted",
}


class HistoryError(Exception):
    """Expose one finite metadata-storage failure without filesystem paths or sensitive contents."""


def encoded(value):
    """Serialize finite metadata canonically for hashing and signing without NaN or arbitrary objects."""
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()


def unique_object(pairs):
    """Reject duplicate signed fields instead of accepting an ambiguous record."""
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate_field")
        value[key] = item
    return value


def validate_record(row):
    """Require exact bounded metadata fields and reject every prompt, result body or recovered authority field."""
    if (
        type(row) is not dict
        or set(row)
        != {
            "schema_version",
            "id",
            "owner_id",
            "workspace_id",
            "state",
            "events",
            "request_sha256",
            "result_sha256",
            "context_sha256",
            "error_code",
        }
        or type(row["schema_version"]) is not int
        or row["schema_version"] != 1
    ):
        raise ValueError("invalid_record")
    for key in ("id", "owner_id", "workspace_id"):
        if type(row[key]) is not str or str(UUID(row[key])) != row[key]:
            raise ValueError("invalid_identity")
    if (
        type(row["state"]) is not str
        or row["state"] not in STATES
        or row["error_code"] not in ERRORS
    ):
        raise ValueError("invalid_state")
    for key in ("request_sha256", "result_sha256", "context_sha256"):
        digest = row[key]
        if digest is None and key != "request_sha256":
            continue
        if type(digest) is not str or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
            raise ValueError("invalid_digest")
    events = row["events"]
    if type(events) is not list or not 1 <= len(events) <= 4:
        raise ValueError("invalid_events")
    previous = None
    transitions = {
        None: {"created"},
        "created": {"running", "cancelled", "failed", "interrupted"},
        "running": {"succeeded", "failed", "cancelled", "interrupted"},
    }
    for index, event in enumerate(events, 1):
        if (
            type(event) is not dict
            or set(event) != {"sequence", "state"}
            or type(event["sequence"]) is not int
            or event["sequence"] != index
            or type(event["state"]) is not str
            or event["state"] not in transitions.get(previous, set())
        ):
            raise ValueError("invalid_transition")
        previous = event["state"]
    if previous != row["state"]:
        raise ValueError("state_event_mismatch")
    return row


def metadata(row):
    """Project an in-memory run onto a strict metadata-only record without serializing its raw inputs or outputs."""
    result = {
        "schema_version": 1,
        "id": row["id"],
        "owner_id": str(row["owner"]),
        "workspace_id": row["workspace_id"],
        "state": row["state"],
        "events": row["events"],
        "request_sha256": row["request_sha256"],
        "result_sha256": hashlib.sha256(encoded(row["result"])).hexdigest()
        if "result" in row
        else row.get("result_sha256"),
        "context_sha256": hashlib.sha256(encoded(row["context"])).hexdigest()
        if "context" in row
        else row.get("context_sha256"),
        "error_code": row.get("error", {}).get("code"),
    }
    return validate_record(result)


class HarnessHistoryStore:
    """Own one nonshared private metadata directory with atomic signed snapshots and no grant recovery."""

    def __init__(self, root):
        """Pin private storage, lock its owning process and load only a protected local signing key."""
        self.fd, self.lockfd, self.key = None, None, None
        try:
            root = Path(root)
            root.mkdir(mode=0o700, parents=False, exist_ok=True)
            self.fd = os.open(
                root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
            )
            info = os.fstat(self.fd)
            if info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o700:
                raise ValueError()
            self.lockfd = os.open(
                "history.lock",
                os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC,
                0o600,
                dir_fd=self.fd,
            )
            self.check_file(self.lockfd, 0)
            fcntl.flock(self.lockfd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            try:
                descriptor = os.open(
                    "history.key",
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                    0o600,
                    dir_fd=self.fd,
                )
            except FileExistsError:
                pass
            else:
                with os.fdopen(descriptor, "wb") as stream:
                    stream.write(secrets.token_bytes(32))
                    stream.flush()
                    os.fsync(stream.fileno())
                os.fsync(self.fd)
            self.key = self.read("history.key", 32)
            if len(self.key) != 32:
                raise ValueError()
            self.names()
        except (OSError, ValueError, TypeError, HistoryError):
            self.close()
            raise HistoryError("history_unavailable") from None
        LOGGER.info("harness_history_opened")

    def check_file(self, descriptor, limit):
        """Require one owner-only regular file on the retained directory's filesystem."""
        info = os.fstat(descriptor)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.geteuid()
            or stat.S_IMODE(info.st_mode) != 0o600
            or info.st_nlink != 1
            or info.st_dev != os.fstat(self.fd).st_dev
            or info.st_size > limit
        ):
            raise HistoryError("history_unavailable")

    def read(self, name, limit=16384):
        """Read bounded protected bytes relative to the pinned directory without following links."""
        descriptor = os.open(
            name,
            os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW | os.O_CLOEXEC,
            dir_fd=self.fd,
        )
        with os.fdopen(descriptor, "rb") as stream:
            self.check_file(stream.fileno(), limit)
            raw = stream.read(limit + 1)
        if len(raw) > limit:
            raise HistoryError("history_unavailable")
        return raw

    def names(self):
        """Bound the directory and reject unknown entries rather than silently losing corrupted history."""
        if self.fd is None:
            raise HistoryError("history_unavailable")
        names = os.listdir(self.fd)
        if len(names) > 130:
            raise HistoryError("history_unavailable")
        records = []
        for name in names:
            if name in {"history.key", "history.lock"}:
                continue
            if re.fullmatch(r"pending-[0-9a-f]{32}", name):
                self.read(name)
                LOGGER.warning("harness_history_unpublished_snapshot_retained")
                continue
            if not name.endswith(".json") or str(UUID(name[:-5])) + ".json" != name:
                raise HistoryError("history_unavailable")
            records.append(name)
        if len(records) > 64:
            raise HistoryError("history_unavailable")
        return sorted(records)

    def load(self):
        """Verify every complete record before making any metadata visible to the application."""
        try:
            records = []
            for name in self.names():
                envelope = json.loads(self.read(name), object_pairs_hook=unique_object)
                if (
                    type(envelope) is not dict
                    or set(envelope) != {"record", "mac"}
                    or type(envelope["mac"]) is not str
                ):
                    raise ValueError()
                row = validate_record(envelope["record"])
                expected = hmac.new(self.key, encoded(row), hashlib.sha256).hexdigest()
                if (
                    not hmac.compare_digest(expected, envelope["mac"])
                    or row["id"] + ".json" != name
                ):
                    raise ValueError()
                records.append(row)
            LOGGER.info("harness_history_loaded records=%d", len(records))
            return records
        except (OSError, ValueError, TypeError, KeyError, UnicodeError):
            raise HistoryError("history_unavailable") from None

    def save(self, row):
        """Publish exactly one metadata transition atomically without retrying a failed write."""
        temporary = "pending-" + uuid4().hex
        try:
            record = metadata(row)
            existing = {item["id"]: item for item in self.load()}
            previous = existing.get(record["id"])
            if previous is None:
                if len(existing) >= 64 or record["events"] != [
                    {"sequence": 1, "state": "created"}
                ]:
                    raise ValueError()
            elif (
                any(
                    previous[key] != record[key]
                    for key in ("owner_id", "workspace_id", "request_sha256")
                )
                or record["events"][:-1] != previous["events"]
            ):
                raise ValueError()
            raw = encoded(
                {
                    "record": record,
                    "mac": hmac.new(
                        self.key, encoded(record), hashlib.sha256
                    ).hexdigest(),
                }
            )
            if len(raw) > 16384:
                raise ValueError()
            descriptor = os.open(
                temporary,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                0o600,
                dir_fd=self.fd,
            )
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(
                temporary,
                record["id"] + ".json",
                src_dir_fd=self.fd,
                dst_dir_fd=self.fd,
            )
            os.fsync(self.fd)
            LOGGER.info(
                "harness_history_saved run_id=%s state=%s",
                record["id"],
                record["state"],
            )
        except (OSError, ValueError, TypeError, KeyError, HistoryError):
            raise HistoryError("history_unavailable") from None
        finally:
            if self.fd is not None:
                try:
                    os.unlink(temporary, dir_fd=self.fd)
                except OSError:
                    pass

    def remove(self, owner, identifier):
        """Delete only a verified owner-bound record selected by a canonical host UUID."""
        try:
            if type(owner) is not UUID or type(identifier) is not UUID:
                raise ValueError()
            row = next(
                (item for item in self.load() if item["id"] == str(identifier)), None
            )
            if (
                row is None
                or row["owner_id"] != str(owner)
                or row["state"] in {"created", "running"}
            ):
                raise ValueError()
            os.unlink(str(identifier) + ".json", dir_fd=self.fd)
            os.fsync(self.fd)
            LOGGER.info("harness_history_removed run_id=%s", identifier)
        except (OSError, ValueError, TypeError, HistoryError):
            raise HistoryError("history_unavailable") from None

    def close(self):
        """Release only owned directory/process-lock descriptors while preserving all stored bytes."""
        if self.lockfd is not None:
            os.close(self.lockfd)
            self.lockfd = None
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None
        self.key = None
        LOGGER.info("harness_history_closed")
