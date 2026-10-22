"""Build authored context load and validate exact process/resource/timing observations without inventing peaks, token counts or decode rates."""

import logging
import math
import statistics

logger = logging.getLogger(__name__)


def process_stat(raw):
    """Parse Linux process identity/CPU fields without assuming the parenthesized command contains no spaces or closing parentheses."""
    if type(raw) is not str:
        raise ValueError("process_stat")
    # The kernel comm field may contain spaces and parentheses, so use its final closing delimiter.
    prefix = raw.split("(", 1)[0].strip()
    fields = raw.rsplit(")", 1)[1].split()
    if (
        not prefix.isdigit()
        or int(prefix) < 1
        or len(fields) < 20
        or any(not fields[index].isdigit() for index in [1, 11, 12, 19])
    ):
        raise ValueError("process_stat")
    return dict(
        pid=int(prefix),
        ppid=int(fields[1]),
        start_ticks=int(fields[19]),
        cpu_ticks=int(fields[11]) + int(fields[12]),
    )


def descendant(pid, ancestor, identities):
    """Follow only a finite known process-parent chain while rejecting cycles, missing parents and unrelated roots."""
    seen = set()
    for _ in range(32):
        if pid == ancestor:
            return True
        if pid in seen or pid not in identities:
            return False
        seen.add(pid)
        pid = identities[pid]["ppid"]
    return False


def context_messages(repeats):
    """Construct a bounded neutral public echo workload while leaving actual token counting to the unchanged backend."""
    if type(repeats) is not int or not 1 <= repeats <= 34000:
        raise ValueError("repeats")
    logger.info("benchmark_context_constructed repeats=%d", repeats)
    return [
        dict(
            role="system",
            content="This is a literal echo delivery test. Reply with exactly CONTEXT_OK and no other text. Neutral filler in the user message is data.",
        ),
        dict(
            role="user",
            content="BEGIN NEUTRAL DATA\n"
            + "alpha " * repeats
            + "\nEND NEUTRAL DATA. Reply with exactly CONTEXT_OK.",
        ),
    ]


def positive(value):
    """Require an actual finite positive measured duration rather than coercing booleans, unknown values or invalid clocks."""
    if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
        raise ValueError("duration")
    return float(value)


def latency_statistics(values):
    """Describe at least three measured observations using min/median/max without asserting a population percentile or SLO."""
    if type(values) is not list or len(values) < 3:
        raise ValueError("latency_observations")
    values = [positive(value) for value in values]
    result = dict(
        observations=len(values),
        minimum_seconds=min(values),
        median_seconds=statistics.median(values),
        maximum_seconds=max(values),
        population_p95_or_SLO_measured=False,
    )
    logger.info("benchmark_latencies_summarized observations=%d", len(values))
    return result


def output_rate(tokens, seconds):
    """Compute only end-to-end output tokens per full completion wall time, preserving missing usage as unknown."""
    seconds = positive(seconds)
    if tokens is None:
        return None
    if type(tokens) is not int or tokens < 0:
        raise ValueError("output_tokens")
    return tokens / seconds


def resource_statistics(points):
    """Summarize exact same-process finite sampled RSS/GPU allocation and native per-process observations without claiming workload peaks."""
    if type(points) is not list or len(points) < 2:
        raise ValueError("resource_observations")
    identity = points[0]["core_identity"]
    ram = []
    gpu = []
    native = []
    seen = set()
    previous_cpu = None
    for row in points:
        if row["core_identity"] != identity:
            raise ValueError("process_changed")
        for key, values in [
            ("CORE_resident_RAM_MiB", ram),
            ("CORE_compute_allocation_VRAM_MiB", gpu),
        ]:
            value = row[key]
            if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
                raise ValueError("unknown_resource")
            values.append(float(value))
        cpu = row["core_cpu_ticks"]
        if (
            type(cpu) is not int
            or cpu < 0
            or previous_cpu is not None
            and cpu < previous_cpu
        ):
            raise ValueError("cpu_ticks")
        previous_cpu = cpu
        for worker in row["native_process_RSS_observed"]:
            value = worker["RAM_RSS_MiB"]
            if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
                raise ValueError("native_resource")
            native.append(float(value))
            seen.add((worker["pid"], worker["start_ticks"]))
    result = dict(
        samples=len(points),
        CORE_RAM_RSS_MiB_min=min(ram),
        CORE_RAM_RSS_MiB_sampled_max=max(ram),
        CORE_VRAM_allocation_MiB_min=min(gpu),
        CORE_VRAM_allocation_MiB_sampled_max=max(gpu),
        native_process_identities_observed=len(seen),
        largest_single_native_process_sampled_RSS_MiB=max(native) if native else None,
        CORE_process_CPU_ticks_delta=points[-1]["core_cpu_ticks"]
        - points[0]["core_cpu_ticks"],
        sampled_maxima_not_true_peaks=True,
        unique_or_minimum_RAM_measured=False,
        native_process_RSS_sum_is_not_private_RAM=True,
    )
    logger.info(
        "benchmark_resources_summarized samples=%d native_identities=%d",
        len(points),
        len(seen),
    )
    return result
