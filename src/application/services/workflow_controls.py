"""Bound trusted workflow hook events, proposal lineages and action slots without accepting model/client callbacks or granting approvals."""

import logging
from dataclasses import dataclass
from uuid import UUID

from src.application.services.workspace_policy import WorkspaceAccessError

logger = logging.getLogger(__name__)
STAGES = frozenset({"proposal", "apply", "capture_checks", "run_checks"})
OUTCOMES = frozenset({"completed", "failed", "cancelled", "uncertain"})
MAX_PROPOSALS = 2
MAX_WORKFLOW_STEPS = 4
MAX_LINEAGE_STEPS = 5
MAX_HOOK_EVENTS = 16
MAX_LINEAGE_EVENTS = 32


@dataclass(frozen=True, slots=True)
class HookEvent:
    """Freeze one finite server-owned metadata event without source/output/credential contents or callback authority."""

    sequence: int
    stage: str
    phase: str
    outcome: str

    def record(self):
        """Return a fresh bounded scalar-only event representation for private workflow audit history."""
        return dict(
            sequence=self.sequence,
            stage=self.stage,
            phase=self.phase,
            outcome=self.outcome,
        )


class WorkflowLineage:
    """Charge at most two fresh proposal records and five total ordinary stages while preserving every original attempt."""

    def __init__(self, owner, workspace, root):
        """Bind exact typed owner/workspace/root identities before allocating any lineage authority or event reservation."""
        if any(type(value) is not UUID for value in (owner, workspace, root)):
            raise WorkspaceAccessError("workflow_control_scope_invalid", 422)
        self.owner, self.workspace, self.root = owner, workspace, root
        self.members = {}
        self.steps, self.reserved_events = 0, 0
        logger.info("workflow_lineage_initialized root_id=%s", root)

    def register(self, identifier, parent=None):
        """Reserve one distinct proposal slot before native/model work without deleting, refunding or reusing an older attempt."""
        if (
            type(identifier) is not UUID
            or identifier in self.members
            or (
                parent is not None
                and (type(parent) is not UUID or parent not in self.members)
            )
        ):
            raise WorkspaceAccessError("workflow_control_scope_invalid", 422)
        if not self.members and (identifier != self.root or parent is not None):
            raise WorkspaceAccessError("workflow_control_scope_invalid", 422)
        if self.members and parent is None:
            raise WorkspaceAccessError("workflow_control_parent_required", 409)
        if len(self.members) >= MAX_PROPOSALS:
            raise WorkspaceAccessError("workflow_retry_limit", 429)
        control = WorkflowControl(self, identifier, parent, len(self.members) + 1)
        self.members[identifier] = control
        logger.info(
            "workflow_lineage_proposal_reserved root_id=%s workflow_id=%s proposals=%d",
            self.root,
            identifier,
            len(self.members),
        )
        return control


class WorkflowControl:
    """Retain finite stage/cancellation hooks and reserve terminal event space before an admitted side effect."""

    def __init__(self, lineage, identifier, parent, ordinal):
        """Bind one already-reserved owner lineage member with empty process-local event/action/cancellation state."""
        self.lineage, self.identifier, self.parent, self.ordinal = (
            lineage,
            identifier,
            parent,
            ordinal,
        )
        self.actions = {}
        self.events = ()
        self.reserved_events = 0
        self.cancel_requested, self.cancel_finished = False, False
        self.hook_uncertain = False
        logger.info("workflow_control_initialized workflow_id=%s", identifier)

    def reserve_pair(self):
        """Reserve both before/after event slots atomically so a later observed action cannot lose its completion slot."""
        if (
            self.reserved_events + 2 > MAX_HOOK_EVENTS
            or self.lineage.reserved_events + 2 > MAX_LINEAGE_EVENTS
        ):
            raise WorkspaceAccessError("workflow_hook_capacity", 429)
        self.reserved_events += 2
        self.lineage.reserved_events += 2

    def append(self, stage, phase, outcome):
        """Append only validated finite server metadata within an already-reserved bounded event pair."""
        if (
            stage not in STAGES | {"cancel"}
            or phase not in {"before", "after"}
            or outcome not in OUTCOMES | {"admitted"}
            or len(self.events) >= self.reserved_events
        ):
            raise WorkspaceAccessError("workflow_hook_invalid", 503)
        event = HookEvent(len(self.events) + 1, stage, phase, outcome)
        self.events = (*self.events, event)
        logger.info(
            "workflow_hook_recorded workflow_id=%s sequence=%d stage=%s phase=%s outcome=%s",
            self.identifier,
            event.sequence,
            stage,
            phase,
            outcome,
        )

    def before(self, stage):
        """Charge a finite action once and enforce cancellation/lineage ceilings before source/model/native work begins."""
        if type(stage) is not str or stage not in STAGES:
            raise WorkspaceAccessError("workflow_hook_invalid", 422)
        if self.cancel_requested:
            raise WorkspaceAccessError("workflow_cancel_requested", 409)
        if self.hook_uncertain:
            raise WorkspaceAccessError("workflow_hook_uncertain", 503)
        if stage in self.actions:
            raise WorkspaceAccessError("workflow_stage_replayed", 409)
        if (
            len(self.actions) >= MAX_WORKFLOW_STEPS
            or self.lineage.steps >= MAX_LINEAGE_STEPS
        ):
            raise WorkspaceAccessError("workflow_step_limit", 429)
        self.reserve_pair()
        self.actions[stage] = "started"
        self.lineage.steps += 1
        self.append(stage, "before", "admitted")

    def after(self, stage, outcome):
        """Retain the actual terminal stage category without granting another attempt or interpreting program output as approval."""
        if (
            stage not in STAGES
            or outcome not in OUTCOMES
            or self.actions.get(stage) != "started"
        ):
            raise WorkspaceAccessError("workflow_hook_invalid", 503)
        self.append(stage, "after", outcome)
        self.actions[stage] = "finished"

    def begin_cancel(self):
        """Record cancellation intent once without consuming another action slot or adding events on repeated pending requests."""
        if self.cancel_requested:
            return False
        self.reserve_pair()
        self.cancel_requested = True
        self.append("cancel", "before", "admitted")
        return True

    def finish_cancel(self, outcome):
        """Publish a reserved cancellation result once while keeping busy/incomplete cancellation intent available for inspection."""
        if not self.cancel_requested or self.cancel_finished or outcome not in OUTCOMES:
            raise WorkspaceAccessError("workflow_hook_invalid", 503)
        self.append("cancel", "after", outcome)
        self.cancel_finished = True

    def snapshot(self):
        """Return fresh bounded policy/history data without exposing internal task handles or mutable lineage/event aliases."""
        return dict(
            policy_version="d44-v1",
            lineage_id=str(self.lineage.root),
            parent_workflow_id=str(self.parent) if self.parent else None,
            proposal_ordinal=self.ordinal,
            proposals_used=len(self.lineage.members),
            max_proposals=MAX_PROPOSALS,
            automatic_retries=0,
            lineage_steps_used=self.lineage.steps,
            max_lineage_steps=MAX_LINEAGE_STEPS,
            workflow_steps_used=len(self.actions),
            max_workflow_steps=MAX_WORKFLOW_STEPS,
            max_hook_events=MAX_HOOK_EVENTS,
            events=[event.record() for event in self.events],
            cancel_requested=self.cancel_requested,
            cancel_finished=self.cancel_finished,
            hook_uncertain=self.hook_uncertain,
            events_grant_action_authority=False,
        )
