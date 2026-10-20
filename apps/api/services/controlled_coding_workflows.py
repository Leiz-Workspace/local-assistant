"""Add finite trusted hooks, discoverable progress, owner signal/join cancellation and one explicit pre-action proposal retry to accepted workflows."""

import asyncio
import logging
from contextlib import asynccontextmanager
from contextvars import ContextVar
from uuid import UUID

from apps.api.services.coding_workflows import CodingWorkflowService
from apps.api.services.files import finish_task
from apps.api.services.workflow_cancellation import retire_pending_patch
from src.application.services.workflow_controls import WorkflowLineage
from src.application.services.workspace_policy import WorkspaceAccessError

logger = logging.getLogger(__name__)
ACTION_STATES = {
    "applying": "apply",
    "capturing_checks": "capture_checks",
    "running_checks": "run_checks",
}


class ControlledCodingWorkflowService(CodingWorkflowService):
    """Keep all accepted domain actions while binding finite lineage/task ownership and cancellation outside normal action admission."""

    def __init__(self, workspace, approvals, patches, checks, *, inference=None):
        """Own only bounded process-local control metadata and task associations without opening roots or changing inference configuration."""
        super().__init__(workspace, approvals, patches, checks, inference=inference)
        self.controls, self.active_tasks = {}, {}
        self.cancel_requests, self.cancel_workers = set(), set()
        self.cancel_admission = asyncio.Lock()
        self.target_context = ContextVar("workflow_control_target", default=None)
        self.retry_context = ContextVar("workflow_control_retry", default=None)
        logger.info("controlled_workflow_service_initialized")

    def retryable(self, record):
        """Allow an explicit second proposal only before any component publication and before cancellation, without refunding an old attempt."""
        control = self.controls[record.identifier]
        if (
            record.value["state"] != "proposal_failed"
            or record.value["patch"] is not None
            or record.value["check"] is not None
            or control.cancel_requested
            or control.hook_uncertain
        ):
            raise WorkspaceAccessError("workflow_retry_not_allowed", 409)
        if len(control.lineage.members) >= 2:
            raise WorkspaceAccessError("workflow_retry_limit", 429)
        return control

    def register(self, record):
        """Bind a fresh proposal slot and exact owning task before the first capture await, preserving the original bounded record insertion."""
        parent_id = self.retry_context.get()
        if parent_id is None:
            lineage = WorkflowLineage(record.owner, record.workspace, record.identifier)
        else:
            parent = self.find(record.owner, record.workspace, parent_id)
            lineage = self.retryable(parent).lineage
        control = lineage.register(record.identifier, parent_id)
        control.before("proposal")
        super().register(record)
        self.controls[record.identifier] = control
        self.active_tasks[record.identifier] = asyncio.current_task()
        super().save(record, controls=control.snapshot())

    def save(self, record, **changes):
        """Run finite before-hooks only after accepted domain preconditions and keep every original terminal receipt update."""
        control = self.controls.get(record.identifier)
        if control is not None:
            stage = ACTION_STATES.get(changes.get("state"))
            if stage is not None:
                control.before(stage)
            changes["controls"] = control.snapshot()
        super().save(record, **changes)

    def component_uncertain(self, component):
        """Preserve trusted patch/check state, error and receipt uncertainty instead of upgrading native cleanup or unknown effects to clean completion."""
        if component is None:
            return False
        receipt = component.get("receipt")
        observation = component.get("observation")
        uncertain = any(
            "uncertain" in str(value)
            for value in (
                component.get("state"),
                component.get("error_code"),
                receipt.get("state") if receipt else None,
            )
        ) or bool(
            (receipt and receipt.get("applied") is None)
            or component.get("terminal_persistence_uncertain")
            or (observation and observation.get("cleanup_uncertain"))
        )
        logger.info("workflow_component_uncertainty_observed uncertain=%s", uncertain)
        return uncertain

    def stage_outcome(self, record, stage, error):
        """Classify supervisor-stage completion without equating exit zero or a model marker with functional quality."""
        value = record.value
        patch, check = value.get("patch"), value.get("check")
        observation = check.get("observation") if check else None
        if (
            value.get("source_cleanup_uncertain")
            or self.component_uncertain(patch)
            or self.component_uncertain(check)
        ):
            return "uncertain"
        if isinstance(error, asyncio.CancelledError):
            return "cancelled"
        expected = {
            "proposal": "awaiting_patch_review",
            "apply": "applied",
            "capture_checks": "awaiting_check_review",
            "run_checks": "completed",
        }
        if value["state"] != expected[stage] or (
            stage == "run_checks" and observation and observation["outcome"] != "exited"
        ):
            return "failed"
        return "completed"

    @asynccontextmanager
    async def operation(self, owner, workspace):
        """Associate only an admitted exact target task and finish its reserved hook before normal admission/pin ownership is released."""
        async with super().operation(owner, workspace) as stop:
            task = asyncio.current_task()
            target = self.target_context.get()
            if target is not None:
                self.find(owner, workspace, target)
                self.active_tasks[target] = task
            error = None
            try:
                yield stop
            except BaseException as failure:
                error = failure
                raise
            finally:
                owned = [
                    identifier
                    for identifier, value in self.active_tasks.items()
                    if value is task
                ]
                for identifier in owned:
                    record, control = (
                        self.records[identifier],
                        self.controls[identifier],
                    )
                    try:
                        for stage, state in tuple(control.actions.items()):
                            if state == "started":
                                control.after(
                                    stage, self.stage_outcome(record, stage, error)
                                )
                        super().save(record, controls=control.snapshot())
                    except BaseException as failure:
                        control.hook_uncertain = True
                        for stage, state in tuple(control.actions.items()):
                            if state == "started":
                                control.actions[stage] = "finished"
                        logger.warning(
                            "workflow_terminal_hook_uncertain workflow_id=%s",
                            identifier,
                        )
                        if not isinstance(failure, Exception):
                            raise
                    finally:
                        self.active_tasks.pop(identifier, None)

    def view(self, record):
        """Expose current bounded control counters with last-observed component receipts and no live source/approval authority."""
        value = super().view(record)
        control = self.controls.get(record.identifier)
        if control is not None:
            value["controls"] = control.snapshot()
        return self.record_copy(value)

    def record_copy(self, value):
        """Apply the accepted complete-record byte budget to added bounded controller metadata without returning aliases."""
        from src.application.services.coding_workflow import bounded_record

        return bounded_record(value)

    async def propose(self, owner, workspace, issue, target, tests, profile):
        """Create one ordinary finite proposal while leaving retry lineage selection solely to the trusted explicit retry method."""
        token = self.target_context.set(None)
        try:
            value = await super().propose(
                owner, workspace, issue, target, tests, profile
            )
            return self.view(self.records[UUID(value["workflow_id"])])
        finally:
            self.target_context.reset(token)

    async def targeted(self, method, owner, workspace, identifier, *arguments):
        """Bind one authorized existing workflow target only after normal admission succeeds, preventing unrelated-task cancellation."""
        self.find(owner, workspace, identifier)
        token = self.target_context.set(identifier)
        try:
            await method(owner, workspace, identifier, *arguments)
            return self.view(self.records[identifier])
        finally:
            self.target_context.reset(token)

    async def apply(self, owner, workspace, identifier, approval):
        """Preserve exact accepted patch approval/native semantics while associating the owner's admitted task with its workflow."""
        return await self.targeted(
            super().apply, owner, workspace, identifier, approval
        )

    async def propose_checks(self, owner, workspace, identifier):
        """Preserve known-applied target/test-hash capture and a separate pending check review without automatic execution."""
        return await self.targeted(super().propose_checks, owner, workspace, identifier)

    async def run_checks(self, owner, workspace, identifier, approval):
        """Preserve exact one-shot native check approval/receipts while associating owned cancellation and finite hooks."""
        return await self.targeted(
            super().run_checks, owner, workspace, identifier, approval
        )

    async def retry_proposal(self, owner, workspace, identifier):
        """Explicitly reserve at most one new failed-proposal lineage member with unchanged options and fresh native source/review identities."""
        record = self.find(owner, workspace, identifier)
        self.retryable(record)
        token = self.retry_context.set(identifier)
        try:
            files = record.options.selections()
            return await self.propose(
                owner,
                workspace,
                record.options.issue,
                files[0],
                files[1:],
                record.options.profile,
            )
        finally:
            self.retry_context.reset(token)

    async def read(self, owner, workspace, identifier):
        """Read only authorized bounded last-observed metadata during generation without queuing or touching native sources/grants."""
        return self.view(self.find(owner, workspace, identifier))

    async def list(self, owner, workspace):
        """Discover only bounded own workflow identities/states so active generation can be cancelled by exact ID."""
        self.authorize(owner, workspace)
        return [
            dict(workflow_id=str(record.identifier), state=record.value["state"])
            for record in self.records.values()
            if record.owner == owner and record.workspace == workspace
        ]

    async def cancel_owned(self, record):
        """Join only the associated task then retire linked idle capabilities, preserving actual commits/observations and busy uncertainty."""
        control = self.controls[record.identifier]
        control.begin_cancel()
        super().save(record, cancel_status="requested", controls=control.snapshot())
        task = self.active_tasks.get(record.identifier)
        if task is not None and task is not asyncio.current_task():
            task.cancel()
            try:
                await finish_task(task)
            except BaseException:
                logger.info(
                    "workflow_cancel_owned_stage_joined workflow_id=%s",
                    record.identifier,
                )
        uncertain = (
            bool(record.value.get("source_cleanup_uncertain")) or control.hook_uncertain
        )
        try:
            patch = record.value.get("patch")
            if patch is not None:
                patch, patch_uncertain = await retire_pending_patch(
                    self.patches,
                    record.owner,
                    record.workspace,
                    UUID(patch["proposal_id"]),
                )
                uncertain = (
                    uncertain or patch_uncertain or self.component_uncertain(patch)
                )
                super().save(record, patch=patch)
            check = record.value.get("check")
            if check is not None:
                check = await self.checks.cancel(
                    record.owner, record.workspace, UUID(check["job_id"])
                )
                uncertain = uncertain or self.component_uncertain(check)
                super().save(record, check=check)
        except WorkspaceAccessError:
            super().save(
                record,
                cancel_status="waiting_for_component",
                controls=control.snapshot(),
            )
            raise
        except Exception:
            uncertain = True
            logger.warning(
                "workflow_cancel_component_cleanup_uncertain workflow_id=%s",
                record.identifier,
            )
        try:
            control.finish_cancel("uncertain" if uncertain else "completed")
        except Exception:
            control.hook_uncertain = True
            control.cancel_finished = True
            uncertain = True
            logger.warning(
                "workflow_cancel_terminal_hook_uncertain workflow_id=%s",
                record.identifier,
            )
        super().save(
            record,
            state="cancelled",
            cancel_status="cleanup_uncertain" if uncertain else "completed",
            controls=control.snapshot(),
        )
        return self.view(record)

    async def cancel(self, owner, workspace, identifier):
        """Authorize a separate nonqueued owner cancellation and join its owned cleanup even when response/request cancellation loses acknowledgement."""
        record = self.find(owner, workspace, identifier)
        control = self.controls[identifier]
        if control.cancel_finished:
            return self.view(record)
        if record.value["state"] == "completed" and identifier not in self.active_tasks:
            super().save(record, cancel_status="already_terminal")
            return self.view(record)
        if self.cancel_admission.locked():
            raise WorkspaceAccessError("workflow_cancel_busy", 429)
        await self.cancel_admission.acquire()
        request = asyncio.current_task()
        self.cancel_requests.add(request)
        cleanup = None
        pending = self.cancel_owned(record)
        try:
            try:
                cleanup = asyncio.create_task(pending)
            except BaseException:
                pending.close()
                logger.warning("workflow_cancel_task_creation_failed")
                raise
            self.cancel_workers.add(cleanup)
            return await asyncio.shield(cleanup)
        except asyncio.CancelledError:
            if cleanup is not None:
                try:
                    await finish_task(cleanup)
                except BaseException:
                    logger.info(
                        "workflow_cancel_request_cleanup_joined workflow_id=%s",
                        identifier,
                    )
            raise
        finally:
            self.cancel_workers.discard(cleanup)
            self.cancel_requests.discard(request)
            self.cancel_admission.release()

    async def shutdown(self):
        """Stop admission and join normal/cancellation work without closing shared native/approval/source dependencies prematurely."""
        self.closing = True
        current = asyncio.current_task()
        tasks = [
            task
            for task in self.operations | self.cancel_requests
            if task is not current
        ]
        for task in tasks:
            task.cancel()
        for task in tasks:
            try:
                await finish_task(task)
            except BaseException:
                logger.info("controlled_workflow_shutdown_request_joined")
        for task in tuple(self.cancel_workers):
            try:
                await finish_task(task)
            except BaseException:
                logger.info("controlled_workflow_shutdown_cleanup_joined")
        logger.info("controlled_workflow_shutdown_complete")
