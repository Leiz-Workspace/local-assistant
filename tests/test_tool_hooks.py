"""Verify finite hook metadata, permission barriers, uncertainty and actual task ownership through cancellation and stop."""

import asyncio
import hashlib
from dataclasses import FrozenInstanceError, replace
from uuid import uuid4

import pytest

from src.application.services.tool_hooks import GuardedToolRun, HookCall, HookError


def fixture(*, effect="read", policy=None, timeout=1):
    """Bind one disposable trusted actor without exposing handlers, effects or approval flags in request data."""

    async def allow(call):
        """Authorize only fixture work without issuing any mutation or production grant."""
        return None

    owner, workspace = uuid4(), uuid4()
    run = GuardedToolRun(
        owner,
        workspace,
        profile="core",
        effects={"fixture.read": effect},
        authorize=policy or allow,
        timeout=timeout,
    )
    call = HookCall(
        owner,
        workspace,
        run.identifier,
        uuid4(),
        "core",
        "fixture.read",
        hashlib.sha256(b"public fixture").hexdigest(),
    )
    return run, call


@pytest.mark.asyncio
async def test_fixed_events_and_immutable_call_grant_no_approval_authority(caplog):
    """Retain exact metadata only and refuse using a hook return value as a grant."""
    caplog.set_level("INFO")
    run, call = fixture()

    async def operation(scope):
        """Return literal untrusted test bytes without a real external action."""
        assert scope is call
        return b"private-output-body"

    assert await run.execute(call, operation) == b"private-output-body"
    assert [(row.phase, row.outcome) for row in run.events] == [
        ("before", "pending"),
        ("after", "completed"),
    ]
    assert all(event.arguments_sha256 == call.arguments_sha256 for event in run.events)
    with pytest.raises(FrozenInstanceError):
        call.profile = "unrestricted"
    with pytest.raises(TypeError):
        replace(call, approved=True)
    assert "private-output-body" not in caplog.text
    await run.close()


@pytest.mark.parametrize(
    "field,value",
    [
        ("owner_id", uuid4()),
        ("workspace_id", uuid4()),
        ("run_id", uuid4()),
        ("profile", "unrestricted"),
        ("tool", "shell"),
        ("arguments_sha256", "x" * 64),
    ],
)
@pytest.mark.asyncio
async def test_untrusted_scope_cannot_reach_policy_or_handler(field, value):
    """Reject forged identity/profile/tool/hash before any operation or hook metadata publication."""
    calls = []

    async def policy(call):
        """Record only unexpected permission-check admission."""
        calls.append("policy")

    run, call = fixture(policy=policy)
    with pytest.raises(HookError, match="invalid_scope"):
        await run.execute(replace(call, **{field: value}), policy)
    assert calls == [] and run.events == ()


@pytest.mark.asyncio
async def test_denial_or_magic_boolean_from_policy_never_invokes_a_tool():
    """Do not interpret arbitrary booleans from a hook/policy-like callback as approved authority."""
    invoked = []

    async def deny(call):
        """Model an invalid boolean grant rather than the trusted policy's successful empty return."""
        return True

    async def operation(call):
        """Expose an unexpected handler call without taking any side effect."""
        invoked.append(True)
        return b"not allowed"

    run, call = fixture(policy=deny)
    with pytest.raises(HookError, match="denied"):
        await run.execute(call, operation)
    assert not invoked and run.events[-1].outcome == "denied"


@pytest.mark.parametrize("effect", ["read", "write"])
@pytest.mark.asyncio
async def test_permission_loss_after_work_withholds_reply_and_preserves_write_uncertainty(
    effect,
):
    """Recheck authority before publication and never claim clean rollback of a possibly executed write."""
    checks = []

    async def policy(call):
        """Revoke the fixture authorization after the handler has completed."""
        checks.append(True)
        if len(checks) > 1:
            raise RuntimeError("private policy detail")

    async def operation(call):
        """Return an authored completed action receipt whose later publication may be refused."""
        return b"receipt"

    run, call = fixture(policy=policy, effect=effect)
    with pytest.raises(HookError, match="uncertain" if effect == "write" else "failed"):
        await run.execute(call, operation)
    assert run.events[-1].outcome == ("uncertain" if effect == "write" else "failed")


@pytest.mark.parametrize("stop", ["caller", "owner"])
@pytest.mark.asyncio
async def test_stop_and_repeated_caller_cancellation_join_real_cleanup_before_retirement(
    stop,
):
    """Keep the guarded task pinned until its real async cleanup ends under both stop paths."""
    run, call = fixture()
    entered, releasing, finished = asyncio.Event(), asyncio.Event(), asyncio.Event()

    async def operation(scope):
        """Emulate an adapter that owns and joins its native cleanup before propagating cancellation."""
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            await releasing.wait()
            finished.set()

    task = asyncio.create_task(run.execute(call, operation))
    await entered.wait()
    with pytest.raises(HookError, match="invalid_scope"):
        run.request_stop(uuid4(), run.identifier)
    if stop == "caller":
        task.cancel()
        await asyncio.sleep(0)
        task.cancel()
    else:
        run.request_stop(run.owner, run.identifier)
    await asyncio.sleep(0)
    assert not finished.is_set() and run.active is not None
    releasing.set()
    with pytest.raises(asyncio.CancelledError if stop == "caller" else HookError):
        await task
    assert finished.is_set() and run.active is None
    assert run.events[-1].outcome == ("cancelled" if stop == "caller" else "stopped")


@pytest.mark.asyncio
async def test_timeout_and_suppressed_cancellation_cannot_publish_success():
    """Retain host deadlines even when the invoked dependency catches its cancellation signal."""
    run, call = fixture(timeout=0.01)

    async def late(scope):
        """Return a stale result after swallowing the per-call timeout."""
        try:
            await asyncio.sleep(1)
        except asyncio.CancelledError:
            pass
        return b"late"

    with pytest.raises(HookError, match="timeout"):
        await run.execute(call, late)
    assert run.events[-1].outcome == "timeout"


@pytest.mark.asyncio
async def test_write_error_is_uncertain_without_reinvocation_and_metadata_is_bounded():
    """Charge action attempts once and retain uncertainty rather than automatically retrying a write."""
    run, call = fixture(effect="write")
    attempts = []

    async def failed(scope):
        """Emulate an action that may have committed before its adapter loses the receipt."""
        attempts.append(True)
        raise RuntimeError("unknown commit outcome")

    with pytest.raises(HookError, match="uncertain"):
        await run.execute(call, failed)
    assert attempts == [True] and run.events[-1].outcome == "uncertain"
    with pytest.raises(HookError, match="invalid_scope"):
        await run.execute(call, failed)
    with pytest.raises(HookError, match="stopped"):
        await run.execute(replace(call, call_id=uuid4()), failed)
    assert attempts == [True]


@pytest.mark.asyncio
async def test_close_from_inside_handler_cannot_publish_or_deadlock():
    """Treat handler-triggered closure as stop without waiting on the current task itself."""
    run, call = fixture()

    async def operation(scope):
        """Close the owned actor before returning an otherwise complete response."""
        await run.close()
        return b"late"

    with pytest.raises(HookError, match="closed"):
        await asyncio.wait_for(run.execute(call, operation), 0.5)
    assert run.events[-1].outcome == "closed" and run.active is None


@pytest.mark.parametrize("effect", ["read", "write"])
@pytest.mark.asyncio
async def test_bad_output_remains_withheld_and_write_uncertainty_stops_reuse(effect):
    """Reject incomplete or overlarge adapter data without falsely reporting a clean write outcome."""
    run, call = fixture(effect=effect)

    async def operation(scope):
        """Return an excessive authored result after the handler was invoked."""
        return b"x" * 65537

    with pytest.raises(
        HookError, match="uncertain" if effect == "write" else "invalid_result"
    ):
        await run.execute(call, operation)
    assert run.events[-1].outcome == (
        "uncertain" if effect == "write" else "invalid_result"
    )


@pytest.mark.asyncio
async def test_invalid_attempts_and_event_pairs_stay_bounded():
    """Bound repeated host calls and reject reused call IDs instead of overwriting their terminal metadata."""
    run, call = fixture()

    async def operation(scope):
        """Return fixed data for one admitted fixture call."""
        return b"ok"

    for _ in range(8):
        await run.execute(replace(call, call_id=uuid4()), operation)
    assert len(run.events) == 16
    with pytest.raises(HookError, match="limit"):
        await run.execute(replace(call, call_id=uuid4()), operation)
    assert len(run.events) == 16


@pytest.mark.asyncio
async def test_repeated_stop_and_close_do_not_interrupt_authorization_cleanup():
    """Own policy cleanup too and send at most one cancellation while stop/close requests overlap."""
    entered, releasing, finished = asyncio.Event(), asyncio.Event(), asyncio.Event()

    async def policy(scope):
        """Emulate an authorization adapter with cleanup that must finish before shutdown returns."""
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            await releasing.wait()
            finished.set()

    async def operation(scope):
        """Fail loudly if a stopped permission check ever reaches execution."""
        raise AssertionError("not authorized")

    run, call = fixture(policy=policy)
    task = asyncio.create_task(run.execute(call, operation))
    await entered.wait()
    run.request_stop(run.owner, run.identifier)
    await asyncio.sleep(0)
    run.request_stop(run.owner, run.identifier)
    closing = asyncio.create_task(run.close())
    await asyncio.sleep(0)
    assert not closing.done() and not finished.is_set()
    releasing.set()
    await closing
    with pytest.raises(HookError, match="stopped"):
        await task
    assert finished.is_set() and run.events[-1].outcome == "stopped"
