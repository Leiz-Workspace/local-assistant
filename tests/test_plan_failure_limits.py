"""Verify global plan output/lifetime limits, deployment revision changes and fail-closed checkpoint publication around action boundaries."""

import pytest
from test_run_planner import plan, runner

from src.application.ports.plan_checkpoint import CheckpointError
from src.application.services.run_planner import PlanError


@pytest.mark.asyncio
async def test_global_output_budget_stops_before_another_action(tmp_path):
    """Stop a full output budget without performing a fifth model-selected step or refunding completed work."""
    calls = []

    async def invoke(step, call):
        """Return exactly the admitted per-call maximum for a finite authored budget test."""
        calls.append(step.identifier)
        return b"x" * 65536

    value, store = runner(tmp_path, invoke)
    with pytest.raises(PlanError, match="budget"):
        await value.start(plan(count=5), explicit_start=True)
    assert calls == [f"step-{i}" for i in range(4)]
    state, reference = store.latest(value.run_id)
    assert state["output_bytes"] == 262144 and state["attempts"] == 4
    with pytest.raises(PlanError, match="budget"):
        await value.resume(plan(count=5), reference, explicit_resume=True)
    await value.close()
    store.close()


@pytest.mark.asyncio
async def test_reply_after_global_deadline_is_not_a_complete_plan(tmp_path):
    """Refuse an otherwise complete tool reply arriving after the durable run lifetime."""
    clock = [100.0]

    async def invoke(step, call):
        """Advance only the fixture host clock to exercise the publication deadline barrier."""
        clock[0] = 220.0
        return b"late"

    value, store = runner(tmp_path, invoke, clock=lambda: clock[0])
    result = await value.start(plan(), explicit_start=True)
    assert result["status"] == "failed" and result["outputs"] == ()
    with pytest.raises(PlanError, match="expired"):
        await value.resume(plan(), result["checkpoint"], explicit_resume=True)
    await value.close()
    store.close()


@pytest.mark.parametrize("stage", ["before", "after"])
@pytest.mark.asyncio
async def test_checkpoint_failure_never_starts_an_unrecorded_action_or_replays_a_possible_write(
    tmp_path, stage
):
    """Keep failed durable publication on the safe side of each real handler boundary."""
    calls = []

    async def invoke(step, call):
        """Record only the authored action count, without editing any production resource."""
        calls.append(True)
        return b"action receipt"

    value, store = runner(tmp_path, invoke, effect="write")
    original = store.append

    def unavailable(run_id, state, previous):
        """Inject an unavailable filesystem before or after the single possible action."""
        boundary = 1 if stage == "before" else 2
        if previous is not None and previous.revision == boundary:
            raise CheckpointError("unavailable")
        return original(run_id, state, previous)

    store.append = unavailable
    with pytest.raises(PlanError, match="storage_failed"):
        await value.start(plan(), explicit_start=True)
    assert calls == ([] if stage == "before" else [True])
    state, reference = store.latest(value.run_id)
    assert state["status"] == ("ready" if stage == "before" else "inflight")
    store.append = original
    if stage == "after":
        with pytest.raises(PlanError, match="uncertain_write"):
            await value.resume(plan(), reference, explicit_resume=True)
        assert calls == [True]
    await value.close()
    store.close()


@pytest.mark.asyncio
async def test_owner_or_handler_revision_change_cannot_reuse_an_old_signed_plan(
    tmp_path,
):
    """Bind recovery to exact current host deployment contracts as well as the raw plan and owner."""

    async def fail(step, call):
        """Produce a recoverable fixture read failure without a live external dependency."""
        raise RuntimeError("fixture")

    value, store = runner(tmp_path, fail)
    result = await value.start(plan(), explicit_start=True)
    owner, workspace = value.owner, value.workspace
    await value.close()
    store.close()
    changed, other = runner(
        tmp_path, fail, owner=owner, workspace=workspace, revision="e" * 64
    )
    with pytest.raises(PlanError, match="invalid_scope"):
        await changed.resume(plan(), result["checkpoint"], explicit_resume=True)
    await changed.close()
    other.close()
