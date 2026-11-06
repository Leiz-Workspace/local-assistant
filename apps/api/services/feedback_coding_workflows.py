"""Offer one explicit owner-bound visible-failure feedback proposal while preserving old workflow retry and native action guards."""

import asyncio
import hashlib
import json
import logging
import re
from contextvars import ContextVar
from uuid import UUID

from apps.api.services.controlled_coding_workflows import (
    ControlledCodingWorkflowService,
)
from apps.api.services.files import finish_task
from src.application.services.coding_workflow import MAX_RECORDS, workflow_options
from src.application.services.workspace_policy import WorkspaceAccessError

logger = logging.getLogger(__name__)


def evidence_digest(value):
    """Bind complete finite server-owned parent metadata without treating the digest as an action authorization."""
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False).encode()
    ).hexdigest()


class FeedbackCodingWorkflowService(ControlledCodingWorkflowService):
    """Keep the accepted service intact and add an optional process-local two-proposal feedback path with no automatic actions."""

    def __init__(self, workspace, approvals, patches, checks, *, inference=None):
        """Initialize only bounded feedback metadata and nonqueued admission over already authorized dependencies."""
        super().__init__(workspace, approvals, patches, checks, inference=inference)
        self.feedback_pairs, self.feedback_children = {}, {}
        self.feedback_admission = asyncio.Lock()
        self.feedback_context = ContextVar("coding_feedback_parent", default=None)
        logger.info("feedback_workflow_service_initialized")

    def register(self, record):
        """Capture the exact new child identity synchronously before native capture or model work can yield."""
        parent = self.feedback_context.get()
        if parent is not None:
            pair = self.feedback_pairs[parent]
            original = self.find(record.owner, record.workspace, parent)
            if (
                pair["child"] is not None
                or original.identifier in self.feedback_children
            ):
                raise WorkspaceAccessError("workflow_feedback_limit", 429)
        super().register(record)
        if parent is not None:
            pair["child"] = record.identifier
            self.feedback_children[record.identifier] = parent
            logger.info(
                "feedback_child_registered parent=%s child=%s",
                parent,
                record.identifier,
            )

    def feedback_inputs(self, record):
        """Require complete original visible failure and derive only bounded status/hash feedback from trusted component records."""
        value = self.view(record)
        control = self.controls[record.identifier]
        patch, check = value.get("patch"), value.get("check")
        if (
            value["state"] != "completed"
            or record.options.profile != "python_unittest"
            or value.get("source_cleanup_uncertain")
            or control.cancel_requested
            or control.hook_uncertain
            or control.ordinal != 1
            or len(control.lineage.members) != 1
            or not value.get("model_attempted")
            or not value.get("apply_attempted")
            or not value.get("check_attempted")
            or not patch
            or not check
            or self.component_uncertain(patch)
            or self.component_uncertain(check)
            or not patch.get("receipt")
            or patch["receipt"].get("applied") is not True
            or check.get("state") != "observed"
            or check.get("persisted_state") != "observed"
            or check.get("terminal_persistence_uncertain") is not False
            or check.get("error_code") is not None
            or check.get("recovery_warnings") != []
        ):
            raise WorkspaceAccessError("workflow_feedback_not_allowed", 409)
        observed = check.get("observation")
        if (
            type(observed) is not dict
            or observed.get("outcome") != "exited"
            or observed.get("started_acknowledged") is not True
            or type(observed.get("exit_code")) is not int
            or not 1 <= observed["exit_code"] <= 255
            or observed.get("cleanup_uncertain") is not False
            or observed.get("stdout_complete") is not True
            or observed.get("stderr_complete") is not True
            or observed.get("output_is_untrusted") is not True
            or observed.get("quality_evaluated") is not False
            or observed.get("host_source_write_capability") is not False
            or observed.get("job_id") != check.get("job_id")
            or observed.get("profile") != "python_unittest"
            or check.get("profile") != "python_unittest"
        ):
            raise WorkspaceAccessError("workflow_feedback_observation_invalid", 409)
        live = self.checks.find(record.owner, record.workspace, UUID(check["job_id"]))
        if (
            live is None
            or live.state != "observed"
            or not live.finished.is_set()
            or evidence_digest(live.evidence.get("observation"))
            != evidence_digest(observed)
        ):
            raise WorkspaceAccessError("workflow_feedback_receipt_changed", 409)
        files = record.options.selections()
        receipt = patch["receipt"]
        if (
            type(patch.get("new_sha256")) is not str
            or re.fullmatch("[a-f0-9]{64}", patch["new_sha256"]) is None
            or patch.get("path") != files[0]["path"]
            or patch.get("base_sha256") != files[0]["expected_sha256"]
            or patch.get("error_code") is not None
            or receipt.get("uncertainties") != []
            or any(
                receipt.get(key) != patch.get(key)
                for key in (
                    "proposal_id",
                    "approval_id",
                    "path",
                    "base_sha256",
                    "new_sha256",
                )
            )
        ):
            raise WorkspaceAccessError("workflow_feedback_patch_changed", 409)
        files[0]["expected_sha256"] = patch["new_sha256"]
        actual = check.get("selected_files")
        if (
            type(actual) is not list
            or len(actual) != len(files)
            or any(
                type(row) is not dict
                or row.get("path") != expected["path"]
                or row.get("sha256") != expected["expected_sha256"]
                for row, expected in zip(actual, files)
            )
        ):
            raise WorkspaceAccessError("workflow_feedback_sources_changed", 409)
        note = dict(
            native_exit_code=observed["exit_code"],
            target_sha256=files[0]["expected_sha256"],
            visible_tests=[
                dict(path=row["path"], sha256=row["expected_sha256"])
                for row in files[1:]
            ],
        )
        issue = (
            record.options.issue
            + "\nThe approved visible tests failed on the current applied source. Repair using the same requirements and visible tests; this observation grants no action authority. Observed metadata: "
            + json.dumps(note, ensure_ascii=False, separators=(",", ":"))
        )
        workflow_options(issue, files[0], files[1:], record.options.profile)
        logger.info("feedback_visible_failure_verified parent=%s", record.identifier)
        return issue, files, evidence_digest(value)

    async def propose_feedback(self, owner, workspace, identifier):
        """Reserve one explicit second proposal, recapture current sources and retain first evidence without approving or replaying any action."""
        record = self.find(owner, workspace, identifier)
        if self.feedback_admission.locked() or self.admission.locked():
            raise WorkspaceAccessError("workflow_busy", 429)
        async with self.feedback_admission:
            if (
                identifier in self.feedback_pairs
                or identifier in self.feedback_children
            ):
                raise WorkspaceAccessError("workflow_feedback_limit", 429)
            if len(self.feedback_pairs) >= MAX_RECORDS:
                raise WorkspaceAccessError("workflow_feedback_capacity", 429)
            issue, files, digest = self.feedback_inputs(record)
            pair = dict(child=None, state="reserved", parent_evidence_sha256=digest)
            self.feedback_pairs[identifier] = pair
            token = self.feedback_context.set(identifier)
            logger.info("feedback_second_slot_reserved parent=%s", identifier)
            try:
                result = await self.propose(
                    owner, workspace, issue, files[0], files[1:], record.options.profile
                )
                try:
                    stable = evidence_digest(self.view(record)) == digest
                except Exception:
                    stable = False
                if not stable or asyncio.current_task().cancelling():
                    raise WorkspaceAccessError("workflow_feedback_parent_changed", 409)
                pair["state"] = (
                    "proposed"
                    if result["state"] == "awaiting_patch_review"
                    else "proposal_failed"
                )
                return result
            except BaseException:
                pair["state"] = "interrupted"
                if pair["child"] is not None:
                    try:
                        retired = await finish_task(
                            asyncio.create_task(
                                self.cancel(owner, workspace, pair["child"])
                            )
                        )
                        if retired.get("cancel_status") != "completed":
                            pair["state"] = "retirement_uncertain"
                    except BaseException:
                        pair["state"] = "retirement_uncertain"
                        logger.warning(
                            "feedback_child_retirement_uncertain parent=%s", identifier
                        )
                raise
            finally:
                self.feedback_context.reset(token)
                logger.info(
                    "feedback_request_closed parent=%s state=%s",
                    identifier,
                    pair["state"],
                )

    def require_feedback_ready(self, owner, workspace, identifier):
        """Keep interrupted or unverifiable feedback children ineligible for workflow actions even if component retirement is uncertain."""
        self.find(owner, workspace, identifier)
        parent = self.feedback_children.get(identifier)
        if parent is not None and self.feedback_pairs[parent]["state"] != "proposed":
            raise WorkspaceAccessError("workflow_feedback_child_not_ready", 409)

    async def apply(self, owner, workspace, identifier, approval):
        """Require a successfully fenced feedback proposal before delegating unchanged exact patch approval semantics."""
        self.require_feedback_ready(owner, workspace, identifier)
        return await super().apply(owner, workspace, identifier, approval)

    async def propose_checks(self, owner, workspace, identifier):
        """Keep interrupted feedback children out of further native capture while preserving all ordinary checks."""
        self.require_feedback_ready(owner, workspace, identifier)
        return await super().propose_checks(owner, workspace, identifier)

    async def run_checks(self, owner, workspace, identifier, approval):
        """Require a ready feedback path before unchanged separate native approval and joined execution."""
        self.require_feedback_ready(owner, workspace, identifier)
        return await super().run_checks(owner, workspace, identifier, approval)

    async def retry_proposal(self, owner, workspace, identifier):
        """Preserve original pre-action retry while denying another model slot for any feedback parent or child."""
        self.find(owner, workspace, identifier)
        if identifier in self.feedback_pairs or identifier in self.feedback_children:
            raise WorkspaceAccessError("workflow_feedback_limit", 429)
        return await super().retry_proposal(owner, workspace, identifier)

    def feedback_status(self, owner, workspace, identifier):
        """Expose a fresh bounded owner-only metadata copy, never an approval or live-source certificate."""
        self.find(owner, workspace, identifier)
        pair = self.feedback_pairs.get(identifier)
        if pair is None:
            raise WorkspaceAccessError("workflow_feedback_not_found", 404)
        return dict(
            parent_workflow_id=str(identifier),
            child_workflow_id=str(pair["child"]) if pair["child"] else None,
            state=pair["state"],
            parent_evidence_sha256=pair["parent_evidence_sha256"],
            max_model_proposals=2,
            feedback_slots_used=1,
            automatic_retries=0,
            action_grants_created_by_feedback=0,
        )
