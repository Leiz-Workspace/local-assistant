"""Own bounded process-local patch proposals and join approved native writes before releasing retained source pins."""

import asyncio
import logging
import threading
from contextlib import asynccontextmanager
from uuid import UUID

from apps.api.services.files import file_io, finish_task
from apps.api.services.workspaces import joined_work
from src.application.services.patch_policy import MAX_PROPOSALS
from src.application.services.workspace_policy import WorkspaceAccessError
from src.infrastructure.atomic_patch import NativePatch

logger = logging.getLogger(__name__)


class PatchService:
    """Serialize trusted owner edits with bounded historical receipts and dependency-ordered descriptor ownership."""

    def __init__(self, workspace, approvals):
        """Bind accepted local scope and explicit approval services without opening roots or enabling model writes."""
        self.workspace = workspace
        self.approvals = approvals
        self.records = {}
        self.admission = asyncio.Lock()
        self.operations = set()
        self.closing = False

    def available(self):
        """Reject new requests during local or dependency teardown before opening or changing filesystem state."""
        if self.closing or self.workspace.closing or self.approvals.closing:
            raise WorkspaceAccessError("patch_unavailable", 503)

    def find(self, owner, workspace, identifier):
        """Authorize typed owner/workspace before expiry, pin cleanup or exposing a proposal's existence."""
        self.available()
        proposal = self.records.get(identifier) if type(identifier) is UUID else None
        if (
            proposal is None
            or type(owner) is not UUID
            or type(workspace) is not UUID
            or proposal.owner != owner
            or proposal.workspace != workspace
        ):
            raise WorkspaceAccessError("patch_not_found", 404)
        return proposal

    async def expire(self, proposal):
        """Release an idle expired pin without changing an applying or already committed historical result."""
        if proposal.state == "proposed" and proposal.clock() >= proposal.expires:
            proposal.state = "expired"
            await file_io(proposal.close)
            logger.info("patch_proposal_expired proposal_id=%s", proposal.identifier)

    @asynccontextmanager
    async def operation(self):
        """Admit one nonqueued operation and retain its task until all owned native work has joined."""
        self.available()
        if self.admission.locked():
            raise WorkspaceAccessError("patch_busy", 429)
        await self.admission.acquire()
        task = asyncio.current_task()
        self.operations.add(task)
        try:
            yield threading.Event()
        finally:
            self.operations.discard(task)
            self.admission.release()
            logger.info("patch_operation_closed")

    async def prepare_proposal(self, proposal, stop, restore_checkpoint):
        """Preserve ephemeral D40 behavior through a trusted optional durable-checkpoint composition hook."""
        if restore_checkpoint is not None:
            raise WorkspaceAccessError("checkpoint_unavailable", 503)
        logger.info("patch_ephemeral_proposal_prepared")

    async def before_apply(self, proposal, stop):
        """Preserve the accepted ephemeral D40 pre-commit behavior without creating a checkpoint journal."""
        logger.info("patch_ephemeral_apply_prepared")

    async def after_apply(self, proposal):
        """Preserve the accepted ephemeral D40 result while allowing trusted durable receipt composition."""
        logger.info("patch_ephemeral_apply_finalized")

    def record_view(self, proposal):
        """Preserve the accepted historical D40 response through an optional checkpoint identity presentation hook."""
        return proposal.public()

    async def propose(
        self,
        owner,
        workspace,
        path,
        expected_sha256,
        replacement,
        *,
        restore_checkpoint=None,
    ):
        """Capture a complete native read-only proposal and register its pending exact review without applying it."""
        async with self.operation() as stop:
            if not any(
                spec.owner_id == owner
                and spec.workspace_id == workspace
                and type(owner) is UUID
                and type(workspace) is UUID
                for spec in self.workspace.catalog.specifications
            ):
                raise WorkspaceAccessError("patch_not_found", 404)
            for record in tuple(self.records.values()):
                await self.expire(record)
            if len(self.records) >= MAX_PROPOSALS:
                retired = next(
                    (key for key, record in self.records.items() if record.closed),
                    None,
                )
                if retired is None:
                    raise WorkspaceAccessError("patch_capacity", 429)
                del self.records[retired]
            proposal = await joined_work(
                stop,
                NativePatch,
                self.workspace.catalog,
                owner,
                workspace,
                path,
                expected_sha256,
                replacement,
                stop,
                close_result=True,
            )
            try:
                await self.prepare_proposal(proposal, stop, restore_checkpoint)
                proposal.register_approval(self.approvals)
                self.records[proposal.identifier] = proposal
                logger.info(
                    "patch_proposal_registered proposal_id=%s", proposal.identifier
                )
                return self.record_view(proposal)
            except BaseException:
                await file_io(proposal.close)
                raise

    async def review(self, owner, workspace, identifier):
        """Return an authorized historical snapshot, closing only its own expired idle root pin."""
        async with self.operation():
            proposal = self.find(owner, workspace, identifier)
            await self.expire(proposal)
            return self.record_view(proposal)

    async def apply(self, owner, workspace, identifier, approval):
        """Join the native one-shot edit and retain its authoritative receipt even when the caller loses acknowledgement."""
        async with self.operation() as stop:
            proposal = self.find(owner, workspace, identifier)
            await self.expire(proposal)
            if proposal.state != "proposed":
                raise WorkspaceAccessError("patch_state_conflict", 409)
            proposal.require_approval(self.approvals, approval)
            try:
                await self.before_apply(proposal, stop)
                await joined_work(stop, proposal.apply, self.approvals, approval, stop)
            except BaseException as error:
                if proposal.state == "proposed":
                    proposal.state = "failed"
                    proposal.error_code = getattr(error, "code", "patch_interrupted")
                raise
            finally:
                try:
                    try:
                        await file_io(proposal.close)
                    except OSError:
                        if proposal.receipt is not None:
                            proposal.record_commit(
                                "applied_cleanup_uncertain"
                                if proposal.receipt["applied"] is True
                                else "outcome_unknown",
                                applied=proposal.receipt["applied"],
                            )
                        else:
                            proposal.state = "failed"
                            proposal.error_code = "patch_pin_cleanup_uncertain"
                        logger.warning(
                            "patch_pin_cleanup_uncertain proposal_id=%s", identifier
                        )
                    if proposal.state == "proposed" and proposal.closed:
                        proposal.state = "failed"
                        proposal.error_code = "patch_interrupted"
                finally:
                    await self.after_apply(proposal)
            return self.record_view(proposal)

    async def shutdown(self):
        """Reject new work, cancel/join active writers and close all pins before approval/workspace teardown."""
        self.closing = True
        tasks = [task for task in self.operations if task is not asyncio.current_task()]
        for task in tasks:
            task.cancel()
        for task in tasks:
            try:
                await finish_task(task)
            except BaseException:
                logger.info("patch_shutdown_operation_joined")
        for proposal in self.records.values():
            try:
                await file_io(proposal.close)
            except OSError:
                logger.warning(
                    "patch_shutdown_pin_cleanup_uncertain proposal_id=%s",
                    proposal.identifier,
                )
        logger.info("patch_shutdown_complete")
