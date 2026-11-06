"""Compose the exact retained voice lane using explicit artifacts and externally owned attested CORE."""

import asyncio
import base64
import logging
import os
import tempfile
import time
from pathlib import Path
import numpy as np
import httpx
from apps.api.services.llama_gateway import LlamaGateway
from src.application.ports.inference import CompletionResult
from src.application.ports.voice import VoiceSpeech, VoiceTranscript
from src.application.services.voice_pipeline import VoiceError, digest
from src.application.services.web_fetch_tasks import finish_owned, spawn_owned
from src.infrastructure.audio_normalizer import NativeAudioNormalizer
from src.infrastructure.voice.audio import decode_wave, encode_wave
from src.infrastructure.voice.core import BorrowedCore
from src.infrastructure.voice.detector import ViewDetector
from src.infrastructure.voice.detector_types import ViewObservation
from src.infrastructure.voice.presence import WholeClipASR
from src.infrastructure.voice.reading_bridge import compose_workflow, verify_native
from src.infrastructure.voice.reading_policy import MODEL, POLICY, VOICE
from src.infrastructure.voice.resources import (
    joined_io,
    mem_available,
    process_tree,
    rss_bytes,
)
from src.infrastructure.voice import resources as original
from src.infrastructure.voice.ipc import IPCWorker, Monitor

LOGGER = logging.getLogger(__name__)
RAM_LIMIT = 64 * 1024**2


class BorrowedGateway(LlamaGateway):
    """Retain original CORE decoding while bounding borrowed-request retirement to sixty seconds."""

    @staticmethod
    def _timeout():
        """Bound one complete response without changing the model or request's numeric decoding settings."""
        return httpx.Timeout(connect=5, read=60, write=5, pool=5)


class Ports:
    """Bind each ephemeral turn to qualified native stages while preserving original source/text/voice contracts."""

    model_id = MODEL
    reading_profile = POLICY

    def __init__(self, runtime, audio, identity):
        """Associate one original recording with single-use detector/ASR/TTS capabilities."""
        self.runtime, self.audio, self.identity = (runtime, audio, identity)
        self.used = set()
        self.gateway = BorrowedGateway(
            base_url=runtime.settings.value["core"]["URL"], model_id="qwen3.5-9b-core"
        )

    def admit(self, stage):
        """Consume one operation capability before dispatch with no retry refund."""
        if stage in self.used:
            raise VoiceError("invalid_result")
        self.used.add(stage)
        self.runtime.counts[stage] += 1
        LOGGER.info(
            "main_voice_stage_admitted stage=%s count=%d",
            stage,
            self.runtime.counts[stage],
        )

    async def observe(self, view):
        """Send only the detector copy while retaining its exact whole-source hash and sample count."""
        self.admit("vad")
        (self.runtime.root / "views/source.f32").write_bytes(view.waveform_f32)
        (self.runtime.root / "views/source.f32").chmod(0o600)
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
            tuple(((x["start"], x["end"]) for x in data["segments"])),
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
        (self.runtime.root / "inputs/source.f32").chmod(0o600)
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
        value = await self.runtime.core_complete(self.gateway, kwargs["messages"])
        first, meta = (value["choices"][0], value["local_assistant"])
        if (
            first["finish_reason"] != "stop"
            or meta.get("status") != "PASS"
            or (meta.get("preset_selected") or meta.get("preset")) != "fast"
            or (meta.get("context_size") != 32768)
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
    """Own VAD/ASR/TTS workers while borrowing, attesting and draining the existing CORE backend."""

    def __init__(self, settings, owner, admission, lease):
        """Bind explicit approved settings and stable principal without model allocation or backend calls."""
        self.settings, self.owner, self.admission, self.lease = (
            settings,
            owner,
            admission,
            lease,
        )
        self.root = self.temp = self.monitor = None
        self.core = BorrowedCore(settings.value["core"])
        self.workers = []
        self.counts = dict(vad=0, asr=0, core=0, tts=0)
        self.binding = settings.value["reading_binding"]
        self.lock = asyncio.Lock()
        self.closed = False
        self.uncertain = False
        self.core_verified = False
        self.startup_error = None
        self.expires = self.deadline = 0
        self.last_core_check = 0

    async def start(self):
        """Verify existing artifacts and borrowed CORE before loading only owned fixed native voice workers."""
        if not Path(tempfile.gettempdir()).resolve().is_relative_to(Path("/dev/shm")):
            raise ValueError("voice_requires_RAM_tempdir")
        await joined_io(self.settings.verify)
        try:
            await self.core.verify()
            self.core_verified = True
        except Exception:
            self.startup_error = "core_not_ready"
            raise
        if mem_available() < 14 * 1024**3:
            raise VoiceError("dependency_failed")
        self.temp = tempfile.TemporaryDirectory(prefix="main-voice-", dir="/dev/shm")
        self.root = Path(self.temp.name)
        for name in ("inputs", "views"):
            (self.root / name).mkdir(mode=0o700)
        (self.root / "passwd").write_text(
            f"asr-evaluation:x:{os.getuid()}:{os.getgid()}:voice:/tmp:/bin/false\n"
        )
        (self.root / "group").write_text(f"asr-evaluation:x:{os.getgid()}:\n")
        for name in ("passwd", "group"):
            (self.root / name).chmod(0o600)
        self.monitor = Monitor(self.settings.paths["cuda_venv"])
        self.deadline = time.monotonic() + 600
        for role in ("vad", "qwen3-asr-0.6b", "turbo"):
            worker = IPCWorker(self, role)
            self.workers.append(worker)
            await worker.start()
        self.expires = time.monotonic() + 480
        LOGGER.info("main_voice_group_ready lifetime_seconds=480")

    def check_resources(self):
        """Enforce original worker/CORE caps plus separate main-process accounting while idle and active."""
        now = time.monotonic()
        if now >= self.deadline:
            raise VoiceError("timeout")
        if now - self.last_core_check > 1:
            self.core.check()
            self.last_core_check = now
        aggregate = sum(rss_bytes(p) for p in process_tree(self.core.pid))
        allowed = set(process_tree(self.core.pid))
        if rss_bytes(os.getpid()) > 1024**3:
            raise VoiceError("dependency_failed")
        for worker in self.workers:
            if worker.process is None or worker.process.returncode is not None:
                continue
            pids = process_tree(worker.process.pid)
            allowed.update(pids)
            own = sum(rss_bytes(p) for p in pids)
            worker.peak_rss = max(worker.peak_rss, own)
            aggregate += own
            if worker.role == "turbo" and own > 2 * 1024**3:
                raise VoiceError("dependency_failed")
            if worker.role == "qwen3-asr-0.6b":
                used, free = self.monitor.sample(pids)
                worker.peak_vram = max(worker.peak_vram, used)
                if used > int(4.5 * 1024**3) or free < int(1.25 * 1024**3):
                    raise VoiceError("dependency_failed")
            if (
                worker.log
                and not worker.log.closed
                and os.fstat(worker.log.fileno()).st_size > 8 * 1024**2
            ):
                raise VoiceError("dependency_failed")
        if aggregate > 8 * 1024**3:
            raise VoiceError("dependency_failed")
        if self.monitor:
            self.monitor.require_owned_compute(allowed)
        if (
            self.root
            and sum(p.stat().st_size for p in self.root.rglob("*") if p.is_file())
            > RAM_LIMIT
        ):
            raise VoiceError("dependency_failed")

    def health(self):
        """Reject expired or exited model groups without silently reloading or replacing them."""
        if self.closed or time.monotonic() >= self.expires:
            raise VoiceError("closed")
        if any(
            w.process is None or w.process.returncode is not None for w in self.workers
        ):
            raise VoiceError("dependency_failed")
        self.check_resources()

    async def core_complete(self, gateway, messages):
        """Retain exclusive admission until a borrowed CORE request actually completes, including cancellation."""
        self.core.check()

        async def generate():
            """Authorize only this owned task to dispatch unchanged Fast512 inference under its residency lease."""
            async with self.admission.borrow(self.lease):
                return await gateway.complete(
                    messages=messages, temperature=0, max_tokens=512, preset="fast"
                )

        task = spawn_owned(generate())
        try:
            result = await asyncio.shield(task)
            self.core.check()
            return result
        except asyncio.CancelledError:
            try:
                await finish_owned(task)
                await self.core.quiesce()
            except BaseException:
                self.uncertain = True
            raise
        except BaseException:
            self.uncertain = True
            raise

    async def ask(self, raw, identity):
        """Process original complete VI PCM under the authenticated principal and erase joined turn files."""
        if self.lock.locked():
            raise VoiceError("busy")
        async with self.lock:
            self.health()
            audio = decode_wave(raw)
            ports = Ports(self, audio, identity)
            gated = WholeClipASR(
                detector=ViewDetector(ports, audit_redacted),
                asr=ports,
                asr_model="qwen3-asr-0.6b",
            )
            pipeline = compose_workflow(
                gated,
                ports,
                ports,
                audit_redacted,
                asr_model="qwen3-asr-0.6b",
                timeout=60,
            )
            try:
                turn = await pipeline.complete(
                    self.owner, audio, "vi", explicit_submission=True
                )
                self.check_resources()
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
                await finish_owned(spawn_owned(pipeline.shutdown()))
                await finish_owned(spawn_owned(gated.shutdown()))
                self.erase_turn()

    def erase_turn(self):
        """Delete only this turn's original/detector/native bytes after all dependencies have joined."""
        if self.root:
            for directory in [
                self.root / "inputs",
                self.root / "views",
                *[w.directory / "native" for w in self.workers],
            ]:
                if directory.exists():
                    for path in directory.iterdir():
                        if path.is_file():
                            path.unlink()
        for worker in self.workers:
            if worker.log and not worker.log.closed:
                worker.log.seek(0)
                worker.log.truncate()
        LOGGER.info("main_voice_turn_RAM_erased")

    async def close(self):
        """Join owned workers and verify shared CORE quiescence before claiming complete retirement."""
        if self.closed:
            return
        failures = []
        for worker in reversed(self.workers):
            try:
                await worker.close(
                    force=worker.process is not None
                    and worker.process.returncode is not None
                )
            except BaseException:
                failures.append("worker_retirement")
        try:
            if self.uncertain:
                raise ValueError("borrowed_core_uncertain")
            if self.core_verified:
                await self.core.quiesce()
        except BaseException:
            failures.append("core_quiescence")
        if self.monitor:
            self.monitor.close()
            self.monitor = None
        if failures:
            self.uncertain = True
            LOGGER.error("main_voice_retirement_unverified count=%d", len(failures))
            raise VoiceError("dependency_failed")
        if self.temp:
            self.temp.cleanup()
        self.closed = True
        LOGGER.info("main_voice_group_joined calls=%s", self.counts)
