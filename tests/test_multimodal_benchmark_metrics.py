"""Protect finite D67 context/resource/timing metrics against unknown values, process replacement and misleading peak/decode labels."""

from copy import deepcopy

import pytest

from tests.multimodal_benchmark_metrics import (
    context_messages,
    descendant,
    latency_statistics,
    output_rate,
    process_stat,
    resource_statistics,
)


def point(cpu=100):
    """Build one controlled same-process resource observation with separate CPU RAM and GPU allocation values."""
    return dict(
        core_identity=dict(pid=12, start_ticks=900),
        CORE_resident_RAM_MiB=100.0,
        CORE_compute_allocation_VRAM_MiB=200.0,
        core_cpu_ticks=cpu,
        native_process_RSS_observed=[],
    )


def test_process_comm_with_parentheses_and_spaces_does_not_shift_identity_or_cpu_fields():
    """Parse fields after the final kernel comm delimiter rather than splitting a name into false resource values."""
    values = ["S", "1", *["0"] * 9, "15", "7", *["0"] * 6, "900"]
    assert process_stat("12 (worker (with) spaces) " + " ".join(values)) == dict(
        pid=12, ppid=1, start_ticks=900, cpu_ticks=22
    )


@pytest.mark.parametrize("raw", [None, "broken", "0 (x) S 1", "12 (x) S -1"])
def test_incomplete_or_invalid_process_fields_refuse_observation(raw):
    """Keep unsupported process identity data unavailable rather than substituting a fabricated zero."""
    with pytest.raises((ValueError, IndexError)):
        process_stat(raw)


def test_process_parent_chain_excludes_unrelated_or_cyclic_workers():
    """Associate only actual descendants and refuse missing/cyclic parent chains without scanning arbitrary private process arguments."""
    identities = {
        10: dict(ppid=1),
        11: dict(ppid=10),
        12: dict(ppid=11),
        20: dict(ppid=21),
        21: dict(ppid=20),
    }
    assert (
        descendant(12, 10, identities)
        and not descendant(12, 30, identities)
        and not descendant(20, 10, identities)
    )


@pytest.mark.parametrize("value", [True, 0, -1, 34001, "128"])
def test_context_repetitions_are_bounded_parameters_not_assumed_token_counts(value):
    """Reject invalid load inputs before constructing a body or asking a model to process it."""
    with pytest.raises(ValueError):
        context_messages(value)


def test_context_fixture_contains_complete_current_turn_and_unambiguous_echo_protocol():
    """Preserve full neutral filler and original echo instruction without silent text truncation."""
    messages = context_messages(128)
    assert len(messages) == 2 and messages[0]["role"] == "system"
    assert messages[1]["content"].count("alpha ") == 128 and messages[1][
        "content"
    ].endswith("CONTEXT_OK.")


def test_latency_statistics_describe_three_observations_without_population_claim():
    """Report exact min/median/max and preserve nonstreaming end-to-end rate terminology."""
    value = latency_statistics([1.0, 5.0, 2.0])
    assert (
        value["minimum_seconds"] == 1
        and value["median_seconds"] == 2
        and value["maximum_seconds"] == 5
    )
    assert value["population_p95_or_SLO_measured"] is False
    assert output_rate(10, 2) == 5 and output_rate(None, 2) is None


@pytest.mark.parametrize("value", [None, True, 0, -1, float("nan"), float("inf")])
def test_invalid_measurements_are_not_zero_filled_or_percentile_scored(value):
    """Refuse missing or nonfinite wall measurements rather than promoting them into a successful performance result."""
    with pytest.raises(ValueError):
        latency_statistics([1, 2, value])
    with pytest.raises(ValueError):
        output_rate(1, value)


@pytest.mark.parametrize("tokens", [True, -1, "10"])
def test_output_rate_rejects_coerced_or_negative_usage(tokens):
    """Keep backend usage counters distinct from guessed or coerced token quantities."""
    with pytest.raises(ValueError):
        output_rate(tokens, 1)


def test_sampled_resource_maxima_are_separate_quantities_and_missed_native_workers_remain_unknown():
    """Preserve RAM/VRAM units and avoid calling no native observations zero worker RAM."""
    values = [point(), point(105)]
    values[1]["CORE_resident_RAM_MiB"] = 110
    result = resource_statistics(values)
    assert (
        result["CORE_RAM_RSS_MiB_sampled_max"] == 110
        and result["CORE_VRAM_allocation_MiB_sampled_max"] == 200
    )
    assert (
        result["largest_single_native_process_sampled_RSS_MiB"] is None
        and result["CORE_process_CPU_ticks_delta"] == 5
    )
    assert (
        result["sampled_maxima_not_true_peaks"] is True
        and result["unique_or_minimum_RAM_measured"] is False
    )


@pytest.mark.parametrize(
    "key,value",
    [
        ("CORE_resident_RAM_MiB", None),
        ("CORE_compute_allocation_VRAM_MiB", float("nan")),
        ("CORE_compute_allocation_VRAM_MiB", -1),
        ("core_cpu_ticks", 99),
        ("core_identity", dict(pid=13, start_ticks=900)),
        ("core_identity", dict(pid=12, start_ticks=901)),
    ],
)
def test_unknown_resource_or_reused_process_identity_refuses_complete_measurement(
    key, value
):
    """Reject unsupported RAM/VRAM and changed/decreasing process counters instead of combining different runtime instances."""
    values = [point(), deepcopy(point(101))]
    values[1][key] = value
    with pytest.raises(ValueError):
        resource_statistics(values)


def test_native_process_rss_is_largest_observed_process_and_never_private_memory_sum():
    """Preserve individual worker samples and identities without adding shared pages into a supposed private memory requirement."""
    values = [point(), point(102)]
    values[0]["native_process_RSS_observed"] = [
        dict(pid=20, start_ticks=1000, RAM_RSS_MiB=5),
        dict(pid=21, start_ticks=1001, RAM_RSS_MiB=7),
    ]
    values[1]["native_process_RSS_observed"] = [
        dict(pid=20, start_ticks=1000, RAM_RSS_MiB=6)
    ]
    result = resource_statistics(values)
    assert (
        result["largest_single_native_process_sampled_RSS_MiB"] == 7
        and result["native_process_identities_observed"] == 2
    )
    assert result["native_process_RSS_sum_is_not_private_RAM"] is True


@pytest.mark.parametrize("value", [None, True, -1, float("nan")])
def test_unknown_native_process_samples_are_not_coerced_to_zero(value):
    """Refuse malformed native resource values rather than hiding them in a successful sampled maximum."""
    values = [point(), point(102)]
    values[1]["native_process_RSS_observed"] = [
        dict(pid=20, start_ticks=1000, RAM_RSS_MiB=value)
    ]
    with pytest.raises(ValueError):
        resource_statistics(values)
