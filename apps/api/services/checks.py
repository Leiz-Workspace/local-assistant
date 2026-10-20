"""Own bounded fresh check approvals, process-local source pins and joined native execution without recovering historical action authority."""

import asyncio
import logging
import threading
from contextlib import asynccontextmanager
from copy import deepcopy
from dataclasses import dataclass, field
from time import monotonic
from uuid import UUID

from apps.api.services.files import file_io, finish_task
from apps.api.services.workspaces import joined_work
from src.application.services.approvals import scope_for
from src.application.services.check_policy import MAX_JOBS, PROPOSAL_SECONDS
from src.application.services.workspace_policy import WorkspaceAccessError
from src.infrastructure.check_sources import NativeCheckSources

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class LiveCheck:
    """Retain one ephemeral exact approval/source capability while durable job history never becomes execution permission."""

    owner: UUID
    workspace: UUID
    identifier: UUID
    sources: NativeCheckSources | None
    review: bytes
    approval: UUID
    scope_digest: str
    expires: float
    summary: dict
    state: str = "publishing"
    evidence: dict = field(default_factory=dict)
    stop: threading.Event | None = None
    finished: asyncio.Event = field(default_factory=asyncio.Event)


class CheckService:
    """Serialize trusted snapshot proposals/runs and drain every owned native/persistence operation before dependency teardown."""

    def __init__(self, workspace, approvals, store, *, clock=monotonic):
        """Own already-admitted local dependencies without registering roots, installing tools or enabling production execution."""
        self.workspace, self.approvals, self.store = workspace, approvals, store
        self.clock, self.records, self.operations = clock, {}, set()
        self.admission, self.closing = asyncio.Lock(), False
        logger.info("checks_service_initialized")

    def available(self):
        """Reject new work when any source/approval/storage dependency is closing."""
        if (
            self.closing
            or self.workspace.closing
            or self.approvals.closing
            or self.store.closing
        ):
            raise WorkspaceAccessError("checks_unavailable", 503)

    @asynccontextmanager
    async def tracked(self):
        """Retain an authenticated operation task through joined native cancellation and terminal publication."""
        self.available()
        task = asyncio.current_task()
        self.operations.add(task)
        try:
            yield
        finally:
            self.operations.discard(task)

    @asynccontextmanager
    async def operation(self):
        """Admit one nonqueued normal operation while cancellation may signal its own already-running job separately."""
        async with self.tracked():
            if self.admission.locked():
                raise WorkspaceAccessError("checks_busy", 429)
            await self.admission.acquire()
            try:
                yield threading.Event()
            finally:
                self.admission.release()
                logger.info("checks_operation_closed")

    def find(self, owner, workspace, identifier):
        """Authorize exact scope before expiry, cancellation or exposing an ephemeral record's existence."""
        self.available()
        self.store.authorize(owner, workspace)
        if type(identifier) is not UUID:
            raise WorkspaceAccessError("checks_job_not_found", 404)
        record = self.records.get(identifier)
        if record is not None and (
            record.owner != owner or record.workspace != workspace
        ):
            raise WorkspaceAccessError("checks_job_not_found", 404)
        return record

    async def close_sources(self, record):
        """Join source-pin closure once and record cleanup uncertainty without erasing known native results."""
        sources, record.sources = record.sources, None
        if sources is not None:
            try:
                await file_io(sources.close)
            except OSError:
                observation = record.evidence.get("observation")
                if observation is not None:
                    observation["cleanup_uncertain"] = True
                record.evidence["error_code"] = (
                    record.evidence.get("error_code")
                    or "checks_source_pin_cleanup_uncertain"
                )
                logger.warning(
                    "checks_source_cleanup_uncertain job_id=%s", record.identifier
                )

    async def expire(self, record):
        """Close an idle expired source capability without deleting durable history or changing an already-running result."""
        if record.state == "proposed" and self.clock() >= record.expires:
            record.state = "expired"
            await self.close_sources(record)
            try:
                await file_io(
                    self.store.retire_live,
                    record.owner,
                    record.workspace,
                    record.identifier,
                    "expired",
                )
            except Exception:
                record.state = "expired_persistence_uncertain"
                logger.warning(
                    "checks_expiry_journal_uncertain job_id=%s", record.identifier
                )
            record.finished.set()

    async def view(self, owner, workspace, identifier, stop, record=None):
        """Return owner-only known observations and distinguish private persisted state from an uncertain terminal acknowledgement."""
        try:
            value = await joined_work(
                stop, self.store.read, owner, workspace, identifier
            )
            value["persisted_state"] = value["state"]
        except Exception:
            if record is None:
                raise
            value = deepcopy(record.summary)
            value.update(
                persisted_state=None, recovery_warnings=["historical_read_unavailable"]
            )
            record.evidence["terminal_persistence_uncertain"] = True
        value["live_proposal"] = False
        value["terminal_persistence_uncertain"] = False
        if record is not None:
            value["state"] = record.state
            value["approval_id"] = str(record.approval)
            value["live_proposal"] = (
                record.state == "proposed" and record.sources is not None
            )
            value["terminal_persistence_uncertain"] = bool(
                record.evidence.get("terminal_persistence_uncertain")
            )
            if record.evidence.get("observation") is not None:
                value["observation"] = deepcopy(record.evidence["observation"])
            if record.evidence.get("error_code"):
                value["error_code"] = record.evidence["error_code"]
            if (
                value["terminal_persistence_uncertain"]
                and record.evidence.get("observation") is not None
            ):
                value["state"] = "observed_persistence_uncertain"
        return value

    async def propose(self, owner, workspace, profile, files):
        """Capture complete immutable selected sources/review and publish one new pending scope without approving or running it."""
        async with self.operation() as stop:
            self.store.authorize(owner, workspace)
            for existing in self.records.values():
                await self.expire(existing)
            if len(self.records) >= MAX_JOBS:
                raise WorkspaceAccessError("checks_job_capacity", 429)
            sources = await joined_work(
                stop,
                NativeCheckSources,
                self.workspace.catalog,
                owner,
                workspace,
                profile,
                files,
                stop,
                close_result=True,
            )
            record = None
            try:
                captured = await joined_work(stop, self.store.capture, sources, stop)
                expires = self.clock() + PROPOSAL_SECONDS
                approval = self.approvals.create(
                    owner, workspace, "run_checks", captured["review"]
                )
                identifier = captured["identifier"]
                summary = dict(
                    job_id=str(identifier),
                    profile=profile,
                    selected_files=[
                        dict(path=item.path, sha256=item.sha256, size=item.size)
                        for item in sources.receipts
                    ],
                    source_version=sources.version,
                    runtime_manifest_sha256=self.store.runtime.sha256,
                    runtime_version=self.store.runtime.version,
                    state="publishing",
                    approval_id=str(approval),
                    observation=None,
                    error_code=None,
                    recovery_warnings=[],
                    current_source_observed=False,
                    recovered_approval=False,
                    live_action_authority=False,
                )
                record = LiveCheck(
                    owner,
                    workspace,
                    identifier,
                    sources,
                    captured["review"],
                    approval,
                    scope_for(owner, workspace, "run_checks", captured["review"])[
                        0
                    ].digest,
                    expires,
                    summary,
                )
                self.records[identifier] = record
                await joined_work(
                    stop,
                    self.store.link_approval,
                    owner,
                    workspace,
                    identifier,
                    approval,
                )
                record.state = "proposed"
                logger.info(
                    "checks_pending_proposal_published job_id=%s request_id=%s",
                    identifier,
                    approval,
                )
                return await self.view(owner, workspace, identifier, stop, record)
            except BaseException:
                if record is not None:
                    record.state = "proposal_persistence_uncertain"
                    await self.close_sources(record)
                    record.finished.set()
                else:
                    await file_io(sources.close)
                raise

    def require_approval(self, record, identifier):
        """Require the exact already-approved ephemeral request before changing live job state or starting expensive validation."""
        if type(identifier) is not UUID or identifier != record.approval:
            raise WorkspaceAccessError("checks_approval_changed", 409)
        value = self.approvals.review(record.owner, identifier)
        if (
            value["state"] != "approved"
            or value["scope_digest"] != record.scope_digest
            or value["artifact"].encode("utf-8") != record.review
        ):
            raise WorkspaceAccessError("checks_approval_required", 409)

    async def run(self, owner, workspace, identifier, approval):
        """Join one freshly approved native attempt and preserve its known receipt before caller cancellation or response failure."""
        async with self.operation() as stop:
            record = self.find(owner, workspace, identifier)
            if record is None:
                await joined_work(stop, self.store.read, owner, workspace, identifier)
                raise WorkspaceAccessError("checks_job_not_live", 409)
            await self.expire(record)
            if record.state != "proposed" or record.sources is None:
                raise WorkspaceAccessError("checks_job_state_conflict", 409)
            self.require_approval(record, approval)
            record.state, record.stop = "running", stop
            record.finished.clear()
            try:
                await joined_work(
                    stop,
                    self.store.run_attempt,
                    record.sources,
                    identifier,
                    approval,
                    self.approvals,
                    stop,
                    record.evidence,
                )
            except BaseException as error:
                record.evidence["error_code"] = record.evidence.get(
                    "error_code"
                ) or getattr(error, "code", "checks_interrupted")
                raise
            finally:
                try:
                    await self.close_sources(record)
                finally:
                    record.state = (
                        "observed"
                        if record.evidence.get("observation") is not None
                        else "failed"
                    )
                    if record.evidence.get("terminal_persistence_uncertain"):
                        record.state += "_persistence_uncertain"
                    record.stop = None
                    record.finished.set()
            return await self.view(owner, workspace, identifier, stop, record)

    async def read(self, owner, workspace, identifier):
        """Read verified own historical/live state without inferring fresh source bytes or reconstructing an old approval."""
        async with self.operation() as stop:
            record = self.find(owner, workspace, identifier)
            if record is not None:
                await self.expire(record)
            return await self.view(owner, workspace, identifier, stop, record)

    async def list(self, owner, workspace):
        """List only authorized retained job metadata without reading or restoring ephemeral action permission."""
        async with self.operation() as stop:
            self.store.authorize(owner, workspace)
            return await joined_work(stop, self.store.list, owner, workspace)

    async def cancel(self, owner, workspace, identifier):
        """Signal only an authorized running job and wait for owned work to join, or close its idle pending capability."""
        async with self.tracked():
            record = self.find(owner, workspace, identifier)
            if record is not None and record.state == "running":
                record.stop.set()
                logger.info("checks_cancel_requested job_id=%s", identifier)
                await record.finished.wait()
                return await self.view(
                    owner, workspace, identifier, threading.Event(), record
                )
        async with self.operation() as stop:
            record = self.find(owner, workspace, identifier)
            if record is None:
                return await self.view(owner, workspace, identifier, stop)
            await self.expire(record)
            if record.state == "proposed":
                record.state = "cancelled"
                await self.close_sources(record)
                try:
                    await joined_work(
                        stop,
                        self.store.retire_live,
                        owner,
                        workspace,
                        identifier,
                        "cancelled",
                    )
                except Exception:
                    record.state = "cancelled_persistence_uncertain"
                    logger.warning(
                        "checks_cancel_journal_uncertain job_id=%s", identifier
                    )
                record.finished.set()
            return await self.view(owner, workspace, identifier, stop, record)

    async def shutdown(self):
        """Stop admission, cancel/join all owned operations and close sources/store before approval/workspace dependencies disappear."""
        self.closing = True
        tasks = [task for task in self.operations if task is not asyncio.current_task()]
        for record in self.records.values():
            if record.stop is not None:
                record.stop.set()
        for task in tasks:
            task.cancel()
        for task in tasks:
            try:
                await finish_task(task)
            except BaseException:
                logger.info("checks_cancelled_operation_joined")
        for record in self.records.values():
            await self.close_sources(record)
        try:
            await file_io(self.store.close)
        except OSError:
            logger.warning("checks_shutdown_storage_cleanup_uncertain")
        logger.info("checks_service_shutdown_complete")
