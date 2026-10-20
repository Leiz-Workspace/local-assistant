"""Persist bounded owner-scoped Git source checkpoints and one-shot action journals without editing registered workspaces."""

import hashlib
import logging
import os
import re
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from time import monotonic
from uuid import UUID, uuid4

from src.application.services.workspace_policy import WorkspaceAccessError, clean_parts
from src.infrastructure.checkpoint_git import OBJECT_ID, CheckpointGit
from src.infrastructure.checkpoint_storage import (
    RESERVATION_BYTES,
    PrivateCheckpointRoot,
    canonical,
    decode_record,
)

logger = logging.getLogger(__name__)
MAX_CHECKPOINTS = 128
MAX_OWNER_CHECKPOINTS = 32
MAX_RESERVED_BYTES = 16 * 1024 * 1024
DIGEST = re.compile(r"^[a-f0-9]{64}$")
ENTRY = re.compile(r"^[a-f0-9]{32}$")
METADATA_FIELDS = {
    "description",
    "owner_id",
    "workspace_id",
    "proposal_id",
    "path",
    "source_version",
    "base_sha256",
    "new_sha256",
    "mode",
    "gid",
    "root",
    "parent",
    "source",
    "review_sha256",
    "captured_at_utc",
}
JOURNAL_FIELDS = {
    "description",
    "checkpoint_id",
    "proposal_id",
    "record_sha256",
    "state",
    "receipt",
    "error_code",
}
TERMINAL_STATES = {
    "failed",
    "applied",
    "applied_durability_uncertain",
    "applied_cleanup_uncertain",
    "outcome_unknown",
    "applied_checkpoint_uncertain",
}


def digest(raw):
    """Bind exact canonical metadata/source/journal bytes with SHA256 independently of Git object identifiers."""
    return hashlib.sha256(raw).hexdigest()


def check_work(stop, deadline):
    """Stop before another private storage stage on cancellation or the shared cooperative checkpoint deadline."""
    if stop.is_set():
        raise WorkspaceAccessError("checkpoint_cancelled", 503)
    if monotonic() >= deadline:
        raise WorkspaceAccessError("checkpoint_deadline", 504)


class CheckpointStore:
    """Own bounded private per-file Git snapshots and durable receipts while old approval grants remain ephemeral."""

    def __init__(self, root, catalog):
        """Open explicit private storage outside workspace roots without opening any existing project Git repository."""
        self.catalog = catalog
        self.storage = PrivateCheckpointRoot(root, catalog)
        logger.info("checkpoint_store_initialized")

    def authorize(self, owner, workspace):
        """Authorize exact typed configured scope before private record reads or exposing checkpoint existence."""
        if (
            type(owner) is not UUID
            or type(workspace) is not UUID
            or not any(
                spec.owner_id == owner and spec.workspace_id == workspace
                for spec in self.catalog.specifications
            )
        ):
            raise WorkspaceAccessError("checkpoint_not_found", 404)

    def validate_record(self, value, identifier):
        """Require the complete bounded canonical owner/path/hash/native-version schema before trusting private recovery metadata."""
        try:
            if set(value) != {
                "description",
                "checkpoint_id",
                "metadata",
                "objects",
                "git_files",
            } or value["checkpoint_id"] != str(identifier):
                raise ValueError()
            metadata, objects, files = (
                value["metadata"],
                value["objects"],
                value["git_files"],
            )
            if (
                type(metadata) is not dict
                or set(metadata) != METADATA_FIELDS
                or len(canonical(metadata)) > 8192
            ):
                raise ValueError()
            for name in ("owner_id", "workspace_id", "proposal_id"):
                if (
                    type(metadata[name]) is not str
                    or str(UUID(metadata[name])) != metadata[name]
                ):
                    raise ValueError()
            for name in (
                "source_version",
                "base_sha256",
                "new_sha256",
                "review_sha256",
            ):
                if type(metadata[name]) is not str or not DIGEST.fullmatch(
                    metadata[name]
                ):
                    raise ValueError()
            clean_parts(metadata["path"])
            for name, length in (("root", 2), ("parent", 5), ("source", 7)):
                if (
                    type(metadata[name]) is not list
                    or len(metadata[name]) != length
                    or any(type(item) is not int for item in metadata[name])
                ):
                    raise ValueError()
            if (
                type(metadata["mode"]) is not int
                or not 0 <= metadata["mode"] <= 0o777
                or type(metadata["gid"]) is not int
                or not 0 <= metadata["gid"] < 2**32
            ):
                raise ValueError()
            if (
                type(metadata["description"]) is not str
                or type(metadata["captured_at_utc"]) is not str
                or len(metadata["captured_at_utc"]) > 64
            ):
                raise ValueError()
            if (
                type(objects) is not dict
                or set(objects) != {"source", "metadata", "tree", "commit"}
                or any(
                    type(item) is not str or not OBJECT_ID.fullmatch(item)
                    for item in objects.values()
                )
            ):
                raise ValueError()
            if type(files) is not dict or not 1 <= len(files) <= 64:
                raise ValueError()
            for name, sha in files.items():
                if (
                    type(name) is not str
                    or len(name) > 1024
                    or name.startswith("/")
                    or any(part in {"", ".", ".."} for part in name.split("/"))
                    or type(sha) is not str
                    or not DIGEST.fullmatch(sha)
                ):
                    raise ValueError()
        except (ValueError, TypeError, KeyError, OverflowError):
            raise WorkspaceAccessError("checkpoint_record_invalid", 503) from None
        return value

    @contextmanager
    def record(self, identifier):
        """Open one opaque private directory and validate its record without following a caller path or guessing partial ownership."""
        if type(identifier) is not UUID:
            raise WorkspaceAccessError("checkpoint_not_found", 404)
        try:
            with self.storage.directory(self.storage.fd, identifier.hex) as directory:
                raw = self.storage.read(directory, "record.json")
                yield (
                    directory,
                    self.validate_record(decode_record(raw), identifier),
                    digest(raw),
                )
        except FileNotFoundError:
            raise WorkspaceAccessError("checkpoint_not_found", 404) from None

    def inventory(self):
        """Account every durable reservation and stop admission on unknown/incomplete records instead of deleting historical data."""
        names = os.listdir(self.storage.fd)
        if any(name != ".store.lock" and not ENTRY.fullmatch(name) for name in names):
            raise WorkspaceAccessError("checkpoint_recovery_required", 503)
        identifiers = [UUID(hex=name) for name in names if name != ".store.lock"]
        if (
            len(identifiers) > MAX_CHECKPOINTS
            or len(identifiers) * RESERVATION_BYTES > MAX_RESERVED_BYTES
        ):
            raise WorkspaceAccessError("checkpoint_storage_limit", 413)
        result = []
        for identifier in identifiers:
            try:
                with self.record(identifier) as (directory, record, record_sha):
                    self.storage.scan_git(directory)
                    if not {"repo", "template", "record.json", "journal.json"} <= set(
                        os.listdir(directory)
                    ):
                        raise WorkspaceAccessError("checkpoint_recovery_required", 503)
                    self.journal(directory, record, record_sha)
                    result.append(record)
            except WorkspaceAccessError:
                raise WorkspaceAccessError(
                    "checkpoint_recovery_required", 503
                ) from None
        return result

    def capture(self, proposal, stop=None):
        """Durably checkpoint one immutable admitted original source before publishing its pending explicit write review."""
        self.authorize(proposal.owner, proposal.workspace)
        stop = stop if stop is not None else threading.Event()
        deadline = monotonic() + 20
        if (
            proposal.approval_id is not None
            or type(proposal.original) is not bytes
            or type(proposal.replacement) is not bytes
            or len(proposal.original) > 8192
            or len(proposal.replacement) > 8192
            or digest(proposal.original) != proposal.base_sha256
            or digest(proposal.replacement) != proposal.new_sha256
        ):
            raise WorkspaceAccessError("checkpoint_proposal_invalid", 409)
        with self.storage.operation():
            check_work(stop, deadline)
            records = self.inventory()
            if (
                len(records) >= MAX_CHECKPOINTS
                or (len(records) + 1) * RESERVATION_BYTES > MAX_RESERVED_BYTES
                or sum(
                    row["metadata"]["owner_id"] == str(proposal.owner)
                    for row in records
                )
                >= MAX_OWNER_CHECKPOINTS
            ):
                raise WorkspaceAccessError("checkpoint_capacity", 429)
            proposal.verify_version(stop, proposal.clock() + 5)
            identifier = uuid4()
            metadata = dict(
                description="Exact original admitted source checkpoint; not an approval grant.",
                owner_id=str(proposal.owner),
                workspace_id=str(proposal.workspace),
                proposal_id=str(proposal.identifier),
                path=proposal.path,
                source_version=proposal.metadata["version"],
                base_sha256=proposal.base_sha256,
                new_sha256=proposal.new_sha256,
                mode=proposal.metadata["mode"],
                gid=proposal.metadata["gid"],
                root=list(proposal.metadata["root"]),
                parent=list(proposal.metadata["parent"]),
                source=list(proposal.metadata["source"]),
                review_sha256=digest(proposal.artifact),
                captured_at_utc=datetime.now(timezone.utc).isoformat(),
            )
            raw_metadata = canonical(metadata)
            if len(raw_metadata) > 8192:
                raise WorkspaceAccessError("checkpoint_metadata_limit", 413)
            self.storage.validate()
            os.mkdir(identifier.hex, 0o700, dir_fd=self.storage.fd)
            os.fsync(self.storage.fd)
            with self.storage.directory(self.storage.fd, identifier.hex) as directory:
                os.mkdir("repo", 0o700, dir_fd=directory)
                os.mkdir("template", 0o700, dir_fd=directory)
                with (
                    self.storage.directory(directory, "repo") as repository,
                    self.storage.directory(directory, "template") as template,
                ):
                    git = CheckpointGit(
                        repository, template, stop=stop, deadline=deadline
                    )
                    git.execute("init")
                    source = git.execute("blob", proposal.original).strip().decode()
                    meta = git.execute("blob", raw_metadata).strip().decode()
                    tree = (
                        git.execute("tree", identifiers=(meta, source)).strip().decode()
                    )
                    commit = git.execute("commit", identifiers=(tree,)).strip().decode()
                    files, _ = self.storage.scan_git(repository, normalize=True)
                check_work(stop, deadline)
                proposal.verify_version(stop, proposal.clock() + 5)
                record = dict(
                    description="Private one-file Git checkpoint with independently verified SHA256 source/review binding.",
                    checkpoint_id=str(identifier),
                    metadata=metadata,
                    objects=dict(
                        source=source, metadata=meta, tree=tree, commit=commit
                    ),
                    git_files=files,
                )
                self.validate_record(record, identifier)
                self.verify(directory, record, stop, deadline)
                raw = canonical(record)
                self.storage.create_file(directory, "record.json", raw)
                journal = dict(
                    description="Durable action evidence, never a recovered approval grant.",
                    checkpoint_id=str(identifier),
                    proposal_id=str(proposal.identifier),
                    record_sha256=digest(raw),
                    state="ready",
                    receipt=None,
                    error_code=None,
                )
                self.storage.create_file(directory, "journal.json", canonical(journal))
                self.storage.scan_git(directory)
                self.storage.validate()
                os.fsync(directory)
                os.fsync(self.storage.fd)
            logger.info(
                "checkpoint_captured checkpoint_id=%s proposal_id=%s",
                identifier,
                proposal.identifier,
            )
            return identifier

    def journal(self, directory, record, record_sha256, value=None):
        """Validate durable action state against exact checkpoint/proposal/hash without inventing an approval or source outcome."""
        value = (
            decode_record(self.storage.read(directory, "journal.json"))
            if value is None
            else value
        )
        if (
            set(value) != JOURNAL_FIELDS
            or value["checkpoint_id"] != record["checkpoint_id"]
            or value["proposal_id"] != record["metadata"]["proposal_id"]
            or value["record_sha256"] != record_sha256
            or type(value["state"]) is not str
            or value["state"] not in {"ready", "applying"} | TERMINAL_STATES
        ):
            raise WorkspaceAccessError("checkpoint_journal_invalid", 503)
        if value["error_code"] is not None and (
            type(value["error_code"]) is not str
            or not re.fullmatch(r"[a-z0-9_]{1,128}", value["error_code"])
        ):
            raise WorkspaceAccessError("checkpoint_journal_invalid", 503)
        receipt = value["receipt"]
        if value["state"] in {"ready", "applying", "failed"}:
            if receipt is not None:
                raise WorkspaceAccessError("checkpoint_journal_invalid", 503)
        elif (
            type(receipt) is not dict
            or set(receipt)
            != {
                "proposal_id",
                "approval_id",
                "state",
                "applied",
                "path",
                "base_sha256",
                "new_sha256",
                "uncertainties",
                "rename_ack_reconciled",
            }
            or receipt.get("proposal_id") != value["proposal_id"]
            or receipt.get("path") != record["metadata"]["path"]
            or receipt.get("base_sha256") != record["metadata"]["base_sha256"]
            or receipt.get("new_sha256") != record["metadata"]["new_sha256"]
            or receipt.get("state") != value["state"]
            or (
                receipt.get("applied") is not None
                if value["state"] == "outcome_unknown"
                else receipt.get("applied") is not True
            )
        ):
            raise WorkspaceAccessError("checkpoint_journal_invalid", 503)
        if receipt is not None:
            try:
                if (
                    type(receipt["approval_id"]) is not str
                    or str(UUID(receipt["approval_id"])) != receipt["approval_id"]
                    or type(receipt["rename_ack_reconciled"]) is not bool
                    or type(receipt["uncertainties"]) is not list
                    or len(receipt["uncertainties"]) > 8
                    or any(
                        type(item) is not str
                        or item not in TERMINAL_STATES - {"failed"}
                        for item in receipt["uncertainties"]
                    )
                ):
                    raise ValueError()
            except (ValueError, TypeError, KeyError):
                raise WorkspaceAccessError("checkpoint_journal_invalid", 503) from None
        return value

    def verify(self, directory, record, stop, deadline):
        """Verify all private Git files, canonical metadata, source SHA256 and actual committed tree before returning historical bytes."""
        with (
            self.storage.directory(directory, "repo") as repository,
            self.storage.directory(directory, "template") as template,
        ):
            files, _ = self.storage.scan_git(repository)
            if files != record["git_files"] or os.listdir(template):
                raise WorkspaceAccessError("checkpoint_git_changed", 409)
            git = CheckpointGit(repository, template, stop=stop, deadline=deadline)
            ids = record["objects"]
            raw = git.execute("read_blob", identifiers=(ids["source"],))
            metadata = git.execute("read_blob", identifiers=(ids["metadata"],))
            tree = git.execute("read_tree", identifiers=(ids["tree"],))
            commit = git.execute("read_commit", identifiers=(ids["commit"],))
            expected_tree = (
                b"100644 metadata.json\x00"
                + bytes.fromhex(ids["metadata"])
                + b"100644 source.bin\x00"
                + bytes.fromhex(ids["source"])
            )
            if (
                len(raw) > 8192
                or b"\x00" in raw
                or digest(raw) != record["metadata"]["base_sha256"]
                or metadata != canonical(record["metadata"])
                or tree != expected_tree
                or not commit.startswith(("tree " + ids["tree"] + "\n").encode())
            ):
                raise WorkspaceAccessError("checkpoint_integrity_failed", 409)
            for kind, content in (
                ("source", raw),
                ("metadata", metadata),
                ("tree", tree),
                ("commit", commit),
            ):
                object_type = "blob" if kind in {"source", "metadata"} else kind
                if (
                    hashlib.sha1(
                        (object_type + " " + str(len(content)) + "\x00").encode()
                        + content
                    ).hexdigest()
                    != ids[kind]
                ):
                    raise WorkspaceAccessError("checkpoint_integrity_failed", 409)
            try:
                raw.decode("utf-8")
            except UnicodeError:
                raise WorkspaceAccessError("checkpoint_integrity_failed", 409) from None
        check_work(stop, deadline)
        self.storage.validate()
        return raw

    def read(self, owner, workspace, identifier, stop=None):
        """Return only an authorized verified historical source/checkpoint/journal without implying current source state or write permission."""
        self.authorize(owner, workspace)
        stop = stop if stop is not None else threading.Event()
        deadline = monotonic() + 20
        with (
            self.storage.operation(),
            self.record(identifier) as (directory, record, record_sha),
        ):
            if record["metadata"]["owner_id"] != str(owner) or record["metadata"][
                "workspace_id"
            ] != str(workspace):
                raise WorkspaceAccessError("checkpoint_not_found", 404)
            raw = self.verify(directory, record, stop, deadline)
            journal = self.journal(directory, record, record_sha)
            warnings = (
                []
                if set(os.listdir(directory))
                == {"repo", "template", "record.json", "journal.json"}
                else ["unacknowledged_private_entry"]
            )
            logger.info("checkpoint_reviewed checkpoint_id=%s", identifier)
            return dict(
                checkpoint_id=str(identifier),
                metadata=record["metadata"],
                commit_id=record["objects"]["commit"],
                original=raw.decode(),
                journal=journal,
                recovery_warnings=warnings,
                current_source_observed=False,
                recovered_approval=False,
            )

    def transition(self, proposal, identifier, stop=None, *, finish=False):
        """Publish ready→applying→terminal evidence for the exact captured proposal without consuming or recovering approval grants."""
        self.authorize(proposal.owner, proposal.workspace)
        stop = stop if stop is not None else threading.Event()
        deadline = monotonic() + 20
        with (
            self.storage.operation(),
            self.record(identifier) as (directory, record, record_sha),
        ):
            metadata = record["metadata"]
            if (
                metadata["owner_id"] != str(proposal.owner)
                or metadata["workspace_id"] != str(proposal.workspace)
                or metadata["proposal_id"] != str(proposal.identifier)
                or metadata["review_sha256"] != digest(proposal.artifact)
                or metadata["base_sha256"] != proposal.base_sha256
                or metadata["new_sha256"] != proposal.new_sha256
                or metadata["path"] != proposal.path
                or metadata["source_version"] != proposal.metadata["version"]
                or metadata["root"] != list(proposal.metadata["root"])
                or metadata["parent"] != list(proposal.metadata["parent"])
                or metadata["source"] != list(proposal.metadata["source"])
                or metadata["mode"] != proposal.metadata["mode"]
                or metadata["gid"] != proposal.metadata["gid"]
            ):
                raise WorkspaceAccessError("checkpoint_proposal_changed", 409)
            journal = self.journal(directory, record, record_sha)
            if set(os.listdir(directory)) != {
                "repo",
                "template",
                "record.json",
                "journal.json",
            }:
                raise WorkspaceAccessError("checkpoint_recovery_required", 503)
            if not finish:
                if journal["state"] != "ready":
                    raise WorkspaceAccessError("checkpoint_state_conflict", 409)
                self.verify(directory, record, stop, deadline)
                check_work(stop, deadline)
                journal["state"] = "applying"
            else:
                if journal["state"] != "applying":
                    raise WorkspaceAccessError("checkpoint_state_conflict", 409)
                journal["state"] = (
                    proposal.receipt["state"]
                    if proposal.receipt is not None
                    else "failed"
                )
                journal["receipt"] = proposal.public()["receipt"]
                journal["error_code"] = (
                    None
                    if proposal.receipt is not None
                    else proposal.error_code or "patch_interrupted"
                )
            self.journal(directory, record, record_sha, journal)
            self.storage.replace_journal(directory, journal)
            logger.info(
                "checkpoint_action_recorded checkpoint_id=%s state=%s",
                identifier,
                journal["state"],
            )
            return journal

    def list(self, owner, workspace):
        """List bounded own historical metadata without exposing another owner's identifiers, content or recovered grants."""
        self.authorize(owner, workspace)
        with self.storage.operation():
            records = self.inventory()
            return [
                dict(
                    checkpoint_id=row["checkpoint_id"],
                    metadata=row["metadata"],
                    commit_id=row["objects"]["commit"],
                )
                for row in records
                if row["metadata"]["owner_id"] == str(owner)
                and row["metadata"]["workspace_id"] == str(workspace)
            ]

    def close(self):
        """Release only private storage capabilities after joined operations while retaining all durable historical files."""
        self.storage.close()
        logger.info("checkpoint_store_closed")
