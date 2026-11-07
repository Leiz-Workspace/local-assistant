"""Own finite offline native voice workers with sampled resource guards and joined process-group cleanup."""

import asyncio
import importlib.util
import json
import logging
import os
import signal
import sys
from pathlib import Path

from src.application.services.voice_pipeline import VoiceError
from src.application.services.web_fetch_tasks import finish_owned, spawn_owned
from src.infrastructure.voice.manifest import file_sha
from src.infrastructure.voice.resources import mem_available
from src.infrastructure.voice.sandbox import command
from src.infrastructure.voice.worker import LIMIT, MODELS, POLICIES

LOGGER = logging.getLogger(__name__)
# ADR176: desktop processes (remote desktop, file manager) hold small GPU contexts on the
# Home Server. Allow them up to this total; unknown sizes count as over the limit.
FOREIGN_VRAM_LIMIT = 1024**3
NVML_UNKNOWN_FLOOR = 2**63


def foreign_compute(rows, pids):
    """Return the count and total VRAM bytes of compute processes outside the owned set."""
    count = total = 0
    for row in rows:
        if row.pid in pids:
            continue
        used = getattr(row, "usedGpuMemory", None)
        count += 1
        total += (
            FOREIGN_VRAM_LIMIT + 1
            if type(used) is not int or not 0 <= used < NVML_UNKNOWN_FLOOR
            else used
        )
    return count, total


class Monitor:
    """Read exact installed NVML process allocations without changing GPU state or spawning polling commands."""

    def __init__(self, venv):
        """Load the manifest-verified existing monitoring module only during explicit native preparation."""
        path = Path(venv) / "lib/python3.12/site-packages/pynvml.py"
        spec = importlib.util.spec_from_file_location("_main_voice_nvml", path)
        self.module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = self.module
        previous = sys.dont_write_bytecode
        sys.dont_write_bytecode = True
        try:
            spec.loader.exec_module(self.module)
        finally:
            sys.dont_write_bytecode = previous
        self.module.nvmlInit()
        self.device = self.module.nvmlDeviceGetHandleByIndex(0)
        LOGGER.info("voice_nvml_opened")

    def sample(self, pids=()):
        """Return owned process VRAM and device-free bytes without touching other processes."""
        rows = self.module.nvmlDeviceGetComputeRunningProcesses_v3(self.device)
        return sum(int(x.usedGpuMemory) for x in rows if x.pid in pids), int(
            self.module.nvmlDeviceGetMemoryInfo(self.device).free
        )

    def close(self):
        """Release only the read-only NVML client handle."""
        self.module.nvmlShutdown()
        LOGGER.info("voice_nvml_closed")

    def require_owned_compute(self, pids):
        """Tolerate small known-size foreign GPU allocations (ADR176) and fail closed otherwise, never touching them."""
        rows = self.module.nvmlDeviceGetComputeRunningProcesses_v3(self.device)
        count, total = foreign_compute(rows, pids)
        if total > FOREIGN_VRAM_LIMIT:
            raise VoiceError("dependency_failed")
        if (count, total // 1024**2) != getattr(self, "foreign_seen", (0, 0)):
            self.foreign_seen = (count, total // 1024**2)
            LOGGER.info(
                "voice_foreign_gpu_tolerated processes=%d mib=%d",
                count,
                total // 1024**2,
            )


class IPCWorker:
    """Bind one qualified worker to group resource checks and an ephemeral RAM-only event channel."""

    def __init__(self, runtime, role):
        """Declare ownership and metadata without allocating models or spawning a child process."""
        self.runtime, self.role = runtime, role
        self.directory = runtime.root / role
        self.process = self.log = self.ready = None
        self.calls = self.peak_rss = self.peak_vram = 0
        self.busy = False

    async def receive(self):
        """Read exactly one bounded protocol event while polling all live resource guards."""
        task = spawn_owned(self.process.stdout.readline())
        try:
            while not task.done():
                self.runtime.check_resources()
                await asyncio.wait({task}, timeout=0.025)
            raw = task.result()
            if not raw or len(raw) > 65536 or not raw.endswith(b"\n"):
                raise VoiceError("invalid_result")
            value = json.loads(raw)
            if type(value) is not dict:
                raise VoiceError("invalid_result")
            return value
        finally:
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    async def start(self):
        """Require original RAM/VRAM headroom and verify concrete loaded precision/policy before readiness."""
        if (
            mem_available() < 14 * 1024**3
            or self.role == "qwen3-asr-0.6b"
            and self.runtime.monitor.sample()[1] < 6 * 1024**3
        ):
            raise VoiceError("dependency_failed")
        self.directory.mkdir(mode=0o700)
        output = self.directory / "native"
        output.mkdir(mode=0o700)
        scope = self.runtime.root / (self.role + "-scope.json")
        payload = dict(
            native_authorized=True,
            role=self.role,
            max_requests=LIMIT,
            cpu_threads=2 if self.role == "vad" else 8,
            mode="voice",
            model=MODELS[self.role],
            policy=POLICIES[self.role],
            voice="Trúc Ly" if self.role == "turbo" else None,
            scope_sha256=self.runtime.settings.sha256,
            execution_backend="cuda-original-precision"
            if self.role == "qwen3-asr-0.6b"
            else "cpu",
        )
        scope.write_text(json.dumps(payload, ensure_ascii=False))
        scope.chmod(0o600)
        sha = file_sha(scope)
        samples = self.runtime.root / ("views" if self.role == "vad" else "inputs")
        args = command(self.runtime.settings, self.role, output, samples, scope, sha)
        self.log = (self.directory / "stderr.log").open("w+b")
        os.fchmod(self.log.fileno(), 0o600)
        LOGGER.info("voice_worker_load_admitted role=%s", self.role)
        self.process = await asyncio.create_subprocess_exec(
            *args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=self.log,
            start_new_session=True,
            limit=65537,
            env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"},
        )
        self.ready = await self.receive()
        if (
            self.ready.get("event"),
            self.ready.get("candidate"),
            self.ready.get("manifest_sha256"),
        ) != ("ready", self.role, sha):
            raise VoiceError("invalid_result")
        execution = self.ready["execution"]
        if self.role == "qwen3-asr-0.6b" and (
            execution.get("device"),
            execution.get("parameter_dtype"),
            execution.get("tf32"),
            self.ready.get("readiness", {}).get("model_calls"),
        ) != ("cuda:0", "torch.float32", False, 1):
            raise VoiceError("invalid_result")
        if self.role == "turbo" and (
            self.ready.get("voice") != "Trúc Ly"
            or self.ready.get("reading_policy") != POLICIES["turbo"]
            or any(x["intra_threads"] != 8 for x in execution["sessions"])
        ):
            raise VoiceError("invalid_result")
        LOGGER.info("voice_native_worker_ready role=%s", self.role)
        if self.role == "qwen3-asr-0.6b":
            LOGGER.info("voice_readiness_verified model_calls=1")

    async def call(self, message):
        """Send one uncached bounded request without retries and require matching complete result identity."""
        if self.busy or self.calls >= LIMIT or self.process.returncode is not None:
            raise VoiceError("busy")
        self.busy = True
        self.calls += 1
        LOGGER.info("voice_stage_dispatched role=%s count=%d", self.role, self.calls)
        try:
            self.process.stdin.write(
                json.dumps(message, ensure_ascii=False).encode() + b"\n"
            )
            await self.process.stdin.drain()
            result = await self.receive()
            if (result.get("event"), result.get("id"), result.get("operation")) != (
                "result",
                message["id"],
                message["op"],
            ):
                raise VoiceError("invalid_result")
            return result
        except BaseException:
            await finish_owned(spawn_owned(self.close(force=True)))
            raise
        finally:
            self.busy = False

    async def close(self, force=False):
        """Join only the worker's owned process group, escalating bounded termination without touching CORE."""
        process = self.process
        if process is None:
            if self.log:
                self.log.close()
            return
        if not force and process.returncode is None:
            try:
                process.stdin.write(b'{"op":"close"}\n')
                await process.stdin.drain()
                event = await asyncio.wait_for(self.receive(), 3)
                if event.get("event") != "closed":
                    raise ValueError("worker_close_event")
                await asyncio.wait_for(process.wait(), 3)
            except BaseException:
                force = True
        if process.returncode is None:
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                await asyncio.wait_for(process.wait(), 3)
            except TimeoutError:
                os.killpg(process.pid, signal.SIGKILL)
                await asyncio.wait_for(process.wait(), 5)
        self.log.close()
        LOGGER.info(
            "voice_native_worker_joined role=%s exit=%s forced=%s",
            self.role,
            process.returncode,
            force,
        )
        if not force and process.returncode:
            raise VoiceError("dependency_failed")
