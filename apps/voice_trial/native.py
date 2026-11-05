"""Own the qualified resident research lane with RAM-only user media and bounded joined native lifetimes."""

import asyncio
import base64
import json
import logging
import tempfile
import time
from pathlib import Path
from uuid import uuid4

import numpy as np

from apps.api.services.llama_gateway import LlamaGateway
from apps.voice_trial.audio import decode_wave, encode_wave
from apps.voice_trial.worker import LIMIT
from benchmarks.scripts import vi_voice_cuda_check as cuda
from benchmarks.scripts.vi_voice_detector_peak import ViewDetector
from benchmarks.scripts.vi_voice_detector_view import ViewObservation
from benchmarks.scripts.vi_voice_presence import WholeClipASR
from benchmarks.scripts.vi_workflow_reading_bridge import (
    compose_workflow,
    verify_native,
)
from benchmarks.scripts.vi_workflow_reading_policy import MODEL, POLICY, VOICE
from scripts.voice_native_smoke import joined_io
from src.application.ports.inference import CompletionResult
from src.application.ports.voice import VoiceSpeech, VoiceTranscript
from src.application.services.voice_pipeline import VoiceError, digest
from src.application.services.web_fetch_tasks import finish_owned, spawn_owned
from src.infrastructure.audio_normalizer import NativeAudioNormalizer

LOGGER = logging.getLogger(__name__)
original = cuda.original
WORKER = "apps/voice_trial/worker.py"
RAM_LIMIT = 64 * 1024**2
AUDIT_ROOT = cuda.PROJECT / "data/backups/d74-voice-browser-trial-first"


def worker_command(role, output, scope, sha, samples):
    """Reuse exact original runtime/device caps while binding only this session's original or detector files."""
    if role == "qwen3-asr-0.6b":
        args = cuda.command(role, output, scope, sha, samples, mode="quality")
    else:
        args = cuda.resident.command(
            role, output, scope, sha, 2 if role == "vad" else 8, samples
        )
    mounts = []
    for name in (WORKER, cuda.WORKER, cuda.resident.WORKER):
        mounts += ["--ro-bind", str(cuda.PROJECT / name), "/app/" + name]
    index = args.index("--remount-ro")
    args[index:index] = mounts
    args[-2] = "/app/" + WORKER
    LOGGER.info("trial_worker_command_bound role=%s", role)
    return args


class IPCWorker(original.Worker):
    """Reuse original resource/retirement guards while keeping user protocol events out of persistent receipts."""

    def __init__(self, role, root, core_pid, monitor, deadline, source_sha):
        """Bind one owned bounded stage to the private RAM workspace and unchanged physical resource limits."""
        super().__init__(role, root / role, deadline, root=root, core_pid=core_pid)
        self.monitor = monitor
        self.calls = 0
        self.peak_vram = 0
        self.source_sha = source_sha

    def check(self):
        """Enforce original aggregate RAM and separate CUDA VRAM headroom even between requests."""
        super().check()
        if self.candidate == "qwen3-asr-0.6b":
            used, free = self.monitor.sample(original.process_tree(self.process.pid))
            self.peak_vram = max(self.peak_vram, used)
            if used > int(4.5 * 1024**3) or free < int(1.25 * 1024**3):
                raise VoiceError("dependency_failed")

    async def receive(self):
        """Materialize one bounded JSON event in memory while continuously sampling owned processes and RAM files."""
        task = spawn_owned(self.process.stdout.readline())
        last = 0
        try:
            while not task.done():
                for worker in list(original.WORKERS):
                    worker.check()
                if time.monotonic() - last > 1:
                    original.assets.budget(self.root, limit=RAM_LIMIT)
                    last = time.monotonic()
                await asyncio.wait({task}, timeout=0.025)
            raw = task.result()
            if not raw or len(raw) > 65536 or not raw.endswith(b"\n"):
                raise VoiceError("dependency_failed")
            value = json.loads(raw)
            if type(value) is not dict:
                raise VoiceError("invalid_result")
            return value
        finally:
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    async def start(self):
        """Require unchanged preload headroom and verify actual role/model/manifest/precision before serving."""
        if original.mem_available() < 14 * 1024**3:
            raise VoiceError("dependency_failed")
        if (
            self.candidate == "qwen3-asr-0.6b"
            and self.monitor.sample()[1] < 6 * 1024**3
        ):
            raise VoiceError("dependency_failed")
        self.directory.mkdir(mode=0o700)
        output = self.directory / "native"
        output.mkdir(mode=0o700)
        role = self.candidate
        scope = self.root / (role + "-scope.json")
        value = dict(
            native_authorized=True,
            role=role,
            max_requests=LIMIT,
            cpu_threads=2 if role == "vad" else 8,
            mode="voice",
            model=cuda.resident.ROLE_MODELS[role],
            policy=cuda.resident.ROLE_POLICIES[role],
            voice=VOICE if role == "turbo" else None,
            scope_sha256=self.source_sha,
            execution_backend="cuda-original-precision"
            if role == "qwen3-asr-0.6b"
            else "cpu",
        )
        original.assets.publish(
            scope,
            dict(
                description="Fixed optional browser research capability; not model/default adoption.",
                **value,
            ),
        )
        self.scope_sha = original.assets.digest(scope)
        samples = self.root / ("views" if role == "vad" else "inputs")
        args = worker_command(role, output, scope, self.scope_sha, samples)
        self.log = (self.directory / "stderr.log").open("w+b")
        self.started = time.monotonic()
        try:
            self.process = await asyncio.create_subprocess_exec(
                *args,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=self.log,
                start_new_session=True,
                limit=65537,
                env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"},
            )
            original.WORKERS.add(self)
            self.ready = await self.receive()
            if (
                self.ready.get("event"),
                self.ready.get("candidate"),
                self.ready.get("manifest_sha256"),
            ) != ("ready", role, self.scope_sha):
                raise VoiceError("invalid_result")
            execution = self.ready["execution"]
            if role == "qwen3-asr-0.6b" and (
                execution.get("device"),
                execution.get("parameter_dtype"),
                execution.get("tf32"),
                self.ready.get("readiness", {}).get("model_calls"),
            ) != ("cuda:0", "torch.float32", False, 1):
                raise VoiceError("invalid_result")
            if role == "turbo" and (
                self.ready.get("voice") != VOICE
                or self.ready.get("reading_policy") != POLICY
                or any(s["intra_threads"] != 8 for s in execution["sessions"])
            ):
                raise VoiceError("invalid_result")
        except BaseException:
            if self.process is not None:
                await finish_owned(spawn_owned(self.close(force=True)))
            else:
                self.log.close()
            raise
        LOGGER.info("trial_worker_ready role=%s", role)
        return self

    async def call(self, message):
        """Dispatch one first request without queue/retry or raw protocol persistence and join failures."""
        if self.busy or self.calls >= LIMIT or self.process.returncode is not None:
            raise VoiceError("busy")
        self.busy = True
        self.calls += 1
        LOGGER.info(
            "trial_stage_dispatched role=%s count=%d", self.candidate, self.calls
        )
        try:
            self.process.stdin.write(
                json.dumps(message, ensure_ascii=False).encode() + b"\n"
            )
            await self.process.stdin.drain()
            value = await self.receive()
            if (value.get("event"), value.get("id"), value.get("operation")) != (
                "result",
                message["id"],
                message["op"],
            ):
                raise VoiceError("invalid_result")
            return value
        except BaseException:
            self.failure = "trial_stage_failed_or_cancelled"
            await finish_owned(spawn_owned(self.close(force=True)))
            raise
        finally:
            self.busy = False


class Ports:
    """Bind each ephemeral turn to qualified native stages while preserving original source/text/voice contracts."""

    model_id = MODEL
    reading_profile = POLICY

    def __init__(self, runtime, audio, identity):
        """Associate one original recording with single-use detector/ASR/TTS capabilities."""
        self.runtime, self.audio, self.identity = runtime, audio, identity
        self.used = set()
        self.gateway = LlamaGateway(
            base_url="http://127.0.0.1:18080", model_id="qwen3.5-9b-core"
        )

    def admit(self, stage):
        """Consume one operation capability before dispatch with no retry refund."""
        if stage in self.used:
            raise VoiceError("invalid_result")
        self.used.add(stage)
        self.runtime.counts[stage] += 1

    async def observe(self, view):
        """Send only the detector copy while retaining its exact whole-source hash and sample count."""
        self.admit("vad")
        (self.runtime.root / "views/source.f32").write_bytes(view.waveform_f32)
        value = await self.runtime.workers[0].call(
            dict(
                op="detect",
                id=self.identity + "-vad",
                filename="source.f32",
                sample_count=view.sample_count,
                waveform_sha256=view.waveform_sha256,
            )
        )
        data = value["vad"]
        if (
            data.get("waveform_sha256"),
            data.get("sample_count"),
            data.get("source_samples_modified"),
            data.get("external_recording_resets"),
        ) != (view.waveform_sha256, view.sample_count, False, 1):
            raise VoiceError("invalid_result")
        return ViewObservation(
            view.waveform_sha256,
            view.sample_count,
            tuple((x["start"], x["end"]) for x in data["segments"]),
        )

    async def transcribe(self, owner, audio, language):
        """Forward identical original PCM to the same CUDA decoder without the detector view or text repair."""
        if audio is not self.audio or language != "vi":
            raise VoiceError("invalid_input")
        self.admit("asr")
        raw = (
            (
                np.frombuffer(audio.pcm_s16le, dtype="<i2").astype(np.float32)
                / np.float32(32768)
            )
            .astype("<f4")
            .tobytes()
        )
        (self.runtime.root / "inputs/source.f32").write_bytes(raw)
        result = await self.runtime.workers[1].call(
            dict(
                op="transcribe",
                id=self.identity + "-asr",
                filename="source.f32",
                sample_count=audio.sample_count,
                waveform_sha256=digest(raw),
            )
        )
        value = result["asr"]
        return VoiceTranscript(
            owner,
            audio.source_sha256,
            audio.pcm_sha256,
            language,
            value["text"],
            "qwen3-asr-0.6b",
            not value["output_cap_reached"],
        )

    async def complete(self, **kwargs):
        """Use the unchanged CORE Fast512 request and require full stop/context provenance without saving content."""
        if (
            kwargs["profile"],
            kwargs["preset"],
            kwargs["max_tokens"],
            kwargs["temperature"],
        ) != ("core", "fast", 512, 0):
            raise VoiceError("invalid_input")
        self.admit("core")
        value = await self.gateway.complete(
            messages=kwargs["messages"], temperature=0, max_tokens=512, preset="fast"
        )
        first, meta = value["choices"][0], value["local_assistant"]
        if (
            first["finish_reason"] != "stop"
            or meta.get("status") != "PASS"
            or (meta.get("preset_selected") or meta.get("preset")) != "fast"
            or meta.get("context_size") != 32768
        ):
            raise VoiceError("invalid_result")
        return CompletionResult(
            first["message"]["content"], "qwen3.5-9b-core", "fast", "stop"
        )

    async def synthesize(self, owner, answer, language):
        """Verify exact accepted voice/reading/chunk provenance before original native-to-playback conversion in RAM."""
        self.admit("tts")
        worker = self.runtime.workers[2]
        message = dict(
            op="synthesize", id=self.identity + "-tts", text=answer, voice=VOICE
        )
        result = await worker.call(message)
        verify_native(
            result, message, worker.directory / "native", self.runtime.binding
        )
        raw = original.read_native(worker.directory / "native", message["id"], result)
        normalized = await joined_io(
            lambda: NativeAudioNormalizer().normalize(
                original.pcm_wave(raw, result["sample_rate"])
            )
        )
        return VoiceSpeech(
            owner,
            digest(answer.encode()),
            language,
            MODEL,
            normalized.pcm_s16le,
            normalized.sample_count,
        )


async def audit_redacted(value):
    """Acknowledge source/reading verification without persisting user content or fingerprints."""
    LOGGER.info("trial_provenance_verified")


class NativeRuntime:
    """Own one fixed-lifetime research group and erase private RAM files after joined turns and shutdown."""

    def __init__(self):
        """Initialize admission metadata without loading models or acquiring a microphone."""
        self.temp = self.root = self.server = self.monitor = None
        self.workers = []
        self.binding = None
        self.closed = False
        self.pipeline = self.gated = None
        self.counts = dict(vad=0, asr=0, core=0, tts=0)
        self.lock = asyncio.Lock()

    def verify_lane(self):
        """Require the retained passing compute/quality and unchanged original artifacts without neural inference."""
        software = json.loads((AUDIT_ROOT / "software-verification.json").read_text())
        if software.get("status") != "PASS" or not software.get("source_sha256"):
            raise VoiceError("dependency_failed")
        cuda.old.verify_snapshot(software["source_sha256"])
        self.source_sha = original.assets.digest(
            AUDIT_ROOT / "software-verification.json"
        )
        receipt = json.loads(
            (
                cuda.PROJECT / "docs/evidence/d74-resident-cuda-latency-result.json"
            ).read_text()
        )
        if (
            receipt["status"] != "LOCAL_BUFFERED_COMPUTE_PASS"
            or receipt["quality"]["qwen3-asr-0.6b"]["exact_text_matches"] != 40
        ):
            raise VoiceError("dependency_failed")
        self.binding, _ = cuda.resident.reading.verify_previous()
        original.verify_originals()
        original.verify_models()
        original.verify_runtime_snapshot()
        cuda.resident.old.verify_provision()
        hashes = json.loads(
            (cuda.resident.previous.ROOT / "asr-checkpoint-post-run.json").read_text()
        )["sha256"]
        cuda.old.verify_snapshot(hashes)
        inventory = json.loads((cuda.ROOT / "sdk-inventory.json").read_text())
        for name, expected in inventory["files"].items():
            if original.assets.digest(cuda.SDK / name) != expected:
                raise VoiceError("dependency_failed")
        LOGGER.info("trial_retained_lane_verified models_changed=False")

    async def start(self):
        """Validate the retained lane then load only owned original CORE/VAD/ASR/TTS with existing guards."""
        if not Path(tempfile.gettempdir()).resolve().is_relative_to(Path("/dev/shm")):
            raise RuntimeError("trial_requires_RAM_tempdir")
        await joined_io(self.verify_lane)
        self.temp = tempfile.TemporaryDirectory(prefix="voice-trial-", dir="/dev/shm")
        self.root = Path(self.temp.name)
        for name in ("inputs", "views", "core"):
            (self.root / name).mkdir(mode=0o700)
        self.monitor = cuda.Monitor()
        self.server = original.OwnedServer("core", self.root / "core")
        self.deadline = time.monotonic() + 600
        try:
            await self.server.start()
            for role in ("vad", "qwen3-asr-0.6b", "turbo"):
                worker = IPCWorker(
                    role,
                    self.root,
                    self.server.process.pid,
                    self.monitor,
                    self.deadline,
                    self.source_sha,
                )
                self.workers.append(worker)
                await worker.start()
            self.expires = time.monotonic() + 480
        except BaseException:
            await finish_owned(spawn_owned(self.close()))
            raise
        LOGGER.info("trial_native_group_ready seconds=480")

    def health(self):
        """Refuse expired or faulted owned groups and sample original worker guards while idle too."""
        if (
            self.closed
            or time.monotonic() >= self.expires
            or self.server.failure
            or self.server.reap() is not None
        ):
            raise VoiceError("closed")
        for worker in self.workers:
            if worker.process.returncode is not None or worker.failure:
                raise VoiceError("dependency_failed")
            worker.check()
        original.assets.budget(self.root, limit=RAM_LIMIT)

    async def ask(self, raw, identity):
        """Run one explicit VI turn and return complete audio solely in memory, deleting request files afterward."""
        if self.lock.locked():
            raise VoiceError("busy")
        async with self.lock:
            self.health()
            audio = decode_wave(raw)
            ports = Ports(self, audio, identity)
            self.gated = WholeClipASR(
                detector=ViewDetector(ports, audit_redacted),
                asr=ports,
                asr_model="qwen3-asr-0.6b",
            )
            self.pipeline = compose_workflow(
                self.gated,
                ports,
                ports,
                audit_redacted,
                asr_model="qwen3-asr-0.6b",
                timeout=60,
            )
            try:
                turn = await self.pipeline.complete(
                    uuid4(), audio, "vi", explicit_submission=True
                )
                return dict(
                    transcript=turn.transcript.text,
                    answer=turn.answer,
                    audio_base64=base64.b64encode(
                        encode_wave(turn.speech.pcm_s16le)
                    ).decode(),
                    buffered_seconds=turn.buffered_latency_seconds,
                    stages=dict(turn.stage_seconds),
                )
            finally:
                await finish_owned(spawn_owned(self.pipeline.shutdown()))
                await finish_owned(spawn_owned(self.gated.shutdown()))
                self.pipeline = self.gated = None
                self.erase_turn()

    def erase_turn(self):
        """Erase original/detector/native user bytes and transient worker diagnostics only after owned work retires."""
        for folder in [
            self.root / "inputs",
            self.root / "views",
            *[w.directory / "native" for w in self.workers],
        ]:
            for path in folder.iterdir():
                if path.is_file():
                    path.unlink()
        for worker in self.workers:
            if worker.log and not worker.log.closed:
                worker.log.seek(0)
                worker.log.truncate()
        if self.server.log and not self.server.log.closed:
            self.server.log.seek(0)
            self.server.log.truncate()
        LOGGER.info("trial_turn_RAM_media_erased")

    async def close(self):
        """Join exactly owned native resources and erase the entire RAM workspace without touching shared services."""
        if self.closed:
            return
        self.closed = True
        failures = []
        for worker in reversed(self.workers):
            try:
                await worker.close(force=bool(worker.failure))
            except BaseException:
                failures.append("worker_retirement")
        if self.server:
            try:
                await self.server.stop()
            except BaseException:
                failures.append("core_retirement")
        if self.monitor:
            self.monitor.close()
        if self.root:
            directory = AUDIT_ROOT / "lifetimes"
            directory.mkdir(mode=0o700, exist_ok=True)
            original.assets.publish(
                directory / (self.root.name + ".json"),
                dict(
                    description="Content-redacted owned research lifetime; no recording, transcript, answer or private fingerprints.",
                    failures=failures,
                    calls=self.counts,
                    workers=[
                        dict(
                            role=w.candidate,
                            pid=w.process.pid if w.process else None,
                            returncode=w.process.returncode if w.process else None,
                            peak_RSS_RAM_bytes=w.peak_rss,
                            peak_ASR_VRAM_bytes=w.peak_vram,
                        )
                        for w in self.workers
                    ],
                    core=self.server.receipt() if self.server else None,
                ),
            )
        if not failures and self.temp:
            self.temp.cleanup()
        LOGGER.info(
            "trial_native_group_retired failures=%d counts=%s",
            len(failures),
            self.counts,
        )
        if failures:
            raise VoiceError("dependency_failed")
