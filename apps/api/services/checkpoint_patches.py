"""Compose accepted exact approved edits with durable private Git checkpoints and freshly approved byte-only rollback proposals."""

import asyncio
import logging

from apps.api.services.files import file_io
from apps.api.services.patches import PatchService
from apps.api.services.workspaces import joined_work
from src.application.services.workspace_policy import WorkspaceAccessError
from src.infrastructure.checkpoint_recovery import observe_checkpoint

logger = logging.getLogger(__name__)


class CheckpointPatchService(PatchService):
    """Retain checkpoint IDs and durable action evidence around unchanged native D40 commit/approval semantics."""

    def __init__(self, workspace, approvals, store):
        """Own one already-admitted private checkpoint store without enabling host roots, commands or model writes."""
        super().__init__(workspace, approvals)
        self.checkpoint_store = store
        self.links = {}
        self.restores = {}
        self.started = set()
        logger.info("checkpoint_patch_service_initialized")

    async def prepare_proposal(self, proposal, stop, restore_checkpoint):
        """Capture the exact admitted original before pending approval publication, validating any historical restore context first."""
        self.links = {
            key: value for key, value in self.links.items() if key in self.records
        }
        self.restores = {
            key: value for key, value in self.restores.items() if key in self.records
        }
        if restore_checkpoint is not None:
            snapshot = await joined_work(
                stop,
                self.checkpoint_store.read,
                proposal.owner,
                proposal.workspace,
                restore_checkpoint,
                stop,
            )
            metadata = snapshot["metadata"]
            if (
                metadata["path"] != proposal.path
                or metadata["root"] != list(proposal.metadata["root"])
                or metadata["base_sha256"] != proposal.new_sha256
            ):
                raise WorkspaceAccessError("checkpoint_restore_context_changed", 409)
            self.restores[proposal.identifier] = restore_checkpoint
        identifier = await joined_work(
            stop, self.checkpoint_store.capture, proposal, stop
        )
        self.links[proposal.identifier] = identifier
        logger.info(
            "checkpoint_patch_linked proposal_id=%s checkpoint_id=%s",
            proposal.identifier,
            identifier,
        )

    async def before_apply(self, proposal, stop):
        """Verify the private source checkpoint and durably publish intent before any native workspace temporary write."""
        identifier = self.links[proposal.identifier]
        await joined_work(
            stop, self.checkpoint_store.transition, proposal, identifier, stop
        )
        self.started.add(proposal.identifier)
        logger.info("checkpoint_patch_intent_ready proposal_id=%s", proposal.identifier)

    async def after_apply(self, proposal):
        """Attempt terminal evidence after joined native work/cancellation while preserving actual applied or uncertain commit status."""
        if proposal.identifier not in self.started:
            return
        try:
            await file_io(
                self.checkpoint_store.transition,
                proposal,
                self.links[proposal.identifier],
                finish=True,
            )
        except (Exception, asyncio.CancelledError) as error:
            if proposal.receipt is not None:
                proposal.record_commit(
                    "applied_checkpoint_uncertain"
                    if proposal.receipt["applied"] is True
                    else "outcome_unknown",
                    applied=proposal.receipt["applied"],
                )
            else:
                proposal.error_code = (
                    proposal.error_code or "checkpoint_journal_uncertain"
                )
            logger.warning(
                "checkpoint_patch_terminal_journal_uncertain proposal_id=%s",
                proposal.identifier,
            )
            if isinstance(error, asyncio.CancelledError):
                raise
        finally:
            self.started.discard(proposal.identifier)

    def record_view(self, proposal):
        """Add only historical checkpoint/restore identities without widening the accepted native proposal/approval artifact."""
        value = proposal.public()
        value["checkpoint_id"] = str(self.links[proposal.identifier])
        value["restores_checkpoint_id"] = (
            str(self.restores[proposal.identifier])
            if proposal.identifier in self.restores
            else None
        )
        return value

    async def checkpoint(self, owner, workspace, identifier):
        """Read verified owner-only historical bytes/journal under request-owned joined private storage admission."""
        async with self.operation() as stop:
            return await joined_work(
                stop, self.checkpoint_store.read, owner, workspace, identifier, stop
            )

    async def checkpoints(self, owner, workspace):
        """List only the authorized bounded checkpoint metadata without disclosing foreign IDs or recovering grants."""
        async with self.operation() as stop:
            return await joined_work(stop, self.checkpoint_store.list, owner, workspace)

    async def rollback(self, owner, workspace, identifier, expected_sha256):
        """Create a fresh complete byte-restore proposal requiring a new explicit approval; never apply or reuse a historical grant."""
        snapshot = await self.checkpoint(owner, workspace, identifier)
        return await self.propose(
            owner,
            workspace,
            snapshot["metadata"]["path"],
            expected_sha256,
            snapshot["original"],
            restore_checkpoint=identifier,
        )

    async def inspect_recovery(self, owner, workspace, identifier):
        """Inspect verified history and fresh native source without resuming old edits, deleting unknown entries or creating approvals."""
        async with self.operation() as stop:
            snapshot = await joined_work(
                stop, self.checkpoint_store.read, owner, workspace, identifier, stop
            )
            return await joined_work(
                stop,
                observe_checkpoint,
                self.workspace.catalog,
                owner,
                workspace,
                snapshot,
                stop,
            )

    async def shutdown(self):
        """Drain all checkpoint/native operations and close private storage only after every writer/pin has joined."""
        await super().shutdown()
        try:
            await file_io(self.checkpoint_store.close)
        except OSError:
            logger.warning("checkpoint_patch_shutdown_storage_cleanup_uncertain")
        logger.info("checkpoint_patch_shutdown_complete")
