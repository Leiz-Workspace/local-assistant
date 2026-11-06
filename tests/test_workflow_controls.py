"""Verify finite typed workflow hook/lineage reservations, cancellation and explicit retry ceilings without model/native actions."""

from uuid import uuid4

import pytest

from src.application.services import workflow_controls as module
from src.application.services.workflow_controls import WorkflowLineage
from src.application.services.workspace_policy import WorkspaceAccessError


def control():
    """Create one explicitly typed disposable lineage member with no task, source, command or approval capability."""
    root = uuid4()
    lineage = WorkflowLineage(uuid4(), uuid4(), root)
    return lineage.register(root)


def test_finite_successful_stages_reserve_terminal_events_and_copy_metadata():
    """Charge four ordinary stages once and retain eight immutable scalar-only events without action authority."""
    value = control()
    for stage in ["proposal", "apply", "capture_checks", "run_checks"]:
        value.before(stage)
        value.after(stage, "completed")
    view = value.snapshot()
    assert view["workflow_steps_used"] == view["lineage_steps_used"] == 4
    assert len(view["events"]) == value.reserved_events == 8
    assert not view["events_grant_action_authority"] and view["automatic_retries"] == 0
    view["events"].clear()
    assert len(value.snapshot()["events"]) == 8
    with pytest.raises(WorkspaceAccessError):
        value.before("apply")


def test_one_explicit_retry_member_keeps_first_failure_and_enforces_total_five_stages():
    """Retain both proposal attempts and allow only one successful branch's separately reviewed edit/check stages."""
    first = control()
    first.before("proposal")
    first.after("proposal", "failed")
    second = first.lineage.register(uuid4(), first.identifier)
    for stage in ["proposal", "apply", "capture_checks", "run_checks"]:
        second.before(stage)
        second.after(stage, "completed")
    assert (
        first.snapshot()["proposals_used"] == 2
        and second.snapshot()["proposal_ordinal"] == 2
    )
    assert (
        first.lineage.steps == 5 and len(first.events) == 2 and len(second.events) == 8
    )
    with pytest.raises(WorkspaceAccessError) as caught:
        first.lineage.register(uuid4(), second.identifier)
    assert caught.value.code == "workflow_retry_limit"


@pytest.mark.parametrize(
    "stage",
    ["shell", "callback", "https://example.invalid", True, None, {"command": "true"}],
)
def test_unknown_or_untyped_callback_stages_never_reserve_policy_slots(stage):
    """Reject dynamic callbacks, network targets and commands before adding a stage/event reservation."""
    value = control()
    with pytest.raises(WorkspaceAccessError):
        value.before(stage)
    assert not value.events and value.lineage.steps == value.reserved_events == 0


@pytest.mark.parametrize("identity", [None, True, "not-a-uuid"])
def test_untyped_lineage_identity_is_rejected_before_registration(identity):
    """Require actual server UUID types instead of implicit owner/root coercion."""
    with pytest.raises(WorkspaceAccessError):
        WorkflowLineage(identity, uuid4(), uuid4())


def test_cancel_intent_blocks_new_stages_preserves_existing_completion_and_is_idempotent():
    """Reserve cancellation once and finish an already-started action without treating cancellation as undo or retry authority."""
    value = control()
    value.before("proposal")
    assert value.begin_cancel() and not value.begin_cancel()
    value.after("proposal", "cancelled")
    value.finish_cancel("completed")
    assert value.cancel_requested and value.cancel_finished and len(value.events) == 4
    with pytest.raises(WorkspaceAccessError):
        value.before("apply")
    with pytest.raises(WorkspaceAccessError):
        value.finish_cancel("completed")
    assert value.lineage.steps == 1


def test_event_pair_capacity_fails_before_any_stage_charge(monkeypatch):
    """Reserve completion space before side effects and leave every counter unchanged on capacity denial."""
    value = control()
    monkeypatch.setattr(module, "MAX_HOOK_EVENTS", 1)
    with pytest.raises(WorkspaceAccessError) as caught:
        value.before("proposal")
    assert caught.value.code == "workflow_hook_capacity"
    assert (
        not value.actions
        and not value.events
        and value.lineage.steps == value.lineage.reserved_events == 0
    )


def test_lineage_step_ceiling_cannot_be_reset_by_another_member(monkeypatch):
    """Share the fixed lineage counter across retry records rather than resetting the total action budget."""
    first = control()
    first.before("proposal")
    first.after("proposal", "failed")
    second = first.lineage.register(uuid4(), first.identifier)
    monkeypatch.setattr(module, "MAX_LINEAGE_STEPS", 1)
    with pytest.raises(WorkspaceAccessError):
        second.before("proposal")
    assert not second.events and first.lineage.steps == 1


def test_terminal_hook_requires_reserved_actual_started_stage():
    """Reject forged completion markers and terminal hook replay without adding any event or slot."""
    value = control()
    with pytest.raises(WorkspaceAccessError):
        value.after("apply", "completed")
    value.before("proposal")
    value.after("proposal", "failed")
    with pytest.raises(WorkspaceAccessError):
        value.after("proposal", "completed")
    assert len(value.events) == 2
