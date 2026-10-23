"""Persist bounded signed append-only plan metadata through a private pinned directory FD and exact latest-chain recovery."""

import fcntl
import hashlib
import hmac
import json
import logging
import os
import secrets
import stat
from contextlib import contextmanager
from pathlib import Path
from uuid import UUID

from src.application.ports.plan_checkpoint import (
    CheckpointError,
    PlanCheckpoint,
    validate_state,
    validate_transition,
)
from src.application.services.workspace_requests import parse_workspace_json

logger = logging.getLogger(__name__)


def encoded(value):
    """Encode bounded finite metadata deterministically for both HMAC and complete-file hashes."""
    try:
        raw = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode()
        if not 1 <= len(raw) <= 16384:
            raise ValueError()
        return raw
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise CheckpointError("invalid") from None


class PlanCheckpointStore:
    """Own one private directory/key and exclusively appended, contiguous signed state chain per trusted run ID."""

    def __init__(self, root):
        """Pin an owner-private directory and a durable local signing key without exposing either to plan arguments."""
        self.fd = None
        self.held = set()
        try:
            root = Path(root)
            root.mkdir(mode=0o700, parents=False, exist_ok=True)
            self.fd = os.open(
                root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
            )
            info = os.fstat(self.fd)
            if info.st_uid != os.geteuid() or info.st_mode & 0o077:
                raise ValueError()
            try:
                keyfd = os.open(
                    "signing.key",
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                    0o600,
                    dir_fd=self.fd,
                )
            except FileExistsError:
                pass
            else:
                with os.fdopen(keyfd, "wb") as stream:
                    stream.write(secrets.token_bytes(32))
                    stream.flush()
                    os.fsync(stream.fileno())
                os.fsync(self.fd)
            self.key = self.read("signing.key", 32)
            if len(self.key) != 32:
                raise ValueError()
        except (OSError, ValueError, TypeError, CheckpointError):
            if self.fd is not None:
                os.close(self.fd)
            self.fd = None
            raise CheckpointError("unavailable") from None
        logger.info("plan_checkpoint_store_opened")

    def opened(self):
        """Refuse I/O after the pinned storage capability has been closed."""
        if self.fd is None:
            raise CheckpointError("closed")

    def read(self, name, bound=16384):
        """Read only a bounded owner-private regular leaf through the pinned directory FD without following links."""
        self.opened()
        try:
            descriptor = os.open(
                name,
                os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC,
                dir_fd=self.fd,
            )
            with os.fdopen(descriptor, "rb") as stream:
                info = os.fstat(stream.fileno())
                if (
                    not stat.S_ISREG(info.st_mode)
                    or info.st_uid != os.geteuid()
                    or info.st_mode & 0o077
                    or info.st_size > bound
                ):
                    raise ValueError()
                raw = stream.read(bound + 1)
            if len(raw) > bound:
                raise ValueError()
            return raw
        except (OSError, ValueError):
            raise CheckpointError("invalid") from None

    @contextmanager
    def lock(self, run_id):
        """Hold one nonblocking kernel run lock through actual action cleanup and checkpoint publication."""
        self.opened()
        if type(run_id) is not UUID:
            raise CheckpointError("invalid")
        descriptor = None
        acquired = False
        try:
            descriptor = os.open(
                str(run_id) + ".lock",
                os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC,
                0o600,
                dir_fd=self.fd,
            )
            info = os.fstat(descriptor)
            if (
                not stat.S_ISREG(info.st_mode)
                or info.st_uid != os.geteuid()
                or info.st_mode & 0o077
            ):
                raise CheckpointError("invalid")
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise CheckpointError("busy") from None
            self.held.add(run_id)
            acquired = True
            yield
        except OSError:
            raise CheckpointError("unavailable") from None
        finally:
            if descriptor is not None:
                os.close(descriptor)
            if acquired:
                self.held.discard(run_id)

    def latest(self, run_id):
        """Verify the entire contiguous signed chain and never silently fall back from a damaged latest record."""
        self.opened()
        if type(run_id) is not UUID:
            raise CheckpointError("invalid")
        prefix = str(run_id) + "."
        names = sorted(
            name
            for name in os.listdir(self.fd)
            if name.startswith(prefix) and name.endswith(".json")
        )
        if not names:
            return None, None
        if len(names) > 32:
            raise CheckpointError("capacity")
        previous = None
        previous_state = None
        for revision, name in enumerate(names, 1):
            if name != f"{run_id}.{revision:02d}.json":
                raise CheckpointError("invalid")
            raw = self.read(name)
            try:
                value = parse_workspace_json(raw)
                if type(value) is not dict or set(value) != {
                    "description",
                    "version",
                    "run_id",
                    "revision",
                    "previous_sha256",
                    "state",
                    "signature",
                }:
                    raise ValueError()
                signature = value.pop("signature")
                actual = hmac.new(self.key, encoded(value), hashlib.sha256).hexdigest()
                if (
                    type(signature) is not str
                    or not hmac.compare_digest(signature, actual)
                    or value["version"] != 1
                    or value["run_id"] != str(run_id)
                    or value["revision"] != revision
                    or value["previous_sha256"]
                    != (previous.sha256 if previous else None)
                ):
                    raise ValueError()
                state = value["state"]
                validate_state(state)
                validate_transition(previous_state, state)
            except Exception:
                raise CheckpointError("invalid") from None
            previous = PlanCheckpoint(run_id, revision, hashlib.sha256(raw).hexdigest())
            previous_state = state
        logger.info(
            "plan_checkpoint_chain_verified run_id=%s revision=%d",
            run_id,
            previous.revision,
        )
        return state, previous

    def append(self, run_id, state, previous):
        """Exclusively append and fsync one signed metadata revision before allowing the next action boundary."""
        self.opened()
        if run_id not in self.held:
            raise CheckpointError("busy")
        validate_state(state)
        prior, latest = self.latest(run_id)
        if latest != previous:
            raise CheckpointError("stale")
        validate_transition(prior, state)
        revision = 1 if previous is None else previous.revision + 1
        if revision > 32:
            raise CheckpointError("capacity")
        value = dict(
            description="Private signed plan status/budget metadata only; no arguments, output bodies or approval grants.",
            version=1,
            run_id=str(run_id),
            revision=revision,
            previous_sha256=previous.sha256 if previous else None,
            state=state,
        )
        raw = encoded(
            dict(
                value,
                signature=hmac.new(
                    self.key, encoded(value), hashlib.sha256
                ).hexdigest(),
            )
        )
        try:
            descriptor = os.open(
                f"{run_id}.{revision:02d}.json",
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                0o600,
                dir_fd=self.fd,
            )
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            os.fsync(self.fd)
        except OSError:
            raise CheckpointError("unavailable") from None
        logger.info("plan_checkpoint_appended run_id=%s revision=%d", run_id, revision)
        return PlanCheckpoint(run_id, revision, hashlib.sha256(raw).hexdigest())

    def close(self):
        """Release only the private directory capability, retaining all signed history and its local key for recovery."""
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None
        logger.info("plan_checkpoint_store_closed")
