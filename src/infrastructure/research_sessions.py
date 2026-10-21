"""Persist bounded private research journals and immutable archives with exclusive native ownership and explicit crash recovery."""

import hashlib
import logging
import os
import re
from contextlib import contextmanager
from uuid import UUID, uuid4

from src.application.services.claim_validation_policy import prepare_claims
from src.application.services.research_session_policy import (
    LIMITS,
    ResearchSessionError,
    check_archive,
    check_journal,
    decode,
    identifiers,
)
from src.application.services.workspace_policy import WorkspaceAccessError
from src.infrastructure.checkpoint_storage import PrivateCheckpointRoot

logger = logging.getLogger(__name__)
MAX_SESSIONS = 16
MAX_OWNER_SESSIONS = 4


class PrivateResearchSessions:
    """Own one explicit exclusive private store without provisioning production paths or deleting retained output."""

    def __init__(self, root, catalog):
        """Open an already provisioned0700 root outside registered workspaces using accepted native inode and lock guards."""
        self.root = None
        self.closing = False
        try:
            self.root = PrivateCheckpointRoot(root, catalog)
            with self.operation():
                self.scan()
        except Exception:
            self.close()
            raise ResearchSessionError("session_store_invalid") from None
        logger.info("research_session_store_opened")

    @contextmanager
    def operation(self):
        """Reject unsafe/uncertain native storage and poison admission while preserving all on-disk evidence."""
        if self.closing or self.root is None:
            raise ResearchSessionError("session_closed")
        try:
            with self.root.operation():
                yield
        except ResearchSessionError as error:
            if error.code == "session_store_invalid":
                self.closing = True
            raise
        except WorkspaceAccessError as error:
            if error.code == "checkpoint_store_busy":
                raise ResearchSessionError("session_busy") from None
            self.closing = True
            raise ResearchSessionError("session_store_invalid") from None
        except Exception:
            self.closing = True
            raise ResearchSessionError("session_store_invalid") from None

    def scan(self):
        """Bound every root entry and validate all retained journals without accepting unknown directories or metadata as progress."""
        names = os.listdir(self.root.fd)
        if len(names) > MAX_SESSIONS + 1 or ".store.lock" not in names:
            raise ResearchSessionError("session_store_invalid")
        journals = []
        for name in names:
            if name == ".store.lock":
                continue
            try:
                run_id = UUID(name)
                if str(run_id) != name:
                    raise ValueError()
            except ValueError:
                raise ResearchSessionError("session_store_invalid") from None
            with self.root.directory(self.root.fd, name) as directory:
                value = self.read_record(directory, run_id)
            journals.append(value)
        return journals

    def read_record(self, directory, run_id, owner=None):
        """Validate complete acknowledged blob hashes and bounded unacknowledged candidates without publishing or deleting them."""
        value = check_journal(decode(self.root.read(directory, "journal.json"), 32768))
        if value["run_id"] != str(run_id):
            raise ResearchSessionError("session_store_invalid")
        if owner is not None and value["owner_id"] != str(owner):
            raise ResearchSessionError("session_not_found")
        owner = UUID(value["owner_id"])
        names = os.listdir(directory)
        if len(names) > 6:
            raise ResearchSessionError("session_store_invalid")
        for name in names:
            if name == "journal.json":
                continue
            if re.fullmatch(r"\.journal-[0-9a-f]{32}\.tmp", name):
                self.root.read(directory, name)
                if value["state"] not in {"running", "interrupted"}:
                    raise ResearchSessionError("session_store_invalid")
                continue
            kind = name.removesuffix(".blob")
            if kind not in LIMITS or name != kind + ".blob":
                raise ResearchSessionError("session_store_invalid")
            raw = self.root.read(directory, name, LIMITS[kind])
            info = value["blobs"].get(kind)
            if info is not None:
                if (
                    len(raw) != info["bytes"]
                    or hashlib.sha256(raw).hexdigest() != info["sha256"]
                ):
                    raise ResearchSessionError("session_store_invalid")
                check_archive(raw, kind, owner, run_id)
            elif value["state"] not in {"running", "interrupted"}:
                raise ResearchSessionError("session_store_invalid")
        if not {kind + ".blob" for kind in value["blobs"]} <= set(names):
            raise ResearchSessionError("session_store_invalid")
        return value

    @contextmanager
    def entry(self, owner, run_id):
        """Admit an exact owned UUID directory and hide missing/foreign session identities behind one finite error."""
        identifiers(owner, run_id)
        if str(run_id) not in os.listdir(self.root.fd):
            raise ResearchSessionError("session_not_found")
        with self.root.directory(self.root.fd, str(run_id)) as directory:
            value = self.read_record(directory, run_id, owner)
            yield directory, value

    def create(self, owner, goal, claims):
        """Reserve a bounded retained session and fsync its initial inputs without initiating a model, provider or source call."""
        identifiers(owner)
        try:
            goal, claims = prepare_claims(goal, claims)
        except Exception:
            raise ResearchSessionError("session_invalid") from None
        with self.operation():
            rows = self.scan()
            if (
                len(rows) >= MAX_SESSIONS
                or sum(row["owner_id"] == str(owner) for row in rows)
                >= MAX_OWNER_SESSIONS
            ):
                raise ResearchSessionError("session_capacity")
            run_id = uuid4()
            value = check_journal(
                dict(
                    description="Private bounded research session journal.",
                    schema_version="research-session-v1",
                    run_id=str(run_id),
                    owner_id=str(owner),
                    goal=goal,
                    claims=list(claims),
                    state="ready",
                    attempts=[],
                    blobs={},
                    error_code=None,
                )
            )
            os.mkdir(str(run_id), 0o700, dir_fd=self.root.fd)
            os.fsync(self.root.fd)
            with self.root.directory(self.root.fd, str(run_id)) as directory:
                self.root.replace_journal(directory, value)
        logger.info("research_session_created")
        return value

    def load(self, owner, run_id):
        """Read an owned journal and validate every acknowledged archive without any tool dispatch or receipt renewal."""
        with self.operation(), self.entry(owner, run_id) as (_, value):
            return value

    def begin(self, owner, run_id):
        """Fsync a once-only next-stage reservation before the caller may dispatch any async model/provider/native work."""
        with self.operation(), self.entry(owner, run_id) as (directory, value):
            if value["state"] not in {"ready", "paused"}:
                raise ResearchSessionError("session_state_invalid")
            stage = "discover" if value["state"] == "ready" else "publish"
            value["state"] = "running"
            value["attempts"].append(stage)
            self.root.replace_journal(directory, check_journal(value))
        logger.info("research_session_attempt_reserved stage=%s", stage)
        return value

    def append(self, owner, run_id, kind, raw):
        """Write one immutable complete bounded blob before atomically acknowledging its hash in the journal."""
        identifiers(owner, run_id)
        if type(kind) is not str or kind not in LIMITS:
            raise ResearchSessionError("session_invalid")
        check_archive(raw, kind, owner, run_id)
        with self.operation(), self.entry(owner, run_id) as (directory, value):
            expected = (
                "discover"
                if len(value["attempts"]) == 1
                else "report"
                if "report" not in value["blobs"]
                else "export"
            )
            if (
                value["state"] != "running"
                or kind != expected
                or kind in value["blobs"]
            ):
                raise ResearchSessionError("session_state_invalid")
            descriptor = os.open(
                kind + ".blob",
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                0o600,
                dir_fd=directory,
            )
            try:
                self.root.file_info(descriptor)
                offset = 0
                while offset < len(raw):
                    written = os.write(descriptor, raw[offset:])
                    if written <= 0:
                        raise OSError()
                    offset += written
                os.fsync(descriptor)
                self.root.file_info(descriptor)
            finally:
                os.close(descriptor)
            os.fsync(directory)
            value["blobs"][kind] = dict(
                sha256=hashlib.sha256(raw).hexdigest(), bytes=len(raw)
            )
            self.root.replace_journal(directory, check_journal(value))
        logger.info(
            "research_session_blob_acknowledged kind=%s bytes=%d", kind, len(raw)
        )

    def finish(self, owner, run_id):
        """Publish only complete acknowledged stage output and pause before the next explicit owner action."""
        with self.operation(), self.entry(owner, run_id) as (directory, value):
            if value["state"] != "running":
                raise ResearchSessionError("session_state_invalid")
            value["state"] = "paused" if len(value["attempts"]) == 1 else "complete"
            self.root.replace_journal(directory, check_journal(value))
        logger.info("research_session_stage_committed state=%s", value["state"])
        return value

    def interrupt(self, owner, run_id, code):
        """Retain every original attempt/blob while terminating an uncertain or cancelled stage without authorizing a retry."""
        with self.operation(), self.entry(owner, run_id) as (directory, value):
            if value["state"] != "running":
                raise ResearchSessionError("session_state_invalid")
            value["state"], value["error_code"] = "interrupted", code
            self.root.replace_journal(directory, check_journal(value))
        logger.info("research_session_interrupted code=%s", code)
        return value

    def recover(self):
        """Mark only previously running journals interrupted without replaying tools or adopting unacknowledged candidate output."""
        recovered = 0
        with self.operation():
            for value in self.scan():
                if value["state"] != "running":
                    continue
                value["state"], value["error_code"] = (
                    "interrupted",
                    "session_process_interrupted",
                )
                with self.root.directory(self.root.fd, value["run_id"]) as directory:
                    self.root.replace_journal(directory, check_journal(value))
                recovered += 1
        logger.info("research_session_recovery_complete interrupted=%d", recovered)
        return recovered

    def archive(self, owner, run_id, kind):
        """Return only acknowledged owned archive bytes, preserving data classification and original hash across restarts."""
        if type(kind) is not str or kind not in LIMITS:
            raise ResearchSessionError("session_invalid")
        with self.operation(), self.entry(owner, run_id) as (directory, value):
            if kind not in value["blobs"]:
                raise ResearchSessionError("session_not_found")
            return self.root.read(directory, kind + ".blob", LIMITS[kind])

    def close(self):
        """Release only exclusive storage handles after session-owned work joins, retaining every journal and artifact."""
        self.closing = True
        if self.root is not None:
            self.root.close()
        logger.info("research_session_store_closed")
