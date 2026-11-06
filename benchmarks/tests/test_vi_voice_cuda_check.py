"""Verify CUDA quality noninferiority, original physical/VRAM guards and conditional native scope without models."""

import copy
import json
import time
from types import SimpleNamespace
import sys

import pytest

from benchmarks.scripts import vi_voice_cuda_check as target


def metrics():
    """Create two complete authored20case language aggregates without real ASR predictions."""
    values = dict(
        observed_speech_cases=20,
        reference_words=100,
        reference_characters=500,
        word_edits=10,
        character_edits=20,
    )
    return dict(
        coverage_complete=True,
        expected_cases=40,
        languages={"vi_vn": dict(values), "en_us": dict(values)},
    )


def test_both_language_metrics_must_be_no_worse():
    """Allow equal or improved edits while retaining fixed original reference denominators."""
    cpu = metrics()
    gpu = copy.deepcopy(cpu)
    gpu["languages"]["vi_vn"]["word_edits"] = 9
    assert target.quality_pass(cpu, gpu)


@pytest.mark.parametrize(
    "bad",
    ["coverage", "count", "language", "word", "char", "denominator", "case_count"],
)
def test_partial_or_degraded_quality_is_not_promoted(bad):
    """Prevent a fast GPU from passing by dropping a language/case or changing reference counts."""
    cpu = metrics()
    gpu = copy.deepcopy(cpu)
    if bad == "coverage":
        gpu["coverage_complete"] = False
    elif bad == "count":
        gpu["expected_cases"] = 39
    elif bad == "language":
        del gpu["languages"]["en_us"]
    elif bad == "word":
        gpu["languages"]["vi_vn"]["word_edits"] = 11
    elif bad == "char":
        gpu["languages"]["en_us"]["character_edits"] = 21
    elif bad == "denominator":
        gpu["languages"]["vi_vn"]["reference_words"] = 101
    else:
        gpu["languages"]["vi_vn"]["observed_speech_cases"] = 19
    assert target.quality_pass(cpu, gpu) is False


@pytest.mark.parametrize("mode,max_requests", [("quality", 40), ("voice", 4)])
def test_gpu_worker_has_separate_phase_scope_and_unchanged_ram_guard(
    tmp_path, mode, max_requests
):
    """Keep explicit CUDA capabilities separate from the CPU manifest without modifying its bytes."""
    scope = tmp_path / "scope.json"
    scope.write_text(
        json.dumps(
            dict(
                role="qwen3-asr-0.6b",
                model="qwen3-asr-0.6b",
                cpu_threads=8,
                max_requests=4,
                native_authorized=True,
                scope_sha256="a" * 64,
            )
        )
    )
    before = scope.read_bytes()
    worker = target.Worker(
        "qwen3-asr-0.6b",
        tmp_path / "worker",
        time.monotonic() + 10,
        99,
        scope,
        8,
        tmp_path,
        SimpleNamespace(),
        mode,
        root=tmp_path / "current-campaign",
    )
    capability = json.loads(worker.scope_path.read_text())
    assert capability["mode"] == mode and capability["max_requests"] == max_requests
    assert scope.read_bytes() == before and worker.samples == 0
    assert worker.root == tmp_path / "current-campaign"


@pytest.mark.parametrize(
    "used,free,passed",
    [
        (4 * 1024**3, 2 * 1024**3, True),
        (int(4.6 * 1024**3), 2 * 1024**3, False),
        (1, 1024**3, False),
    ],
)
def test_gpu_allocation_and_global_headroom_do_not_relax_cpu_limits(
    monkeypatch, tmp_path, used, free, passed
):
    """Enforce both new GPU limits while invoking the original aggregate physical-RAM guard first."""
    scope = tmp_path / "scope.json"
    scope.write_text("{}")
    monitor = SimpleNamespace(sample=lambda pids: (used, free))
    worker = target.Worker(
        "qwen3-asr-0.6b",
        tmp_path / "worker",
        time.monotonic() + 10,
        99,
        scope,
        8,
        tmp_path,
        monitor,
    )
    worker.process = SimpleNamespace(pid=77)
    calls = []
    monkeypatch.setattr(
        target.resident.Worker, "check", lambda self: calls.append("physical_guard")
    )
    monkeypatch.setattr(target.original, "process_tree", lambda pid: {pid})
    if passed:
        worker.check()
    else:
        with pytest.raises(ValueError, match="cuda_vram"):
            worker.check()
    assert calls == ["physical_guard"]


def test_monitor_registers_its_module_before_vendor_initialization(monkeypatch):
    """Support the vendor's module-based exception construction without modifying the CUDA environment."""
    called = []
    name = "_voice_cuda_nvml_fixture"
    module = SimpleNamespace(
        nvmlInit=lambda: called.append("init"),
        nvmlDeviceGetHandleByIndex=lambda i: "device",
        nvmlDeviceGetComputeRunningProcesses_v3=lambda d: [
            SimpleNamespace(pid=1, usedGpuMemory=20),
            SimpleNamespace(pid=2, usedGpuMemory=30),
        ],
        nvmlDeviceGetMemoryInfo=lambda d: SimpleNamespace(free=100),
        nvmlShutdown=lambda: called.append("shutdown"),
    )

    def execute(value):
        """Require module registration before executing vendor-style class initialization."""
        assert sys.modules[name] is value and sys.dont_write_bytecode is True

    monkeypatch.setattr(
        target.importlib.util,
        "spec_from_file_location",
        lambda *args: SimpleNamespace(
            name=name, loader=SimpleNamespace(exec_module=execute)
        ),
    )
    monkeypatch.setattr(target.importlib.util, "module_from_spec", lambda spec: module)
    monkeypatch.setitem(sys.modules, name, None)
    before = sys.dont_write_bytecode
    monitor = target.Monitor()
    assert monitor.sample({2}) == (30, 100)
    assert sys.dont_write_bytecode == before
    monitor.close()
    assert called == ["init", "shutdown"]


@pytest.mark.parametrize("mode", ["quality", "voice", "probe"])
def test_gpu_namespace_is_explicit_and_cpu_original_scope_is_unchanged(
    monkeypatch, tmp_path, mode
):
    """Change only the ASR runtime/device/virtual mapping while keeping network isolation and original CPUpackage mount."""

    def base(*args):
        """Describe one original CPU ASR command without private package or model files."""
        return [
            "/usr/bin/taskset",
            "--cpu-list",
            "0,1",
            "/usr/bin/bwrap",
            "--unshare-all",
            "--ro-bind",
            str(target.original.ROOT / "samples"),
            "/samples",
            "--setenv",
            "CUDA_VISIBLE_DEVICES",
            "",
            "--setenv",
            "OMP_NUM_THREADS",
            "2",
            "--remount-ro",
            "/",
            "--",
            "/usr/bin/prlimit",
            "--as=8589934592",
            "--",
            "/venv/bin/python",
            "/app/worker.py",
            "role",
        ]

    original_exists = target.Path.exists
    monkeypatch.setattr(target.original, "namespace", base)
    monkeypatch.setattr(
        target.Path,
        "exists",
        lambda p: True if str(p).startswith("/dev/nvidia") else original_exists(p),
    )
    args = target.command(
        "qwen3-asr-0.6b",
        tmp_path / "out",
        tmp_path / "scope.json",
        "a" * 64,
        tmp_path / "quality",
        mode=mode,
    )
    assert "--as=68719476736" in args and "--as=8589934592" not in args
    assert (
        "--unshare-all" in args and args[args.index("CUDA_VISIBLE_DEVICES") + 1] == "0"
    )
    assert "/dev/nvidia0" in args and "/cuda-venv" in args
    source = args[args.index("/samples") - 1]
    assert source == str(
        target.original.ROOT / "samples" if mode == "voice" else tmp_path / "quality"
    )
    assert args[-3:] == ["/cuda-venv/bin/python", "/app/" + target.WORKER, "a" * 64]
    with pytest.raises(ValueError, match="cuda_command_role"):
        target.command("turbo", tmp_path, tmp_path, "a" * 64, tmp_path, mode=mode)
    with pytest.raises(ValueError, match="cuda_command_mode"):
        target.command(
            "qwen3-asr-0.6b", tmp_path, tmp_path, "a" * 64, tmp_path, mode="unknown"
        )


def test_original_waveform_integrity_refuses_detector_copy(tmp_path):
    """Exercise the real ASR loader with distinct original and amplified bytes, preserving the original request digest."""
    import hashlib
    import numpy as np
    from scripts.asr_evaluation_worker import load_waveform

    original = tmp_path / "original"
    detector = tmp_path / "detector"
    original.mkdir()
    detector.mkdir()
    values = np.full(16000, 0.125, dtype="<f4")
    (original / "speech.f32").write_bytes(values.tobytes())
    (detector / "speech.f32").write_bytes((values * 4).tobytes())
    message = dict(
        filename="speech.f32",
        sample_count=16000,
        waveform_sha256=hashlib.sha256(values.tobytes()).hexdigest(),
    )
    assert np.array_equal(load_waveform(message, original), values)
    with pytest.raises(ValueError, match="asr_waveform_integrity"):
        load_waveform(message, detector)
