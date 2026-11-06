"""Verify honest SSE timing extraction distinguishes first text, completion, usage, native rates and unsupported client token boundaries."""

import json

import pytest

from scripts.streaming_timing_probe import TimingError, measure


def frame(content=None, *, finish=None, **extra):
    """Build one fixed native-like SSE event with no hidden token boundaries or synthetic timing claims."""
    return "data: " + json.dumps(
        dict(
            model="fixture-core",
            choices=[dict(index=0, delta=dict(content=content), finish_reason=finish)],
            **extra,
        )
    )


async def lines(values):
    """Yield only authored finite SSE lines without network or model execution."""
    for value in values:
        yield value


def stream():
    """Include an empty initial event, two content chunks, explicit stop, usage and a terminal marker."""
    return [
        frame(),
        frame("Cedar"),
        frame(" blue", finish="stop"),
        'data: {"model":"fixture-core","choices":[],"usage":{"prompt_tokens":8,"completion_tokens":3}}',
        "data: [DONE]",
    ]


@pytest.mark.asyncio
async def test_first_text_timing_is_not_first_event_or_fabricated_decode_rate():
    """Measure first content after one empty role event and leave unobserved token-boundary rates explicitly absent."""
    clock = iter([1.2, 1.4, 1.5])
    result = await measure(
        lines(stream()), model_id="fixture-core", started=1, clock=lambda: next(clock)
    )
    assert (
        result["client_ttft_ms"] == pytest.approx(200)
        and result["client_total_ms"] == 500
    )
    assert (
        result["client_end_to_end_tokens_per_second"] == 6
        and result["client_decode_tokens_per_second"] is None
    )
    assert (
        result["native_reported_decode_tokens_per_second"] is None
        and result["content_chunks"] == 2
    )


@pytest.mark.parametrize(
    "fault",
    [
        "truncated",
        "wrong_model",
        "no_usage",
        "length",
        "duplicate_usage",
        "backward",
        "oversize",
    ],
)
@pytest.mark.asyncio
async def test_invalid_stream_cannot_publish_timing_evidence(fault):
    """Reject truncated/mismatched/incomplete/invalid-clock streams rather than reporting successful decode measurements."""
    values = stream()
    if fault == "truncated":
        values.pop()
    if fault == "wrong_model":
        values[1] = values[1].replace("fixture-core", "foreign")
    if fault == "no_usage":
        values.pop(-2)
    if fault == "length":
        values[2] = values[2].replace('"stop"', '"length"')
    if fault == "duplicate_usage":
        values.insert(-1, values[-2])
    if fault == "oversize":
        values.insert(0, ":" + "x" * 65537)
    clock = iter([1.2, 1.1, 1.5] if fault == "backward" else [1.2, 1.4, 1.5])
    with pytest.raises(TimingError):
        await measure(
            lines(values), model_id="fixture-core", started=1, clock=lambda: next(clock)
        )


@pytest.mark.asyncio
async def test_native_rate_is_labeled_server_reported_not_client_measurement():
    """Keep the optional native decode rate separate from application latency and SSE chunk observations."""
    values = stream()
    values[-2] = (
        'data: {"model":"fixture-core","choices":[],"usage":{"prompt_tokens":8,"completion_tokens":3},"timings":{"predicted_per_second":42.5}}'
    )
    clock = iter([1.2, 1.4, 1.5])
    result = await measure(
        lines(values), model_id="fixture-core", started=1, clock=lambda: next(clock)
    )
    assert (
        result["native_reported_decode_tokens_per_second"] == 42.5
        and result["native_rate_availability"] == "server_reported"
    )
    assert result["client_decode_tokens_per_second"] is None


@pytest.mark.parametrize("started", [True, float("nan"), -1])
@pytest.mark.asyncio
async def test_invalid_start_clock_cannot_create_a_timing_sample(started):
    """Reject invalid or coerced timing origins before consuming any stream data."""
    with pytest.raises(TimingError):
        await measure(lines(stream()), model_id="fixture-core", started=started)
