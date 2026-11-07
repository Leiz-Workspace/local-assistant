"""Verify fixed worker mounts, offline execution and resource guards without invoking model processes."""

from types import SimpleNamespace

import httpx
import pytest

from src.application.services.voice_pipeline import VoiceError
from src.infrastructure.voice import ipc
from src.infrastructure.voice.core import BorrowedCore
from src.infrastructure.voice.manifest import PATHS, PINS
from src.infrastructure.voice.sandbox import command


@pytest.mark.parametrize(
    "role,virtual,cpu",
    [
        ("vad", 3 * 1024**3, "180:181"),
        ("turbo", 8 * 1024**3, "1200:1201"),
        ("qwen3-asr-0.6b", 64 * 1024**3, "1200:1201"),
    ],
)
def test_offline_namespace_retains_profiles(tmp_path, monkeypatch, role, virtual, cpu):
    """Retain read-only assets, fixed affinity, no network and exact virtual/CPU caps for each declared role."""
    output = tmp_path / "output"
    output.mkdir(mode=0o700)
    settings = SimpleNamespace(paths={name: tmp_path / name for name in PATHS})
    original = ipc.Path.exists

    def devices(path):
        """Provide only synthetic CUDA device existence for inspecting a command that will never execute."""
        return True if str(path).startswith("/dev/nvidia") else original(path)

    monkeypatch.setattr(ipc.Path, "exists", devices)
    args = command(
        settings, role, output, tmp_path / "samples", tmp_path / "scope.json", "a" * 64
    )
    assert (
        "--unshare-all" in args and "--clearenv" in args and "--die-with-parent" in args
    )
    assert f"--as={virtual}" in args and f"--cpu={cpu}" in args
    assert "--core=0" in args and "--nofile=128" in args and "--fsize=16777216" in args
    assert args[args.index("--cpu-list") + 1] == (
        "0,1" if role == "vad" else "0,1,2,3,4,5,6,7"
    )
    assert "src.infrastructure.voice.worker" in args
    assert not any("benchmarks" in a or "data/backups" in a for a in args)
    assert "PYTHONPYCACHEPREFIX" in args and "/tmp/pycache" in args


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["vad", "qwen3-asr-0.6b", "turbo"])
async def test_preload_memory_gate_prevents_any_worker_start(
    tmp_path, monkeypatch, role
):
    """Refuse inadequate original preload headroom before output creation, subprocess spawn or model import."""
    monkeypatch.setattr(ipc, "mem_available", lambda: 13 * 1024**3)
    runtime = SimpleNamespace(root=tmp_path)
    worker = ipc.IPCWorker(runtime, role)
    with pytest.raises(VoiceError):
        await worker.start()
    assert worker.process is None and not worker.directory.exists()


def monitor_with(rows):
    """Build a monitor over fixed NVML rows that exposes no GPU reset or process-control calls."""
    monitor = ipc.Monitor.__new__(ipc.Monitor)
    monitor.device = 0
    monitor.module = SimpleNamespace(
        nvmlDeviceGetComputeRunningProcesses_v3=lambda device: list(rows)
    )
    return monitor


def test_unknown_compute_is_refused_without_process_actions():
    """Observe external GPU contention without resetting a GPU or signalling another process."""
    monitor = monitor_with([SimpleNamespace(pid=123, usedGpuMemory=None)])
    monitor.require_owned_compute({123})
    with pytest.raises(VoiceError):
        monitor.require_owned_compute({456})


@pytest.mark.parametrize(
    "sizes",
    [
        [223 * 1024**2],
        [213 * 1024**2, 46 * 1024**2, 272 * 1024**2],
        [ipc.FOREIGN_VRAM_LIMIT],
    ],
)
def test_small_known_foreign_desktop_allocations_are_tolerated(sizes, caplog):
    """ADR176: desktop GPU contexts up to 1 GiB in total do not block owned voice work."""
    owned = SimpleNamespace(pid=1, usedGpuMemory=3 * 1024**3)
    foreign = [
        SimpleNamespace(pid=100 + i, usedGpuMemory=s) for i, s in enumerate(sizes)
    ]
    monitor = monitor_with([owned, *foreign])
    with caplog.at_level("INFO"):
        monitor.require_owned_compute({1})
        monitor.require_owned_compute({1})
    logged = [r.getMessage() for r in caplog.records if "foreign_gpu" in r.getMessage()]
    assert logged == [
        f"voice_foreign_gpu_tolerated processes={len(sizes)} mib={sum(sizes) // 1024**2}"
    ]


@pytest.mark.parametrize(
    "rows",
    [
        [SimpleNamespace(pid=7, usedGpuMemory=ipc.FOREIGN_VRAM_LIMIT + 1)],
        [
            SimpleNamespace(pid=7, usedGpuMemory=ipc.FOREIGN_VRAM_LIMIT // 2 + 1),
            SimpleNamespace(pid=8, usedGpuMemory=ipc.FOREIGN_VRAM_LIMIT // 2),
        ],
        [SimpleNamespace(pid=7, usedGpuMemory=None)],
        [SimpleNamespace(pid=7)],
        [SimpleNamespace(pid=7, usedGpuMemory=2**64 - 1)],
        [SimpleNamespace(pid=7, usedGpuMemory=-1)],
        [SimpleNamespace(pid=7, usedGpuMemory=True)],
        [SimpleNamespace(pid=7, usedGpuMemory=1.0)],
    ],
)
def test_large_or_unknown_foreign_allocations_still_fail_closed(rows):
    """Over-limit totals and unknown sizes keep the original fail-closed behaviour."""
    with pytest.raises(VoiceError):
        monitor_with(rows).require_owned_compute({1})


@pytest.mark.asyncio
async def test_borrowed_core_checks_only_get_and_waits_for_actual_idle(monkeypatch):
    """Verify alias/context and busy-to-idle retirement with no generation, start, stop or reset request."""
    from src.infrastructure.voice import core

    paths = []
    slots = [True, False, False, False, False]

    def backend(request):
        """Serve bounded authored metadata and two consecutive idle observations without any model."""
        paths.append((request.method, request.url.path))
        if request.url.path == "/v1/models":
            return httpx.Response(200, json={"data": [{"id": "qwen3.5-9b-core"}]})
        if request.url.path == "/props":
            return httpx.Response(
                200, json={"default_generation_settings": {"n_ctx": 32768}}
            )
        assert request.url.path == "/slots"
        return httpx.Response(200, json=[{"is_processing": slots.pop(0)}])

    settings = {
        "URL": "http://127.0.0.1:18080",
        "identity": {"pid": 123, "executable": "neutral"},
        "executable_sha256": "a" * 64,
        "model_sha256": PINS["CORE_GGUF"],
    }
    borrowed = BorrowedCore(settings, transport=httpx.MockTransport(backend))
    monkeypatch.setattr(borrowed, "check", lambda: None)
    monkeypatch.setattr(core, "file_sha", lambda path: "a" * 64)
    await borrowed.verify()
    assert all(method == "GET" for method, path in paths)
    assert sum(path == "/slots" for method, path in paths) == 3
