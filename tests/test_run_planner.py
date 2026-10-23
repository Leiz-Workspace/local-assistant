"""Verify finite typed plan execution, explicit read-only resume, durable budgets and refusal to recover uncertain writes."""

import asyncio
import json
from uuid import uuid4

import pytest
from test_mcp_adapter import EchoArguments

from src.application.services.run_planner import (
    BoundedPlanRunner,
    PlanError,
    PlanTool,
    parse_plan,
)
from src.infrastructure.plan_checkpoints import PlanCheckpointStore


def plan(*, count=1, **changes):
    """Return one fixed literal model-like plan without host scope, budgets, handlers or credentials."""
    value = dict(
        version=1,
        steps=[
            dict(
                id=f"step-{index}",
                tool="echo",
                arguments=dict(text="private-plan-argument"),
            )
            for index in range(count)
        ],
    )
    value.update(changes)
    return json.dumps(value).encode()


def runner(
    tmp_path,
    invoke,
    *,
    effect="read",
    clock=None,
    owner=None,
    workspace=None,
    revision="f" * 64,
):
    """Bind disposable host scope, strict fixed contracts, metadata store and a cancellation-aware test handler."""
    store = PlanCheckpointStore(tmp_path / "state")

    async def authorize(call):
        """Approve only authored fixture work without restoring any production skill or action approval."""
        return None

    return BoundedPlanRunner(
        owner or uuid4(),
        workspace or uuid4(),
        profile="core",
        store=store,
        tools=(PlanTool("echo", EchoArguments, effect, revision),),
        authorize=authorize,
        invoke=invoke,
        **({"clock": clock} if clock else {}),
    ), store


@pytest.mark.parametrize(
    "changes",
    [
        {"version": True},
        {"owner": "fake"},
        {"profile": "unrestricted"},
        {"budget": 999},
        {"steps": []},
        {"steps": [dict(id="one", tool="shell", arguments={})]},
        {"steps": [dict(id="one", tool="echo", arguments={"text": 1})]},
    ],
)
def test_untrusted_plans_cannot_select_scope_budget_or_arbitrary_execution(changes):
    """Reject the whole plan before any state file or native handler is created."""
    with pytest.raises(PlanError, match="invalid_plan"):
        parse_plan(
            plan(**changes), (PlanTool("echo", EchoArguments, "read", "f" * 64),)
        )


@pytest.mark.asyncio
async def test_complete_plan_buffers_private_results_but_persists_only_metadata(
    tmp_path, caplog
):
    """Run a fixed typed sequence while keeping argument and output bodies out of signed checkpoints and logs."""
    caplog.set_level("INFO")
    called = []

    async def invoke(step, call):
        """Return a private authored result and retain exact fixed step order."""
        called.append(step.identifier)
        return b"private-tool-output"

    value, store = runner(tmp_path, invoke)
    with pytest.raises(PlanError, match="explicit_action_required"):
        await value.start(plan(), explicit_start=1)
    result = await value.start(plan(count=2), explicit_start=True)
    assert (
        result["status"] == "complete"
        and result["completed_steps"] == 2
        and result["attempts"] == 2
    )
    assert (
        called == ["step-0", "step-1"]
        and result["outputs"][0][1] == b"private-tool-output"
    )
    saved = b"".join(path.read_bytes() for path in (tmp_path / "state").glob("*.json"))
    assert b"private-plan-argument" not in saved and b"private-tool-output" not in saved
    assert (
        "private-plan-argument" not in caplog.text
        and "private-tool-output" not in caplog.text
    )
    with pytest.raises(PlanError, match="not_resumable"):
        await value.resume(plan(count=2), result["checkpoint"], explicit_resume=True)
    await value.close()
    store.close()


@pytest.mark.asyncio
async def test_failed_read_needs_explicit_latest_resume_and_never_refunds_attempts(
    tmp_path,
):
    """Recover through a fresh runner/store while retaining exact original plan/catalog/owner and charged attempts."""
    attempts = []

    async def flaky(step, call):
        """Fail once before returning an authored value for an explicit user-controlled second attempt."""
        attempts.append(True)
        if len(attempts) == 1:
            raise RuntimeError("public fixture failure")
        return b"ok"

    value, store = runner(tmp_path, flaky)
    raw = plan()
    first = await value.start(raw, explicit_start=True)
    assert first["status"] == "failed" and len(attempts) == 1
    owner, workspace = value.owner, value.workspace
    await value.close()
    store.close()
    recovered, other = runner(tmp_path, flaky, owner=owner, workspace=workspace)
    with pytest.raises(PlanError, match="explicit_action_required"):
        await recovered.resume(raw, first["checkpoint"], explicit_resume=False)
    with pytest.raises(PlanError, match="invalid_scope"):
        await recovered.resume(raw + b" ", first["checkpoint"], explicit_resume=True)
    complete = await recovered.resume(raw, first["checkpoint"], explicit_resume=True)
    assert (
        complete["status"] == "complete"
        and complete["attempts"] == 2
        and len(attempts) == 2
    )
    with pytest.raises(PlanError, match="stale"):
        await recovered.resume(raw, first["checkpoint"], explicit_resume=True)
    await recovered.close()
    other.close()


@pytest.mark.asyncio
async def test_write_failure_is_uncertain_and_cannot_be_resumed_or_automatically_repeated(
    tmp_path,
):
    """Keep a possibly applied write blocked even when the owner presents a valid signed checkpoint again."""
    calls = []

    async def invoke(step, call):
        """Emulate loss of a receipt after the trusted action may have committed."""
        calls.append(True)
        raise RuntimeError("unknown write outcome")

    value, store = runner(tmp_path, invoke, effect="write")
    result = await value.start(plan(), explicit_start=True)
    assert result["status"] == "uncertain_write" and calls == [True]
    with pytest.raises(PlanError, match="uncertain_write"):
        await value.resume(plan(), result["checkpoint"], explicit_resume=True)
    assert calls == [True]
    await value.close()
    store.close()


@pytest.mark.asyncio
async def test_original_wall_lifetime_and_per_step_attempts_survive_resume(tmp_path):
    """Reject expired/read-retry-exhausted runs instead of refreshing their budgets on restart."""
    clock = [100.0]

    async def fail(step, call):
        """Return one stable failure without taking a real action."""
        raise RuntimeError("failed")

    value, store = runner(tmp_path, fail, clock=lambda: clock[0])
    first = await value.start(plan(), explicit_start=True)
    clock[0] = 220.0
    with pytest.raises(PlanError, match="expired"):
        await value.resume(plan(), first["checkpoint"], explicit_resume=True)
    await value.close()
    store.close()
    clock[0] = 100.0
    value, store = runner(tmp_path, fail, clock=lambda: clock[0])
    first = await value.start(plan(), explicit_start=True)
    second = await value.resume(plan(), first["checkpoint"], explicit_resume=True)
    assert second["attempts"] == 2
    with pytest.raises(PlanError, match="budget"):
        await value.resume(plan(), second["checkpoint"], explicit_resume=True)
    await value.close()
    store.close()


@pytest.mark.asyncio
async def test_cancel_and_close_join_action_cleanup_and_durable_terminal_state(
    tmp_path,
):
    """Retire the complete run lock/guard/checkpoint operation before returning shutdown to the host."""
    entered, releasing, finished = asyncio.Event(), asyncio.Event(), asyncio.Event()

    async def invoke(step, call):
        """Hold owned cleanup to expose premature state-directory or lock release."""
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            await releasing.wait()
            finished.set()

    value, store = runner(tmp_path, invoke)
    operation = asyncio.create_task(value.start(plan(), explicit_start=True))
    await entered.wait()
    operation.cancel()
    await asyncio.sleep(0)
    operation.cancel()
    closing = asyncio.create_task(value.close())
    await asyncio.sleep(0)
    assert not closing.done() and not finished.is_set()
    releasing.set()
    with pytest.raises(asyncio.CancelledError):
        await operation
    await closing
    assert finished.is_set() and value.pending is None and not value.active
    files = list((tmp_path / "state").glob("*.03.json"))
    assert len(files) == 1
    state = json.loads(files[0].read_text())["state"]
    assert state["status"] == "cancelled" and state["attempts"] == 1
    store.close()


@pytest.mark.asyncio
async def test_handler_close_cannot_deadlock_its_parent_or_publish_a_late_result(
    tmp_path,
):
    """Close from an owned handler without awaiting its parent and withhold the handler's late output."""

    async def invoke(step, call):
        """Request shutdown from inside the admitted child and then return a forbidden late body."""
        await value.close()
        return b"late"

    value, store = runner(tmp_path, invoke)
    result = await asyncio.wait_for(value.start(plan(), explicit_start=True), 1)
    assert result["status"] == "failed" and result["outputs"] == ()
    assert value.closed and value.pending is None and not value.active
    store.close()
