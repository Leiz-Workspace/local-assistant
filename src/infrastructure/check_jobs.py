"""Persist bounded owner-scoped immutable check snapshots, concrete review artifacts and durable execution journals without workspace writes."""

import logging
import os
import re
import stat
import threading
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
from time import monotonic
from uuid import UUID, uuid4

from src.application.services.approvals import scope_for
from src.application.services.check_policy import (
    CAPTURE_SECONDS,
    MAX_JOBS,
    MAX_OWNER_JOBS,
    MAX_RECORD_BYTES,
    RESERVATION_BYTES,
    execution_policy,
)
from src.application.services.workspace_policy import WorkspaceAccessError
from src.infrastructure.check_job_records import (
    decode_record,
    encode_record,
    review_artifact,
    sha256,
    validate_core,
    validate_journal,
)
from src.infrastructure.check_runner import NativeChecks
from src.infrastructure.check_runtime import RuntimeCapsule
from src.infrastructure.check_runtime_io import (
    check_capture,
    read_private,
)
from src.infrastructure.check_sources import directory_context
from src.infrastructure.checkpoint_storage import (
    PrivateCheckpointRoot,
    ancestor_identities,
)
from src.infrastructure.readonly_workspace import ROOT_FLAGS, open_beneath
from src.infrastructure.workspace_reader import fingerprint

logger = logging.getLogger(__name__)
ENTRY = re.compile(r"^[a-f0-9]{32}$")
JOB_MEMBERS = frozenset({"snapshot", "manifest.json", "review.json", "journal.json"})


class CheckJobStore:
    """Own one explicit exclusive private check store and runtime while keeping grants and source pins process-local."""

    def __init__(self, root, catalog, runtime_spec, checkpoint_root, stop=None):
        """Admit native disjoint private roots and a verified existing runtime without registering workspaces or installing tools."""
        self.catalog, self.runtime, self.storage, self.closing = (
            catalog,
            None,
            None,
            False,
        )
        self.cpu = min(os.sched_getaffinity(0))
        try:
            self.storage = PrivateCheckpointRoot(root, catalog)
            other = os.fstat(checkpoint_root)
            current = os.fstat(self.storage.fd)
            if (other.st_dev, other.st_ino) in ancestor_identities(self.storage.fd) or (
                current.st_dev,
                current.st_ino,
            ) in ancestor_identities(checkpoint_root):
                raise WorkspaceAccessError("checks_checkpoint_root_overlap", 422)
            self.runtime = RuntimeCapsule(self.storage.fd, runtime_spec, stop)
            with self.operation():
                self.inventory()
            logger.info("checks_job_store_initialized")
        except BaseException:
            self.close()
            raise

    def available(self):
        """Refuse new native work during dependency-ordered store teardown before touching private descriptors."""
        if self.closing or self.storage is None or self.storage.closing:
            raise WorkspaceAccessError("checks_store_unavailable", 503)

    @contextmanager
    def operation(self):
        """Admit one nonqueued operation and validate the retained root/lock before any private file access."""
        self.available()
        with self.storage.operation():
            self.available()
            yield
        logger.info("checks_store_operation_closed")

    def authorize(self, owner, workspace):
        """Authorize typed configured application scope before metadata reads, capacity inspection or revealing job existence."""
        if (
            type(owner) is not UUID
            or type(workspace) is not UUID
            or not any(
                spec.owner_id == owner and spec.workspace_id == workspace
                for spec in self.catalog.specifications
            )
        ):
            raise WorkspaceAccessError("checks_job_not_found", 404)

    @contextmanager
    def job(self, identifier, owner=None, workspace=None):
        """Borrow one opaque private job and verify its exact canonical context/review/journal before returning trusted metadata."""
        if type(identifier) is not UUID:
            raise WorkspaceAccessError("checks_job_not_found", 404)
        try:
            with self.storage.directory(self.storage.fd, identifier.hex) as directory:
                raw = self.storage.read(directory, "manifest.json")
                value = decode_record(raw)
                if owner is not None and (
                    value.get("owner_id") != str(owner)
                    or value.get("workspace_id") != str(workspace)
                ):
                    raise WorkspaceAccessError("checks_job_not_found", 404)
                if "review_sha256" not in value:
                    raise WorkspaceAccessError("checks_job_manifest_invalid", 503)
                core = {
                    key: item for key, item in value.items() if key != "review_sha256"
                }
                validate_core(core, identifier)
                info = os.fstat(directory)
                if (
                    core["private_root"] != [info.st_dev, info.st_ino]
                    or encode_record(value) != raw
                ):
                    raise WorkspaceAccessError("checks_job_changed", 409)
                review = self.storage.read(directory, "review.json")
                if (
                    sha256(review) != value["review_sha256"]
                    or review_artifact(core) != review
                ):
                    raise WorkspaceAccessError("checks_job_review_changed", 409)
                digest = sha256(raw)
                journal = validate_journal(
                    decode_record(self.storage.read(directory, "journal.json")),
                    core,
                    digest,
                )
                yield directory, core, journal, digest, review
        except FileNotFoundError:
            raise WorkspaceAccessError("checks_job_not_found", 404) from None

    def inventory(self):
        """Charge every retained job and reject unknown/partial entries instead of deleting history or silently reclaiming capacity."""
        names = os.listdir(self.storage.fd)
        if len(names) > MAX_JOBS + 2 or any(
            name not in {"runtime", ".store.lock"} and not ENTRY.fullmatch(name)
            for name in names
        ):
            raise WorkspaceAccessError("checks_storage_recovery_required", 503)
        records = []
        for name in names:
            if name in {"runtime", ".store.lock"}:
                continue
            try:
                with self.job(UUID(hex=name)) as (directory, core, _, _, _):
                    if set(os.listdir(directory)) != JOB_MEMBERS:
                        raise WorkspaceAccessError(
                            "checks_storage_recovery_required", 503
                        )
                    self.scan_snapshot(directory, core["source"], core["snapshot"])
                    self.allocated_job(directory)
                    records.append(core)
            except (WorkspaceAccessError, OSError):
                raise WorkspaceAccessError(
                    "checks_storage_recovery_required", 503
                ) from None
        return records

    @contextmanager
    def snapshot_parent(self, snapshot, path, *, create=False):
        """Borrow only native private path parents and fsync newly created directory entries without following aliases."""
        current = os.dup(snapshot)
        try:
            for part in path.split("/")[:-1]:
                if create:
                    try:
                        os.mkdir(part, 0o700, dir_fd=current)
                        os.fsync(current)
                    except FileExistsError:
                        pass
                child = open_beneath(current, part, flags=ROOT_FLAGS)
                try:
                    self.storage.directory_info(child)
                except BaseException:
                    os.close(child)
                    raise
                os.close(current)
                current = child
            yield current
            if create:
                os.fsync(current)
        finally:
            os.close(current)

    def scan_snapshot(self, directory, source, expected=None, stop=None, deadline=None):
        """Verify complete selected private bytes and native identities, rejecting extra directories/files before launch."""
        stop = stop if stop is not None else threading.Event()
        deadline = deadline if deadline is not None else monotonic() + CAPTURE_SECONDS
        selected = {item["path"]: item for item in source["files"]}
        files, directories, entries = {}, {}, 0
        with self.storage.directory(directory, "snapshot") as snapshot:

            def visit(parent, prefix, depth):
                """Walk only bounded owned snapshot entries and bind exact source hashes plus inode/time context."""
                nonlocal entries
                check_capture(stop, deadline)
                info = self.storage.directory_info(parent)
                directories[prefix.rstrip("/")] = list(fingerprint(info))
                names = sorted(os.listdir(parent))
                entries += len(names)
                if entries > 128 or depth > 3:
                    raise WorkspaceAccessError("checks_snapshot_limit", 413)
                for name in names:
                    check_capture(stop, deadline)
                    path = prefix + name
                    info = os.stat(name, dir_fd=parent, follow_symlinks=False)
                    if stat.S_ISDIR(info.st_mode):
                        with self.storage.directory(parent, name) as child:
                            visit(child, path + "/", depth + 1)
                    else:
                        if path not in selected:
                            raise WorkspaceAccessError("checks_snapshot_changed", 409)
                        raw, version = read_private(
                            parent, name, 8192, self.storage.identity.st_dev, mode=0o600
                        )
                        item = selected[path]
                        if len(raw) != item["size"] or sha256(raw) != item["sha256"]:
                            raise WorkspaceAccessError("checks_snapshot_changed", 409)
                        files[path] = dict(
                            sha256=sha256(raw), size=len(raw), native=list(version)
                        )
                if (
                    list(fingerprint(self.storage.directory_info(parent)))
                    != directories[prefix.rstrip("/")]
                ):
                    raise WorkspaceAccessError("checks_snapshot_changed", 409)

            visit(snapshot, "", 0)
            needed = {""}
            for path in selected:
                parts = path.split("/")
                needed.update("/".join(parts[:index]) for index in range(1, len(parts)))
            if set(files) != set(selected) or set(directories) != needed:
                raise WorkspaceAccessError("checks_snapshot_changed", 409)
            for path, item in files.items():
                check_capture(stop, deadline)
                descriptor = open_beneath(snapshot, path)
                try:
                    if (
                        list(fingerprint(self.storage.file_info(descriptor)))
                        != item["native"]
                    ):
                        raise WorkspaceAccessError("checks_snapshot_changed", 409)
                finally:
                    os.close(descriptor)
            for path, version in directories.items():
                descriptor = (
                    os.dup(snapshot)
                    if not path
                    else open_beneath(snapshot, path, flags=ROOT_FLAGS)
                )
                try:
                    if (
                        list(fingerprint(self.storage.directory_info(descriptor)))
                        != version
                    ):
                        raise WorkspaceAccessError("checks_snapshot_changed", 409)
                finally:
                    os.close(descriptor)
        value = dict(files=files, directories=directories)
        if expected is not None and encode_record(value) != encode_record(expected):
            raise WorkspaceAccessError("checks_snapshot_changed", 409)
        return value

    def allocated_job(self, directory):
        """Bound every actual private job inode/allocation independently of logical reservations and preserve unknown entries."""
        allocated, entries = 0, 0

        def visit(parent, depth):
            """Account only kernel-admitted private inodes without following mount/link aliases or reading unbounded data."""
            nonlocal allocated, entries
            info = self.storage.directory_info(parent)
            allocated += info.st_blocks * 512
            names = os.listdir(parent)
            entries += len(names)
            if entries > 128 or depth > 5:
                raise WorkspaceAccessError("checks_job_storage_limit", 413)
            for name in names:
                descriptor = open_beneath(parent, name)
                try:
                    info = os.fstat(descriptor)
                    if stat.S_ISDIR(info.st_mode):
                        visit(descriptor, depth + 1)
                    else:
                        info = self.storage.file_info(descriptor)
                        allocated += info.st_blocks * 512
                        if info.st_size > MAX_RECORD_BYTES:
                            raise WorkspaceAccessError("checks_job_storage_limit", 413)
                    if allocated > RESERVATION_BYTES:
                        raise WorkspaceAccessError("checks_job_storage_limit", 413)
                finally:
                    os.close(descriptor)

        visit(directory, 0)
        if allocated > RESERVATION_BYTES:
            raise WorkspaceAccessError("checks_job_storage_limit", 413)
        return allocated

    def capture(self, sources, stop=None):
        """Reserve and durably capture one exact private source snapshot/review before creating any pending execution grant."""
        self.authorize(sources.owner, sources.workspace)
        stop = stop if stop is not None else threading.Event()
        deadline = monotonic() + CAPTURE_SECONDS
        with self.operation():
            records = self.inventory()
            if (
                len(records) >= MAX_JOBS
                or sum(item["owner_id"] == str(sources.owner) for item in records)
                >= MAX_OWNER_JOBS
            ):
                raise WorkspaceAccessError("checks_job_capacity", 429)
            sources.validate(stop, deadline)
            with self.catalog.open(sources.owner, sources.workspace) as current:
                if directory_context(current.fd) != sources.root:
                    raise WorkspaceAccessError("checks_source_changed", 409)
            self.runtime.validate(stop, deadline)
            identifier = uuid4()
            os.mkdir(identifier.hex, 0o700, dir_fd=self.storage.fd)
            os.fsync(self.storage.fd)
            with self.storage.directory(self.storage.fd, identifier.hex) as directory:
                os.mkdir("snapshot", 0o700, dir_fd=directory)
                os.fsync(directory)
                with self.storage.directory(directory, "snapshot") as snapshot:
                    for path, raw in sources.originals.items():
                        check_capture(stop, deadline)
                        with self.snapshot_parent(
                            snapshot, path, create=True
                        ) as parent:
                            self.storage.create_file(parent, path.split("/")[-1], raw)
                source = sources.metadata()
                snapshot = self.scan_snapshot(
                    directory, source, stop=stop, deadline=deadline
                )
                info = os.fstat(directory)
                core = dict(
                    description="Private immutable selected-source check job; no recovered action permission.",
                    version=1,
                    job_id=str(identifier),
                    owner_id=str(sources.owner),
                    workspace_id=str(sources.workspace),
                    profile=sources.profile.name,
                    source=source,
                    runtime=dict(
                        manifest_sha256=self.runtime.sha256,
                        native_version=self.runtime.version,
                        python_sha256=self.runtime.spec.python_sha256,
                        ruff_sha256=self.runtime.spec.ruff_sha256,
                        files=len(self.runtime.manifest["files"]),
                        allocated_bytes=self.runtime.allocated_bytes,
                    ),
                    snapshot=snapshot,
                    private_root=[info.st_dev, info.st_ino],
                    policy=execution_policy(self.cpu),
                    created_at_utc=datetime.now(timezone.utc).isoformat(),
                )
                validate_core(core, identifier)
                review = review_artifact(core)
                raw = encode_record(dict(**core, review_sha256=sha256(review)))
                self.storage.create_file(directory, "review.json", review)
                self.storage.create_file(directory, "manifest.json", raw)
                journal = dict(
                    description="Durable check attempt observations, never a recovered grant or quality certificate.",
                    job_id=str(identifier),
                    manifest_sha256=sha256(raw),
                    state="captured",
                    approval_id=None,
                    observation=None,
                    error_code=None,
                )
                self.storage.create_file(
                    directory, "journal.json", encode_record(journal)
                )
                self.allocated_job(directory)
                sources.validate(stop, deadline)
                os.fsync(directory)
                os.fsync(self.storage.fd)
            logger.info(
                "checks_job_captured job_id=%s files=%d",
                identifier,
                len(source["files"]),
            )
            return dict(
                identifier=identifier, review=review, manifest_sha256=sha256(raw)
            )

    def read(self, owner, workspace, identifier):
        """Return verified owner-only historical context/results without claiming live source state or recovering an old grant."""
        self.authorize(owner, workspace)
        with (
            self.operation(),
            self.job(identifier, owner, workspace) as (directory, core, journal, _, _),
        ):
            self.scan_snapshot(directory, core["source"], core["snapshot"])
            self.allocated_job(directory)
            warnings = (
                []
                if set(os.listdir(directory)) == JOB_MEMBERS
                else ["unacknowledged_private_entry"]
            )
            return deepcopy(
                dict(
                    job_id=str(identifier),
                    profile=core["profile"],
                    selected_files=[
                        dict(
                            path=item["path"], sha256=item["sha256"], size=item["size"]
                        )
                        for item in core["source"]["files"]
                    ],
                    source_version=core["source"]["source_version"],
                    runtime_manifest_sha256=core["runtime"]["manifest_sha256"],
                    runtime_version=core["runtime"]["native_version"],
                    state=journal["state"],
                    approval_id=journal["approval_id"],
                    observation=journal["observation"],
                    error_code=journal["error_code"],
                    recovery_warnings=warnings,
                    current_source_observed=False,
                    recovered_approval=False,
                    live_action_authority=False,
                )
            )

    def link_approval(self, owner, workspace, identifier, approval):
        """Durably link a newly created pending exact review without approving, consuming or starting any action."""
        self.authorize(owner, workspace)
        if type(approval) is not UUID:
            raise WorkspaceAccessError("checks_approval_invalid", 422)
        with (
            self.operation(),
            self.job(identifier, owner, workspace) as (
                directory,
                core,
                journal,
                digest,
                _,
            ),
        ):
            if journal["state"] != "captured" or journal["approval_id"] is not None:
                raise WorkspaceAccessError("checks_job_state_conflict", 409)
            journal.update(state="proposed", approval_id=str(approval))
            validate_journal(journal, core, digest)
            self.storage.replace_journal(directory, journal)
            self.allocated_job(directory)
            logger.info(
                "checks_pending_review_linked job_id=%s request_id=%s",
                identifier,
                approval,
            )

    def list(self, owner, workspace):
        """List only bounded authorized historical metadata without recovering grants or exposing foreign private snapshots."""
        self.authorize(owner, workspace)
        with self.operation():
            records = self.inventory()
            return [
                dict(
                    job_id=item["job_id"],
                    profile=item["profile"],
                    source_version=item["source"]["source_version"],
                    created_at_utc=item["created_at_utc"],
                    recovered_approval=False,
                )
                for item in records
                if item["owner_id"] == str(owner)
                and item["workspace_id"] == str(workspace)
            ]

    def require_approval(self, owner, workspace, approval, journal, review, approvals):
        """Require the exact already-approved linked owner/kind/content scope before validating or executing private code."""
        if type(approval) is not UUID or str(approval) != journal["approval_id"]:
            raise WorkspaceAccessError("checks_approval_changed", 409)
        scope = scope_for(owner, workspace, "run_checks", review)[0]
        value = approvals.review(owner, approval)
        if (
            value["state"] != "approved"
            or value["scope_digest"] != scope.digest
            or value["artifact"].encode("utf-8") != review
        ):
            raise WorkspaceAccessError("checks_approval_required", 409)

    def run_attempt(self, sources, identifier, approval, approvals, stop, evidence):
        """Consume one fresh exact grant only after durable intent/fresh fences and preserve observations before terminal publication."""
        owner, workspace = sources.owner, sources.workspace
        self.authorize(owner, workspace)
        with (
            self.operation(),
            self.job(identifier, owner, workspace) as (
                directory,
                core,
                journal,
                digest,
                review,
            ),
        ):
            if journal["state"] != "proposed":
                raise WorkspaceAccessError("checks_job_state_conflict", 409)
            self.require_approval(
                owner, workspace, approval, journal, review, approvals
            )
            native, error = None, None
            evidence.update(
                observation=None, terminal_persistence_uncertain=False, error_code=None
            )
            try:
                deadline = monotonic() + CAPTURE_SECONDS
                check_capture(stop, deadline)
                if encode_record(sources.metadata()) != encode_record(core["source"]):
                    raise WorkspaceAccessError("checks_source_changed", 409)
                sources.validate(stop, deadline)
                self.runtime.validate(stop, deadline)
                if (
                    core["runtime"]["manifest_sha256"] != self.runtime.sha256
                    or core["runtime"]["native_version"] != self.runtime.version
                    or encode_record(core["policy"])
                    != encode_record(execution_policy(self.cpu))
                ):
                    raise WorkspaceAccessError("checks_runtime_changed", 409)
                self.scan_snapshot(
                    directory, core["source"], core["snapshot"], stop, deadline
                )
                self.allocated_job(directory)
                if self.cpu not in os.sched_getaffinity(0):
                    raise WorkspaceAccessError(
                        "checks_runner_identity_or_cpu_invalid", 503
                    )
                journal["state"] = "starting"
                validate_journal(journal, core, digest)
                self.storage.replace_journal(directory, journal)
                sources.validate(stop, deadline)
                self.scan_snapshot(
                    directory, core["source"], core["snapshot"], stop, deadline
                )
                check_capture(stop, deadline)
                with self.storage.directory(directory, "snapshot") as snapshot:
                    approvals.consume(owner, approval, workspace, "run_checks", review)
                    native = NativeChecks(
                        snapshot,
                        self.runtime.fd,
                        core["profile"],
                        self.cpu,
                        identifier,
                        stop,
                    )
                    evidence["observation"] = native.observation
                    logger.info(
                        "checks_exact_grant_consumed job_id=%s request_id=%s",
                        identifier,
                        approval,
                    )
                    native.run()
            except BaseException as failure:
                error = failure
                evidence["error_code"] = getattr(failure, "code", "checks_interrupted")
            finally:
                try:
                    sources.close()
                except OSError:
                    if native is not None:
                        native.observation["cleanup_uncertain"] = True
                    evidence["error_code"] = (
                        evidence["error_code"] or "checks_source_pin_cleanup_uncertain"
                    )
                    logger.warning(
                        "checks_attempt_source_pin_cleanup_uncertain job_id=%s",
                        identifier,
                    )
                journal.update(
                    state="observed" if native is not None else "failed",
                    observation=deepcopy(native.observation)
                    if native is not None
                    else None,
                    error_code=evidence["error_code"],
                )
                try:
                    validate_journal(journal, core, digest)
                    self.storage.replace_journal(directory, journal)
                    self.allocated_job(directory)
                except BaseException:
                    evidence["terminal_persistence_uncertain"] = True
                    logger.warning(
                        "checks_terminal_journal_uncertain job_id=%s", identifier
                    )
            if error is not None:
                raise error
            return deepcopy(evidence)

    def retire_live(self, owner, workspace, identifier, state, error_code=None):
        """Record expiry/cancellation/failure without deleting snapshots, consuming grants or resuming an old intent."""
        self.authorize(owner, workspace)
        if state not in {"expired", "cancelled", "failed"}:
            raise WorkspaceAccessError("checks_job_state_conflict", 409)
        with (
            self.operation(),
            self.job(identifier, owner, workspace) as (
                directory,
                core,
                journal,
                digest,
                _,
            ),
        ):
            if journal["state"] not in {"captured", "proposed"}:
                raise WorkspaceAccessError("checks_job_state_conflict", 409)
            journal.update(state=state, error_code=error_code)
            validate_journal(journal, core, digest)
            self.storage.replace_journal(directory, journal)

    def close(self):
        """Close private pins only after admitted work joins, retaining every source snapshot/runtime/history byte."""
        if self.storage is None:
            return
        if not self.storage.admission.acquire(blocking=False):
            raise WorkspaceAccessError("checks_store_busy", 429)
        try:
            self.closing = True
            self.storage.closing = True
            if self.runtime is not None:
                self.runtime.close()
        finally:
            self.storage.admission.release()
            self.storage.close()
        logger.info("checks_job_store_closed")
