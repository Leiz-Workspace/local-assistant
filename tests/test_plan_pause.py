"""Verify explicit owner pause and durable remaining-step resume without replaying completed tool actions."""

import asyncio
from uuid import uuid4

import pytest
from test_run_planner import plan, runner

from src.application.services.run_planner import PlanError


@pytest.mark.asyncio
async def test_explicit_owner_pause_preserves_completed_steps_and_resumes_only_remaining_work(
    tmp_path,
):
    """Pause after a durable completed step without repeating it or refunding lifetime/attempt budgets."""
    entered, releasing = asyncio.Event(), asyncio.Event()
    calls = []

    async def invoke(step, call):
        """Wait during the first authored read so the owner can request a clean between-step pause."""
        calls.append(step.identifier)
        if step.identifier == "step-0":
            entered.set()
            await releasing.wait()
        return b"private result"

    value, store = runner(tmp_path, invoke)
    operation = asyncio.create_task(value.start(plan(count=2), explicit_start=True))
    await entered.wait()
    with pytest.raises(PlanError, match="invalid_scope"):
        value.request_pause(uuid4(), value.run_id)
    value.request_pause(value.owner, value.run_id)
    releasing.set()
    paused = await operation
    assert (
        paused["status"] == "paused"
        and paused["completed_steps"] == 1
        and calls == ["step-0"]
    )
    complete = await value.resume(
        plan(count=2), paused["checkpoint"], explicit_resume=True
    )
    assert (
        complete["status"] == "complete"
        and complete["attempts"] == 2
        and calls == ["step-0", "step-1"]
    )
    assert complete["outputs"] == (("step-1", b"private result"),)
    await value.close()
    store.close()
