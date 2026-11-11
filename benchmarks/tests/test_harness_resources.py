"""Test native process telemetry identity, units, failures and thread cleanup without GPU or model requirements."""

import logging
from types import SimpleNamespace

import pytest

from benchmarks.harness_resources import ResourceSampler, gpu_memory, process_memory

LOGGER = logging.getLogger(__name__)


def test_proc_reader_pins_identity_and_keeps_lifetime_hwm_separate(tmp_path):
    """Parse a command with spaces and preserve Linux KiB counters without confusing field offsets."""
    root = tmp_path / "42"
    root.mkdir()
    (root / "comm").write_text("llama-server\n")
    (root / "stat").write_text(
        "42 (llama server) " + " ".join(["S"] + ["0"] * 18 + ["12345"])
    )
    (root / "status").write_text("VmRSS:\t2048 kB\nVmHWM:\t4096 kB\n")
    assert process_memory(42, proc=tmp_path) == dict(
        pid=42, start_ticks=12345, rss_kib=2048, lifetime_hwm_kib=4096
    )
    (root / "comm").write_text("other-process\n")
    with pytest.raises(ValueError, match="explicit_llama"):
        process_memory(42, proc=tmp_path)


@pytest.mark.parametrize("text", ["42, N/A\n", "17, 600\n", "not csv\n"])
def test_gpu_unavailable_is_not_reported_as_zero(text):
    """Refuse unsupported/unreported memory instead of fabricating a zero allocation."""
    with pytest.raises(ValueError):
        gpu_memory(42, run=lambda *args, **kwargs: SimpleNamespace(stdout=text))


def test_gpu_sums_only_target_process_and_bounds_command():
    """Measure summed process allocations without contacting another endpoint or invoking a shell."""

    def query(arguments, **options):
        """Inspect the finite native GPU query and return controlled multiple-device rows."""
        assert arguments[0] == "nvidia-smi" and options["timeout"] == 2
        assert "shell" not in options
        return SimpleNamespace(stdout="42, 1024\n17, 900\n42, 512\n")

    assert gpu_memory(42, run=query) == 1536


def test_sampler_joins_on_exception_and_reports_sampled_units():
    """Preserve a measured failure while retaining both baseline and final observations."""

    def memory(pid):
        """Return a stable process without reading actual machine memory."""
        return dict(pid=pid, start_ticks=5, rss_kib=2048, lifetime_hwm_kib=4096)

    sampler = ResourceSampler(42, memory=memory, gpu=lambda pid: 1024)
    with pytest.raises(RuntimeError, match="measured_failure"):
        with sampler:
            raise RuntimeError("measured_failure")
    report = sampler.report()
    assert report["status"] == "COMPLETE" and len(report["samples"]) == 2
    assert report["sampled_peak_rss_kib"] == 2048 and report["lifetime_hwm_kib"] == 4096
    assert (
        report["sampled_peak_gpu_process_mib"] == 1024 and not sampler.thread.is_alive()
    )
    LOGGER.info("test_resource_sampler_owned_thread_joined")


def test_replaced_pid_and_missing_final_metric_remain_incomplete():
    """Flag identity drift after baseline rather than reusing a different process's allocation."""
    calls = []

    def memory(pid):
        """Replace the fixture start tick on the final read."""
        calls.append(pid)
        return dict(pid=pid, start_ticks=len(calls), rss_kib=1, lifetime_hwm_kib=1)

    with ResourceSampler(42, memory=memory, gpu=lambda pid: 2) as sampler:
        pass
    assert sampler.report()["status"] == "INCOMPLETE"
    with pytest.raises(ValueError, match="sampler_not_reusable"):
        with sampler:
            pass


def test_global_pid_identity_is_checked_before_each_new_attempt():
    """Reject a recycled native PID between measured requests instead of silently changing targets."""

    def memory(pid):
        """Return a different process start tick from the frozen global identity."""
        return dict(pid=pid, start_ticks=8, rss_kib=1, lifetime_hwm_kib=1)

    sampler = ResourceSampler(42, memory=memory, gpu=lambda pid: 2, expected_start=7)
    with pytest.raises(ValueError, match="sampled_process_replaced"):
        with sampler:
            pass
    assert sampler.thread is None
