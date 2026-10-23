"""Verify bounded content-free aggregate inference counters, explicit unavailable token timings and truthful failure/cancellation accounting."""

import asyncio
from dataclasses import replace

import pytest
from test_profile_prompts import Port

from src.application.ports.inference import InferenceFailure
from src.application.services.inference_observability import InferenceObservability


@pytest.mark.asyncio
async def test_exact_usage_latency_no_fake_ttft_or_content_logging(caplog):
    """Count real complete port usage and measured wall time while omitting all private model/request/response data."""
    caplog.set_level("INFO")
    clock = iter([1, 1.25])
    port = Port()
    observed = InferenceObservability(port, clock=lambda: next(clock))
    result = await observed.complete(
        profile="core", messages=[dict(role="user", content="PRIVATE-TOKEN-CANARY")]
    )
    assert result.content == "private reply" and len(port.calls) == 1
    snapshot = observed.snapshot()
    assert snapshot["ttft_ms"] is None and snapshot["decode_tokens_per_second"] is None
    core = snapshot["profiles"]["core"]
    assert (
        core["completed"] == 1
        and core["input_tokens"] == 12
        and core["output_tokens"] == 3
    )
    assert (
        core["latency_ms_total"] == 250
        and core["active"] == 0
        and core["usage_samples"] == 1
    )
    assert (
        "PRIVATE" not in caplog.text
        and "private reply" not in caplog.text
        and "fixture-core" not in caplog.text
    )
    core["completed"] = 999
    assert observed.snapshot()["profiles"]["core"]["completed"] == 1


@pytest.mark.parametrize(
    "clock", [iter([5, 4]), iter([float("nan"), 6]), iter([True, 7])]
)
@pytest.mark.asyncio
async def test_invalid_clock_is_unavailable_never_zero(clock):
    """Do not fabricate a latency sample when timing input is invalid or moves backwards."""
    observed = InferenceObservability(Port(), clock=lambda: next(clock))
    await observed.complete(profile="core")
    core = observed.snapshot()["profiles"]["core"]
    assert core["latency_samples"] == 0 and core["timing_unavailable"] == 1


@pytest.mark.asyncio
async def test_error_text_does_not_become_a_trace_label(caplog):
    """Count finite failures while passing the original dependency exception to its established caller boundary."""

    class Failed:
        """Raise a private test exception solely to verify safe metric/log labels."""

        async def complete(self, **request):
            """Avoid logging the authored private failure text at the telemetry layer."""
            raise RuntimeError("PRIVATE-CREDENTIAL-CANARY")

    observed = InferenceObservability(Failed())
    with pytest.raises(RuntimeError):
        await observed.complete(profile="core")
    assert (
        "PRIVATE" not in caplog.text
        and observed.snapshot()["profiles"]["core"]["failed"] == 1
    )


@pytest.mark.asyncio
async def test_cancelled_work_is_counted_after_dependency_cleanup():
    """Keep active counters until the actual awaited dependency has cleaned up on cancellation."""
    entered, joined = asyncio.Event(), asyncio.Event()

    class Blocked:
        """Expose fixture-native cleanup ordering for cancellation accounting."""

        async def complete(self, **request):
            """Remain active until cancellation runs the dependency's final cleanup."""
            entered.set()
            try:
                await asyncio.Event().wait()
            finally:
                joined.set()

    observed = InferenceObservability(Blocked())
    task = asyncio.create_task(observed.complete(profile="core"))
    await asyncio.wait_for(entered.wait(), 1)
    assert observed.snapshot()["profiles"]["core"]["active"] == 1
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert joined.is_set() and observed.snapshot()["profiles"]["core"]["cancelled"] == 1
    assert observed.snapshot()["profiles"]["core"]["active"] == 0


@pytest.mark.parametrize(
    "changes",
    [dict(input_tokens=True), dict(output_tokens=-1), dict(finish_reason="length")],
)
@pytest.mark.asyncio
async def test_bad_result_is_failed_not_successful_usage(changes):
    """Reject malformed or truncated responses instead of inflating successful token/quality metrics."""
    observed = InferenceObservability(
        Port(transform=lambda result: replace(result, **changes))
    )
    with pytest.raises(InferenceFailure):
        await observed.complete(profile="core")
    core = observed.snapshot()["profiles"]["core"]
    assert core["failed"] == 1 and core["completed"] == 0 and core["usage_samples"] == 0


@pytest.mark.asyncio
async def test_unknown_profile_never_delegates_or_adds_high_cardinality_labels():
    """Refuse request-controlled telemetry labels before calling a backend or changing fixed-profile counters."""
    port = Port()
    observed = InferenceObservability(port)
    with pytest.raises(InferenceFailure):
        await observed.complete(profile="PRIVATE-SECRET")
    assert not port.calls and set(observed.snapshot()["profiles"]) == {
        "core",
        "unrestricted",
    }


@pytest.mark.parametrize("points", [[0.0, 1e308], [10**1000, 1.0]])
@pytest.mark.asyncio
async def test_extreme_clock_values_cannot_overflow_or_mask_valid_completion(points):
    """Treat numeric clock overflow as unavailable telemetry while preserving the original successful inference result."""
    clock = iter(points)
    observed = InferenceObservability(Port(), clock=lambda: next(clock))
    result = await observed.complete(profile="core")
    assert result.content == "private reply"
    core = observed.snapshot()["profiles"]["core"]
    assert (
        core["completed"] == 1
        and core["latency_samples"] == 0
        and core["timing_unavailable"] == 1
    )
