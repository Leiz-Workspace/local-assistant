"""Compose one source-selected CORE proposal with separately approved checkpoint edits and snapshot checks while preserving actual receipts."""

import asyncio
import base64
import hashlib
import logging
import threading
from contextlib import asynccontextmanager
from dataclasses import dataclass
from uuid import UUID, uuid4

from apps.api.services.files import file_io, finish_task
from apps.api.services.workspaces import joined_work
from src.application.ports.inference import CompletionResult
from src.application.services.coding_workflow import (
    MAX_OWNER_RECORDS,
    MAX_RECORDS,
    MODEL_SECONDS,
    MODEL_TOKENS,
    WorkflowOptions,
    bounded_record,
    resolve_candidate,
    workflow_messages,
    workflow_options,
)
from src.application.services.workspace_policy import WorkspaceAccessError
from src.infrastructure.check_sources import NativeCheckSources
from src.infrastructure.inference.llama_adapter import LlamaInferenceAdapter

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class WorkflowRecord:
    """Retain one process-local owner's immutable options and bounded historical component/attempt data without recovering grants."""

    owner: UUID
    workspace: UUID
    identifier: UUID
    options: WorkflowOptions
    value: dict


class CodingWorkflowService:
    """Own a finite nonretrying proposal/apply/check composition without bypassing native component approval or lifecycle rules."""

    def __init__(self, workspace, approvals, patches, checks, *, inference=None):
        """Bind existing live services and the established CORE adapter without opening storage or changing model configuration."""
        self.workspace, self.approvals, self.patches, self.checks = (
            workspace,
            approvals,
            patches,
            checks,
        )
        self.inference = inference if inference is not None else LlamaInferenceAdapter()
        self.records, self.operations = {}, set()
        self.admission, self.closing = asyncio.Lock(), False
        logger.info("coding_workflow_service_initialized")

    def available(self):
        """Reject new work before any source access when this service or a required dependency is closing."""
        if self.closing or any(
            value.closing
            for value in (self.workspace, self.approvals, self.patches, self.checks)
        ):
            raise WorkspaceAccessError("workflow_unavailable", 503)

    def authorize(self, owner, workspace):
        """Authorize exact typed configured owner/workspace scope before lookup, quota inspection or model work."""
        self.available()
        if (
            type(owner) is not UUID
            or type(workspace) is not UUID
            or not any(
                spec.owner_id == owner and spec.workspace_id == workspace
                for spec in self.workspace.catalog.specifications
            )
        ):
            raise WorkspaceAccessError("workflow_not_found", 404)

    @asynccontextmanager
    async def operation(self, owner, workspace):
        """Admit one authenticated nonqueued stage and retain its task through joined model/native cancellation."""
        self.authorize(owner, workspace)
        if self.admission.locked():
            raise WorkspaceAccessError("workflow_busy", 429)
        await self.admission.acquire()
        task = asyncio.current_task()
        self.operations.add(task)
        try:
            yield threading.Event()
        finally:
            self.operations.discard(task)
            self.admission.release()
            logger.info("coding_workflow_operation_closed")

    def find(self, owner, workspace, identifier):
        """Mask unknown and foreign workflow records uniformly without side effects or component access."""
        self.authorize(owner, workspace)
        record = self.records.get(identifier) if type(identifier) is UUID else None
        if record is None or record.owner != owner or record.workspace != workspace:
            raise WorkspaceAccessError("workflow_not_found", 404)
        return record

    def save(self, record, **changes):
        """Commit only bounded owned JSON state and retain the previous record if a proposed update exceeds its budget."""
        record.value = bounded_record(record.value | changes)
        logger.info(
            "coding_workflow_state_recorded workflow_id=%s state=%s",
            record.identifier,
            record.value["state"],
        )

    def view(self, record):
        """Build a truthful snapshot-bound summary from known component receipts without model-generated quality claims."""
        value = bounded_record(record.value)
        patch, check = value.get("patch"), value.get("check")
        receipt = patch.get("receipt") if patch else None
        observation = check.get("observation") if check else None
        value["summary"] = dict(
            edit_applied=receipt.get("applied") if receipt else False,
            applied_sha256=patch["new_sha256"]
            if receipt and receipt.get("applied") is True
            else None,
            checkpoint_id=patch.get("checkpoint_id") if patch else None,
            tested_source_version=check.get("source_version") if check else None,
            native_started=observation.get("started_acknowledged")
            if observation
            else False,
            native_outcome=observation.get("outcome") if observation else None,
            native_exit_code=observation.get("exit_code") if observation else None,
            current_source_observed=False,
            quality_evaluated=False,
            output_is_untrusted=True,
            summary_source="trusted_component_receipts",
        )
        return bounded_record(value)

    def error(self, record, error):
        """Record only a bounded stable failure code without logging source, model text, credentials or exception messages."""
        code = (
            error.code
            if isinstance(error, WorkspaceAccessError)
            else "workflow_interrupted"
        )
        self.save(record, error_code=code)
        logger.warning(
            "coding_workflow_stage_failed workflow_id=%s code=%s",
            record.identifier,
            code,
        )

    async def complete(self, record, messages):
        """Own one fixed existing CORE attempt and preserve bounded received bytes before validating its completion contract."""
        self.save(record, model_attempted=True)
        work = asyncio.create_task(
            self.inference.complete(
                profile="core",
                messages=messages,
                preset="fast",
                temperature=0,
                max_tokens=MODEL_TOKENS,
            )
        )
        try:
            result = await asyncio.wait_for(asyncio.shield(work), MODEL_SECONDS)
            if (
                not isinstance(result, CompletionResult)
                or type(result.content) is not str
            ):
                raise WorkspaceAccessError("workflow_model_invalid", 503)
            try:
                raw = result.content.encode("utf-8")
            except UnicodeError:
                self.save(
                    record,
                    model_observation=dict(
                        completion_received=True, valid_unicode=False
                    ),
                )
                raise WorkspaceAccessError("workflow_model_invalid", 503) from None
            prefix = raw[:16384]
            self.save(
                record,
                model_observation=dict(
                    completion_received=True,
                    model_id=str(result.model_id)[:256],
                    preset_selected=str(result.preset_selected)[:32],
                    finish_reason=str(result.finish_reason)[:32],
                    raw_bytes=len(raw),
                    raw_sha256=hashlib.sha256(raw).hexdigest(),
                    raw_prefix_base64=base64.b64encode(prefix).decode("ascii"),
                    prefix_bytes=len(prefix),
                    prefix_sha256=hashlib.sha256(prefix).hexdigest(),
                    prefix_encoding="base64",
                    valid_unicode=True,
                    prefix_truncated=len(raw) > 16384,
                ),
            )
            if result.finish_reason != "stop" or result.preset_selected != "fast":
                raise WorkspaceAccessError("workflow_model_incomplete", 503)
            return resolve_candidate(result.content)
        except TimeoutError:
            raise WorkspaceAccessError("workflow_model_timeout", 504) from None
        finally:
            if not work.done():
                work.cancel()
            try:
                await finish_task(work)
            except BaseException:
                logger.info(
                    "coding_workflow_model_joined workflow_id=%s", record.identifier
                )

    async def propose(self, owner, workspace, issue, target, tests, profile):
        """Read exact selected context, request one untrusted CORE proposal and publish a pending checkpoint-backed diff without applying it."""
        async with self.operation(owner, workspace) as stop:
            options = workflow_options(issue, target, tests, profile)
            if (
                len(self.records) >= MAX_RECORDS
                or sum(row.owner == owner for row in self.records.values())
                >= MAX_OWNER_RECORDS
            ):
                raise WorkspaceAccessError("workflow_capacity", 429)
            identifier = uuid4()
            record = WorkflowRecord(
                owner,
                workspace,
                identifier,
                options,
                bounded_record(
                    dict(
                        workflow_id=str(identifier),
                        owner_id=str(owner),
                        workspace_id=str(workspace),
                        issue=options.issue,
                        profile=options.profile,
                        selected_files=options.selections(),
                        state="generating",
                        plan=[],
                        plan_trust="not_generated",
                        model_attempted=False,
                        model_observation=None,
                        source_version=None,
                        patch=None,
                        check=None,
                        apply_attempted=False,
                        check_proposal_attempted=False,
                        check_attempted=False,
                        error_code=None,
                        source_cleanup_uncertain=False,
                        recovered_approval=False,
                        live_action_authority=False,
                    )
                ),
            )
            self.records[identifier] = record
            sources = None
            try:
                sources = await joined_work(
                    stop,
                    NativeCheckSources,
                    self.workspace.catalog,
                    owner,
                    workspace,
                    options.profile,
                    options.selections(),
                    stop,
                    close_result=True,
                )
                self.save(record, source_version=sources.version)
                messages = workflow_messages(options, sources.originals)
                candidate = await self.complete(record, messages)
                self.save(
                    record, plan=candidate["plan"], plan_trust="generated_untrusted"
                )
                if (
                    hashlib.sha256(candidate["replacement"].encode("utf-8")).hexdigest()
                    == options.files[0][1]
                ):
                    raise WorkspaceAccessError("workflow_no_change", 409)
                await joined_work(stop, sources.validate, stop)
                patch = await self.patches.propose(
                    owner,
                    workspace,
                    options.files[0][0],
                    options.files[0][1],
                    candidate["replacement"],
                )
                self.save(record, patch=patch, state="publishing_patch")
                await joined_work(stop, sources.validate, stop)
                self.save(record, state="awaiting_patch_review")
            except BaseException as error:
                self.error(record, error)
                self.save(
                    record,
                    state="cancelled"
                    if isinstance(error, asyncio.CancelledError)
                    else "proposal_failed",
                )
                if not isinstance(error, Exception):
                    raise
            finally:
                if sources is not None:
                    try:
                        await file_io(sources.close)
                    except OSError:
                        self.save(
                            record,
                            source_cleanup_uncertain=True,
                            state="proposal_cleanup_uncertain",
                        )
                        logger.warning(
                            "coding_workflow_source_cleanup_uncertain workflow_id=%s",
                            identifier,
                        )
            return self.view(record)

    def require_stage_approval(self, record, approval, component, kind):
        """Check only the exact already-approved linked component request before changing workflow attempt/state flags."""
        if type(approval) is not UUID or str(approval) != component["approval_id"]:
            raise WorkspaceAccessError("workflow_approval_changed", 409)
        value = self.approvals.review(record.owner, approval)
        if (
            value["state"] != "approved"
            or value["kind"] != kind
            or value["workspace_id"] != str(record.workspace)
        ):
            raise WorkspaceAccessError("workflow_approval_required", 409)

    async def apply(self, owner, workspace, identifier, approval):
        """Apply only the linked explicitly approved checkpoint proposal once and retain actual commit evidence on failure/cancellation."""
        async with self.operation(owner, workspace):
            record = self.find(owner, workspace, identifier)
            if (
                record.value["state"] != "awaiting_patch_review"
                or record.value["apply_attempted"]
            ):
                raise WorkspaceAccessError("workflow_state_conflict", 409)
            self.require_stage_approval(
                record, approval, record.value["patch"], "patch"
            )
            proposal = UUID(record.value["patch"]["proposal_id"])
            native = self.patches.find(owner, workspace, proposal)
            await self.patches.expire(native)
            native.require_approval(self.approvals, approval)
            self.save(record, state="applying", apply_attempted=True)
            try:
                await self.patches.apply(owner, workspace, proposal, approval)
            except BaseException as error:
                self.error(record, error)
                if not isinstance(error, Exception):
                    raise
            finally:
                patch = self.patches.record_view(native)
                applied = patch["receipt"] and patch["receipt"].get("applied") is True
                self.save(
                    record, patch=patch, state="applied" if applied else "edit_failed"
                )
            return self.view(record)

    async def propose_checks(self, owner, workspace, identifier):
        """Capture the known applied target hash plus original selected test hashes and publish a separate pending check approval without execution."""
        async with self.operation(owner, workspace):
            record = self.find(owner, workspace, identifier)
            if (
                record.value["state"] != "applied"
                or record.value["check_proposal_attempted"]
            ):
                raise WorkspaceAccessError("workflow_state_conflict", 409)
            patch = record.value["patch"]
            if not patch["receipt"] or patch["receipt"].get("applied") is not True:
                raise WorkspaceAccessError("workflow_applied_receipt_required", 409)
            files = record.options.selections()
            files[0]["expected_sha256"] = patch["new_sha256"]
            self.save(record, state="capturing_checks", check_proposal_attempted=True)
            try:
                check = await self.checks.propose(
                    owner, workspace, record.options.profile, files
                )
                self.save(record, check=check, state="awaiting_check_review")
            except BaseException as error:
                self.error(record, error)
                self.save(record, state="check_proposal_failed")
                if not isinstance(error, Exception):
                    raise
            return self.view(record)

    async def run_checks(self, owner, workspace, identifier, approval):
        """Run only the separately approved linked immutable snapshot once while preserving actual native results through cancellation."""
        async with self.operation(owner, workspace):
            record = self.find(owner, workspace, identifier)
            if (
                record.value["state"] != "awaiting_check_review"
                or record.value["check_attempted"]
            ):
                raise WorkspaceAccessError("workflow_state_conflict", 409)
            self.require_stage_approval(
                record, approval, record.value["check"], "run_checks"
            )
            job = UUID(record.value["check"]["job_id"])
            live = self.checks.find(owner, workspace, job)
            if live is None:
                raise WorkspaceAccessError("workflow_check_not_live", 409)
            await self.checks.expire(live)
            self.checks.require_approval(live, approval)
            self.save(record, state="running_checks", check_attempted=True)
            try:
                await self.checks.run(owner, workspace, job, approval)
            except BaseException as error:
                self.error(record, error)
                if not isinstance(error, Exception):
                    raise
            finally:
                check = await self.checks.view(
                    owner, workspace, job, threading.Event(), live
                )
                self.save(
                    record,
                    check=check,
                    state="completed"
                    if check.get("observation") is not None
                    else "check_failed",
                )
            return self.view(record)

    async def read(self, owner, workspace, identifier):
        """Read only bounded own last-observed workflow/component history without recovering approval or claiming current source state."""
        async with self.operation(owner, workspace):
            return self.view(self.find(owner, workspace, identifier))

    async def list(self, owner, workspace):
        """List bounded own workflow identities/states without exposing foreign issue/source/model contents."""
        async with self.operation(owner, workspace):
            return [
                dict(workflow_id=str(row.identifier), state=row.value["state"])
                for row in self.records.values()
                if row.owner == owner and row.workspace == workspace
            ]

    async def shutdown(self):
        """Cancel/join every owned model/native stage before checks, checkpoint, approval and workspace dependencies drain."""
        self.closing = True
        tasks = [task for task in self.operations if task is not asyncio.current_task()]
        for task in tasks:
            task.cancel()
        for task in tasks:
            try:
                await finish_task(task)
            except BaseException:
                logger.info("coding_workflow_cancelled_stage_joined")
        logger.info("coding_workflow_shutdown_complete")
