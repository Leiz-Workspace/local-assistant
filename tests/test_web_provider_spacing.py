"""Check actual dispatch spacing, original outcomes and cancellation/clock/admission failure boundaries without network or model calls."""

import asyncio

import pytest
from web_provider_spacing import SpacedSearchEvaluation, SpacingError


class Clock:
    """Provide controlled monotonic time and cancellable sleeps for bounded request admission tests."""

    def __init__(self):
        """Prepare deterministic ticks and wait observations without changing process time."""
        self.now, self.waits = 100.0, []

    def __call__(self):
        """Read the current controlled monotonic value."""
        return self.now

    async def sleep(self, seconds):
        """Advance controlled time by exactly the requested wait without actual sleeping."""
        self.waits.append(seconds)
        self.now += seconds


class Provider:
    """Return the same controlled batch object or original exception while recording dispatch options."""

    def __init__(self, error=None):
        """Bind an optional original failure and an opaque result for identity-preservation checks."""
        self.error, self.result, self.calls = error, object(), []

    async def search(self, **options):
        """Observe one real port dispatch without HTTP, retries or source fabrication."""
        self.calls.append(options)
        if self.error is not None:
            raise self.error
        return self.result


@pytest.mark.asyncio
async def test_three_requests_keep_options_results_and_minimum_spacing():
    """Preserve exact objects/options and space starts rather than sleeping after a response or retrying."""
    clock, port = Clock(), Provider()
    service = SpacedSearchEvaluation(port, clock=clock, sleep=clock.sleep)
    for query in ("public alpha", "public beta", "public gamma"):
        assert await service.search(query=query, max_results=5) is port.result
    assert service.starts == [100, 105, 110] and clock.waits == [5, 5]
    assert port.calls == [
        dict(query=query, max_results=5)
        for query in ("public alpha", "public beta", "public gamma")
    ]
    assert service.backend_attempts == service.admissions == 3 and not service.busy


@pytest.mark.asyncio
async def test_already_elapsed_time_requires_no_extra_wait():
    """Count actual elapsed time and avoid adding an unnecessary fixed sleep to every call."""
    clock, port = Clock(), Provider()
    service = SpacedSearchEvaluation(port, clock=clock, sleep=clock.sleep)
    await service.search(query="first public query", max_results=5)
    clock.now += 9
    await service.search(query="second public query", max_results=5)
    assert service.starts == [100, 109] and clock.waits == []


@pytest.mark.asyncio
async def test_provider_failure_stops_later_dispatch_and_preserves_exception():
    """Keep the exact original refusal and stop the next port admission before I/O without manufacturing an empty batch."""
    error = RuntimeError("PRIVATE_CANARY")
    port = Provider(error)
    service = SpacedSearchEvaluation(port)
    with pytest.raises(RuntimeError) as caught:
        await service.search(query="first public query", max_results=5)
    assert caught.value is error
    with pytest.raises(SpacingError, match="spacing_stopped"):
        await service.search(query="second public query", max_results=5)
    assert (
        len(port.calls) == service.backend_attempts == 1 and service.blocked_calls == 1
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("bad", [-1, float("nan"), float("inf"), True, "100"])
async def test_invalid_clock_refuses_before_dispatch(bad):
    """Deny invalid clock states without sending a request or granting early admission."""
    port = Provider()
    service = SpacedSearchEvaluation(port, clock=lambda: bad)
    with pytest.raises(SpacingError, match="spacing_clock"):
        await service.search(query="public query", max_results=5)
    assert not port.calls and service.stopped and not service.busy


@pytest.mark.asyncio
async def test_early_sleep_return_cannot_dispatch_early():
    """Recheck monotonic time after waiting instead of trusting a sleep acknowledgement."""
    clock, port = Clock(), Provider()

    async def early_sleep(seconds):
        """Simulate an acknowledged wait with no elapsed clock time."""
        return None

    service = SpacedSearchEvaluation(port, clock=clock, sleep=early_sleep)
    await service.search(query="first public query", max_results=5)
    with pytest.raises(SpacingError, match="spacing_clock"):
        await service.search(query="second public query", max_results=5)
    assert len(port.calls) == 1 and service.stopped


@pytest.mark.asyncio
async def test_cancellation_during_spacing_releases_admission_without_dispatch():
    """Join a cancelled waiting caller and reject concurrent queueing before any second backend request."""
    clock, port = Clock(), Provider()
    waiting, release = asyncio.Event(), asyncio.Event()

    async def wait(seconds):
        """Hold only the caller's cancellable task with no spawned cleanup worker."""
        waiting.set()
        await release.wait()

    service = SpacedSearchEvaluation(port, clock=clock, sleep=wait)
    await service.search(query="first public query", max_results=5)
    task = asyncio.create_task(
        service.search(query="second public query", max_results=5)
    )
    await waiting.wait()
    with pytest.raises(SpacingError, match="spacing_busy"):
        await service.search(query="third public query", max_results=5)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert not service.busy and len(port.calls) == service.backend_attempts == 1


@pytest.mark.asyncio
async def test_decreasing_clock_poisoned_before_second_request():
    """Reject a backward clock instead of shortening the next request interval."""
    clock, port = Clock(), Provider()
    service = SpacedSearchEvaluation(port, clock=clock, sleep=clock.sleep)
    await service.search(query="first public query", max_results=5)
    clock.now = 99
    with pytest.raises(SpacingError, match="spacing_clock"):
        await service.search(query="second public query", max_results=5)
    assert len(port.calls) == 1 and service.stopped


@pytest.mark.asyncio
async def test_invalid_options_do_not_dispatch():
    """Preserve the fixed five-result option and fail before any provider request."""
    port = Provider()
    service = SpacedSearchEvaluation(port)
    with pytest.raises(SpacingError, match="spacing_options"):
        await service.search(query="public query", max_results=1)
    assert not port.calls


@pytest.mark.asyncio
async def test_caller_deadline_includes_spacing():
    """Keep the original caller timeout active while spacing waits rather than extending backend budgets."""
    clock, port = Clock(), Provider()

    async def wait(seconds):
        """Wait for caller cancellation without actual provider I/O."""
        await asyncio.Event().wait()

    service = SpacedSearchEvaluation(port, clock=clock, sleep=wait)
    await service.search(query="first public query", max_results=5)
    with pytest.raises(TimeoutError):
        async with asyncio.timeout(0.02):
            await service.search(query="second public query", max_results=5)
    assert len(port.calls) == 1 and not service.busy


@pytest.mark.asyncio
async def test_backend_cancellation_stops_future_dispatch():
    """Retire a cancelled backend call and prevent reuse from silently replaying a potentially uncertain request."""
    entered = asyncio.Event()

    class WaitingProvider:
        """Expose one cancellable controlled backend operation without native cleanup work."""

        async def search(self, **options):
            """Acknowledge backend entry and wait for the owning caller's cancellation."""
            entered.set()
            await asyncio.Event().wait()

    service = SpacedSearchEvaluation(WaitingProvider())
    task = asyncio.create_task(
        service.search(query="first public query", max_results=5)
    )
    await entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    with pytest.raises(SpacingError, match="spacing_stopped"):
        await service.search(query="second public query", max_results=5)
    assert service.backend_attempts == 1 and not service.busy
