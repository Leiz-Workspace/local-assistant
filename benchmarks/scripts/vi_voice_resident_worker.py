"""Serve manifest-bound resident voice stages with fixed CPU profiles and unchanged models, decoding and reading policy."""

import contextlib
import hashlib
import json
import logging
import os
import sys
import time
from pathlib import Path

from benchmarks.scripts.vi_voice_worker import (
    Runtime,
    FrameObserver,
    VOICES,
    emit,
    validate_message,
)

LOGGER = logging.getLogger(__name__)
ROLE_MODELS = {
    "vad": "silero-vad-v5.0-5cd2ba54",
    "turbo": "vieneu-v3-turbo-truc-ly",
    "whisper-small-ct2": "whisper-small-ct2",
    "qwen3-asr-0.6b": "qwen3-asr-0.6b",
}
ROLE_POLICIES = {
    "vad": "detector-peak-half-v2",
    "turbo": "truc-ly-workflow-reading-1",
    "whisper-small-ct2": "original-asr-decoding",
    "qwen3-asr-0.6b": "original-asr-decoding",
}


def validate_scope(value):
    """Admit only the fixed resident roles, CPU profiles and finite request capabilities before loading any model."""
    if (
        type(value) is not dict
        or value.get("role")
        not in ("vad", "turbo", "whisper-small-ct2", "qwen3-asr-0.6b")
        or type(value.get("cpu_threads")) is not int
        or value["cpu_threads"] not in (2, 4, 8)
        or type(value.get("max_requests")) is not int
        or value["max_requests"] != (6 if value["role"] == "vad" else 4)
        or value.get("native_authorized") is not True
        or type(value.get("scope_sha256")) is not str
        or len(value["scope_sha256"]) != 64
        or any(x not in "0123456789abcdef" for x in value["scope_sha256"])
    ):
        raise ValueError("resident_scope")
    if value["role"] == "vad" and value["cpu_threads"] != 2:
        raise ValueError("resident_vad_threads")
    if (
        value.get("model") != ROLE_MODELS[value["role"]]
        or value.get("policy") != ROLE_POLICIES[value["role"]]
        or (value["role"] == "turbo" and value.get("voice") != "Trúc Ly")
    ):
        raise ValueError("resident_scope_model_policy")
    LOGGER.info(
        "resident_scope_verified role=%s threads=%d",
        value["role"],
        value["cpu_threads"],
    )
    return value


class ProfileRuntime(Runtime):
    """Reuse original inference methods while changing only explicit CPU allocation for the fixed trial."""

    def __init__(self, candidate, threads):
        """Load the same model/backend/precision and validate concrete CPU session or decoder settings."""
        if threads not in (2, 4, 8):
            raise ValueError("resident_runtime_threads")
        if threads == 2:
            super().__init__(candidate)
        elif candidate == "turbo":
            started = time.perf_counter()
            import numpy as np
            import onnxruntime as ort
            from vieneu.v3turbo import V3TurboVieNeuTTS

            self.candidate, self.numpy = candidate, np
            self.import_seconds = time.perf_counter() - started
            started = time.perf_counter()
            self.engine = V3TurboVieNeuTTS(
                backbone_repo="/model",
                onnx_dir="/model/onnx_update",
                device="cpu",
                backend="onnx",
                precision="fp32",
                threads=threads,
                babble_retries=0,
            )
            if (
                self.engine.backend != "onnx"
                or self.engine.engine.babble_retries != 0
                or self.engine.engine.denoiser is None
                or not VOICES <= self.engine._preset_voices.keys()
            ):
                raise ValueError("resident_tts_backend")
            sessions = []
            for name in (
                "sess_pre",
                "sess_dec",
                "sess_ac",
                "sess_codec_dec",
                "sess_codec_step",
            ):
                session = getattr(self.engine.engine, name)
                options = session.get_session_options()
                if (
                    session.get_providers() != ["CPUExecutionProvider"]
                    or options.intra_op_num_threads != threads
                    or options.inter_op_num_threads != 1
                ):
                    raise ValueError("resident_tts_session_threads")
                sessions.append(
                    dict(
                        name=name,
                        providers=session.get_providers(),
                        intra_threads=threads,
                        inter_threads=1,
                    )
                )
            self.observer = FrameObserver(self.engine.engine)
            self.load_seconds = time.perf_counter() - started
            self.execution = dict(
                device="cpu",
                backend="onnx",
                precision="fp32",
                sample_rate=48000,
                sessions=sessions,
                babble_retries=0,
                watermark=self.engine.watermarker is not None,
                onnxruntime_version=ort.__version__,
                voices=sorted(VOICES),
                original_text_normalization=True,
                original_frame_cap=True,
            )
        elif candidate == "qwen3-asr-0.6b":
            super().__init__(candidate)
            self.engine.torch.set_num_threads(threads)
            if self.engine.torch.get_num_threads() != threads:
                raise ValueError("resident_qwen_threads")
        elif candidate == "whisper-small-ct2":
            started = time.perf_counter()
            import ctranslate2
            from faster_whisper import WhisperModel, __version__
            from scripts.asr_evaluation_worker import Runtime as ASRRuntime

            self.candidate = candidate
            self.import_seconds = time.perf_counter() - started
            started = time.perf_counter()
            self.engine = ASRRuntime.__new__(ASRRuntime)
            self.engine.candidate = candidate
            self.engine.model = WhisperModel(
                "/model",
                device="cpu",
                compute_type="int8",
                cpu_threads=threads,
                num_workers=1,
                local_files_only=True,
            )
            self.load_seconds = time.perf_counter() - started
            self.execution = dict(
                device=str(self.engine.model.model.device),
                requested_compute_type="int8",
                engine_compute_type=str(self.engine.model.model.compute_type),
                faster_whisper_source=__version__,
                ctranslate2=ctranslate2.__version__,
            )
            if self.execution["device"] != "cpu":
                raise ValueError("resident_whisper_device")
        else:
            raise ValueError("resident_candidate")
        self.execution = dict(
            self.execution,
            cpu_threads=threads,
            logical_CPU_affinity=sorted(os.sched_getaffinity(0)),
        )
        LOGGER.info("resident_runtime_ready role=%s threads=%d", candidate, threads)


def serve(scope, expected_sha):
    """Serve original fixed-reading TTS or reference-free ASR/VAD messages without retries or cached results."""
    role = scope["role"]
    if role == "turbo":
        from benchmarks.scripts import vi_workflow_reading_worker as worker
        from benchmarks.scripts.vi_speech_worker import configure_runtime

        def factory(profile, adapter_factory):
            """Bind the existing reading adapter to the sole declared CPU runtime factory."""
            return configure_runtime(
                profile,
                factory=lambda candidate: ProfileRuntime(
                    candidate, scope["cpu_threads"]
                ),
                adapter_factory=adapter_factory,
            )

        worker.configure_runtime = factory
        worker.serve(expected_sha)
        return
    if role == "vad":
        from scripts.vad_evaluation_worker import (
            Runtime as VADRuntime,
            load_waveform,
            validate_request,
        )

        with contextlib.redirect_stdout(sys.stderr):
            runtime = VADRuntime(load=True)
        execution = dict(
            runtime.execution,
            cpu_threads=2,
            logical_CPU_affinity=sorted(os.sched_getaffinity(0)),
        )
    else:
        with contextlib.redirect_stdout(sys.stderr):
            runtime = ProfileRuntime(role, scope["cpu_threads"])
        execution = runtime.execution
    emit(
        "ready",
        candidate=role,
        profile="resident-latency",
        manifest_sha256=expected_sha,
        execution=execution,
    )
    seen = set()
    for _ in range(scope["max_requests"] + 1):
        raw = sys.stdin.buffer.readline(16385)
        if not raw or len(raw) > 16384 or not raw.endswith(b"\n"):
            raise ValueError("resident_message_bound")
        message = json.loads(raw)
        if message == {"op": "close"}:
            emit("closed", calls=len(seen))
            return
        if message.get("id") in seen or len(seen) >= scope["max_requests"]:
            raise ValueError("resident_budget_or_duplicate")
        if role == "vad":
            if (
                set(message)
                != {"op", "id", "filename", "sample_count", "waveform_sha256"}
                or message["op"] != "detect"
            ):
                raise ValueError("resident_vad_message")
            case = {k: v for k, v in message.items() if k != "op"}
            validate_request(dict(mode="smoke", cases=[case]))
        else:
            validate_message(message)
            if message["op"] != "transcribe":
                raise ValueError("resident_asr_operation")
        seen.add(message["id"])
        started = time.perf_counter()
        with contextlib.redirect_stdout(sys.stderr):
            if role == "vad":
                waveform = load_waveform(case)
                result = dict(
                    vad=dict(
                        sample_count=case["sample_count"],
                        waveform_sha256=case["waveform_sha256"],
                        **runtime.observe(waveform),
                    )
                )
            else:
                result = runtime.predict(message)
        emit(
            "result",
            id=message["id"],
            operation=message["op"],
            worker_wall_seconds=time.perf_counter() - started,
            **result,
        )
    raise ValueError("resident_request_ceiling")


def main():
    """Verify one exact read-only capability before allocating any resident CPU model."""
    logging.basicConfig(level=logging.INFO)
    os.umask(0o077)
    if len(sys.argv) != 2:
        raise ValueError("resident_arguments")
    raw = Path("/approved-workflow.json").read_bytes()
    if hashlib.sha256(raw).hexdigest() != sys.argv[1]:
        raise ValueError("resident_manifest_sha")
    scope = validate_scope(json.loads(raw))
    if sorted(os.sched_getaffinity(0)) != list(range(scope["cpu_threads"])):
        raise ValueError("resident_cpu_affinity")
    serve(scope, sys.argv[1])


if __name__ == "__main__":
    main()
