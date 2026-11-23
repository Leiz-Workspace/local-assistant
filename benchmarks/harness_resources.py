"""Sample an explicitly selected native CORE process without changing its residency, configuration or limits."""

import logging
import subprocess
import threading
import time
from pathlib import Path

LOGGER = logging.getLogger(__name__)


def process_memory(pid, *, proc=Path("/proc")):
    """Read RSS, lifetime high-water RSS and process identity without inspecting environment or arguments."""
    root = proc / str(pid)
    command = (root / "comm").read_text().strip()
    if command != "llama-server":
        raise ValueError("explicit_llama_server_pid_required")
    tail = (root / "stat").read_text().rsplit(")", 1)[1].split()
    started = int(tail[19])
    values = {}
    for line in (root / "status").read_text().splitlines():
        if line.startswith(("VmRSS:", "VmHWM:")):
            name, amount, unit = line.split()
            if unit != "kB" or int(amount) < 0:
                raise ValueError("invalid_process_memory")
            values[name[:-1]] = int(amount)
    if set(values) != {"VmRSS", "VmHWM"}:
        raise ValueError("process_memory_unavailable")
    if int((root / "stat").read_text().rsplit(")", 1)[1].split()[19]) != started:
        raise ValueError("sampled_process_replaced")
    return dict(
        pid=pid,
        start_ticks=started,
        rss_kib=values["VmRSS"],
        lifetime_hwm_kib=values["VmHWM"],
    )


def gpu_memory(pid, *, run=subprocess.run):
    """Read nvidia-smi process allocations in MiB with a bounded command and no shell or new dependency."""
    result = run(
        [
            "nvidia-smi",
            "--query-compute-apps=pid,used_memory",
            "--format=csv,noheader,nounits",
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=2,
    )
    if len(result.stdout) > 65536:
        raise ValueError("gpu_query_too_large")
    amounts = []
    for line in result.stdout.splitlines():
        parts = [item.strip() for item in line.split(",")]
        if len(parts) != 2 or not parts[0].isdigit():
            raise ValueError("invalid_gpu_process_row")
        if int(parts[0]) == pid:
            if not parts[1].isdigit():
                raise ValueError("gpu_allocation_unavailable")
            amounts.append(int(parts[1]))
    if not amounts:
        raise ValueError("gpu_process_not_reported")
    return sum(amounts)


class ResourceSampler:
    """Own a bounded sampling thread for one request and label sampled peaks separately from lifetime counters."""

    def __init__(
        self,
        pid,
        *,
        memory=process_memory,
        gpu=gpu_memory,
        interval=0.2,
        expected_start=None,
    ):
        """Pin a real process identity and inject deterministic readers for isolated tests."""
        if type(pid) is not int or pid <= 0 or not 0.01 <= interval <= 1:
            raise ValueError("invalid_sampler_options")
        self.pid, self.memory, self.gpu, self.interval = pid, memory, gpu, interval
        self.identity = (pid, expected_start) if expected_start is not None else None
        self.samples, self.errors = [], []
        self.stop = threading.Event()
        self.thread = None
        self.started = None

    def sample(self):
        """Capture one finite observation while rejecting PID replacement and preserving reader failures."""
        value = self.memory(self.pid)
        identity = (value["pid"], value["start_ticks"])
        if self.identity is not None and identity != self.identity:
            raise ValueError("sampled_process_replaced")
        self.identity = identity
        value = dict(
            value,
            gpu_process_mib=self.gpu(self.pid),
            elapsed_seconds=round(time.monotonic() - self.started, 6),
        )
        self.samples.append(value)

    def worker(self):
        """Take periodic measurements until stopped or a finite error/time/sample boundary is reached."""
        while not self.stop.wait(self.interval):
            try:
                if len(self.samples) >= 700 or time.monotonic() - self.started > 130:
                    raise ValueError("sampler_limit")
                self.sample()
            except Exception:
                self.errors.append("sample_failed")
                LOGGER.warning("harness_resource_sample_failed")
                return

    def __enter__(self):
        """Require usable baseline metrics before starting one owned background sampler."""
        if self.thread is not None:
            raise ValueError("sampler_not_reusable")
        self.started = time.monotonic()
        self.sample()
        self.thread = threading.Thread(
            target=self.worker, daemon=True, name="harness-resource-sampler"
        )
        self.thread.start()
        LOGGER.info("harness_resource_sampling_started pid=%d", self.pid)
        return self

    def __exit__(self, *error):
        """Stop and join the owned sampler even when the measured operation failed or was interrupted."""
        self.stop.set()
        self.thread.join(timeout=3)
        if self.thread.is_alive():
            raise RuntimeError("resource_sampler_not_joined")
        try:
            self.sample()
        except Exception:
            self.errors.append("final_sample_failed")
            LOGGER.warning("harness_resource_final_sample_failed")
        LOGGER.info(
            "harness_resource_sampling_stopped samples=%d errors=%d",
            len(self.samples),
            len(self.errors),
        )

    def report(self):
        """Return raw observations and conservative units without treating lifetime HWM as a request peak."""
        if self.thread is None or self.thread.is_alive() or not self.stop.is_set():
            raise ValueError("sampler_not_finished")
        baseline = self.samples[0]
        return {
            "status": "COMPLETE" if not self.errors else "INCOMPLETE",
            "interval_seconds": self.interval,
            "baseline": baseline,
            "sampled_peak_rss_kib": max(row["rss_kib"] for row in self.samples),
            "sampled_peak_gpu_process_mib": max(
                row["gpu_process_mib"] for row in self.samples
            ),
            "lifetime_hwm_kib": max(row["lifetime_hwm_kib"] for row in self.samples),
            "samples": self.samples,
            "errors": self.errors,
            "limits": "Sampled process allocation/RSS; lifetime HWM is not per-request, GPU allocation is not tensor usage, cached warm resident process; sub-interval peaks and other workload interference are not excluded.",
        }
