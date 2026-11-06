"""Serve accepted Turbo reading with the unchanged CPU8 numerical path and no evaluation corpus."""

import contextlib
import functools
import hashlib
import json
import logging
import os
import sys
import time
from pathlib import Path
from src.infrastructure.voice.waveform import (
    FrameObserver,
    native_bytes,
    emit,
    validate_message,
    VOICES,
)
from src.infrastructure.voice.prosody import ProsodyAdapter
from src.infrastructure.voice.reading_policy import (
    WorkflowReadingAdapter,
    MODEL,
    POLICY,
    VOICE,
    check_text,
)

LOGGER = logging.getLogger(__name__)
PROFILES = {"raw": 256, "reading": 256, "clauses": 256}


class Runtime:
    """Serve only the retained Turbo CPU8 native inference path."""

    def __init__(self, candidate, threads=8):
        """Load the unchanged original Turbo CPU8 FP32 engine and verify all concrete sessions."""
        if candidate != "turbo" or threads != 8:
            raise ValueError("voice_fixed_tts_profile")
        started = time.perf_counter()
        import numpy as np
        import onnxruntime as ort
        from vieneu.v3turbo import V3TurboVieNeuTTS

        self.candidate, self.numpy = (candidate, np)
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
            or (not VOICES <= self.engine._preset_voices.keys())
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
        self.execution = dict(
            self.execution,
            cpu_threads=threads,
            logical_CPU_affinity=sorted(os.sched_getaffinity(0)),
        )
        LOGGER.info("resident_runtime_ready role=%s threads=%d", candidate, threads)

    def predict(self, message):
        """Generate once with the original random seed, frame observer, float/WAV encoding and EOS metadata."""
        if message["voice"] not in VOICES:
            raise ValueError("worker_voice_binding")
        self.numpy.random.seed(7)
        self.observer.reset()
        started = time.perf_counter()
        values = self.engine.infer(message["text"], voice=message["voice"])
        seconds, rate = (time.perf_counter() - started, self.engine.sample_rate)
        metadata = dict(
            full_call_seconds=seconds,
            chunks=list(self.observer.groups),
            generation_complete=bool(self.observer.groups)
            and all((x["eos"] for x in self.observer.groups)),
            audio_availability="complete_synchronous_waveform",
        )
        raw, wav = native_bytes(values, rate)
        for suffix, content in [("f32", raw), ("wav", wav)]:
            descriptor = os.open(
                Path("/output") / (message["id"] + "." + suffix),
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                384,
            )
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(content)
        LOGGER.info(
            "native_output_retained id=%s samples=%d", message["id"], len(values)
        )
        return dict(
            native_sha256=hashlib.sha256(raw).hexdigest(),
            wav_sha256=hashlib.sha256(wav).hexdigest(),
            sample_rate=rate,
            channels=1,
            samples=len(values),
            dtype="float32",
            **metadata,
        )


def configure_runtime(profile, factory=Runtime, adapter_factory=ProsodyAdapter):
    """Bind existing weights to the original path or the explicit question-preserving phoneme adapter."""
    if profile not in PROFILES:
        raise ValueError("quality_profile")
    runtime = factory("turbo")
    runtime.prosody_adapter = None
    if profile == "clauses":
        runtime.prosody_adapter = adapter_factory(runtime.engine)
        runtime.engine.infer = runtime.prosody_adapter.infer
    else:
        runtime.engine.infer = functools.partial(
            runtime.engine.infer, max_chars=PROFILES[profile]
        )
    runtime.execution = dict(
        runtime.execution,
        research_profile=profile,
        max_chars=PROFILES[profile],
        product_response_unchanged=True,
        original_text_normalization=profile != "clauses",
        sampling_unchanged=True,
        speed_or_style_override=False,
        question_preserving_phoneme_api=profile == "clauses",
        chunk_policy="one_sentence_no_word_split"
        if profile == "clauses"
        else "original_packing",
    )
    LOGGER.info(
        "quality_runtime_configured profile=%s max_chars=%d", profile, PROFILES[profile]
    )
    return runtime


def manifest(value):
    """Refuse an unapproved scope, altered policy/model/preset or unbounded request count before loading weights."""
    if (
        type(value) is not dict
        or value.get("native_authorized") is not True
        or value.get("policy") != POLICY
        or (value.get("model") != MODEL)
        or (value.get("voice") != VOICE)
        or (type(value.get("max_requests")) is not int)
        or (not 1 <= value["max_requests"] <= 24)
        or (type(value.get("scope_sha256")) is not str)
        or (len(value["scope_sha256"]) != 64)
        or any((char not in "0123456789abcdef" for char in value["scope_sha256"]))
    ):
        raise ValueError("workflow_reading_native_not_authorized")
    LOGGER.info(
        "workflow_reading_manifest_verified max_requests=%d", value["max_requests"]
    )
    return value


def serve(expected_sha):
    """Load only after an exact approved manifest and serve bounded fixed-preset first attempts without retry."""
    raw = Path("/approved-workflow.json").read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected_sha:
        raise ValueError("workflow_reading_manifest_sha")
    scope = manifest(json.loads(raw))
    with contextlib.redirect_stdout(sys.stderr):
        runtime = configure_runtime("clauses", adapter_factory=WorkflowReadingAdapter)
    emit(
        "ready",
        candidate="turbo",
        profile="workflow-reading",
        reading_policy=POLICY,
        voice=VOICE,
        manifest_sha256=expected_sha,
        execution=runtime.execution,
    )
    seen = set()
    for _ in range(scope["max_requests"] + 1):
        raw = sys.stdin.buffer.readline(16385)
        if not raw or len(raw) > 16384 or (not raw.endswith(b"\n")):
            raise ValueError("workflow_reading_message_bound")
        message = json.loads(raw)
        validate_message(message)
        if message["op"] == "close":
            emit("closed", calls=len(seen))
            return
        if (
            message["op"] != "synthesize"
            or message.get("voice") != VOICE
            or message["id"] in seen
            or (len(seen) >= scope["max_requests"])
        ):
            raise ValueError("workflow_reading_request_scope")
        check_text(message["text"], 4096)
        seen.add(message["id"])
        started = time.perf_counter()
        with contextlib.redirect_stdout(sys.stderr):
            result = runtime.predict(message)
            result["prosody_trace"] = runtime.prosody_adapter.last_trace
            for index, chunk in enumerate(runtime.prosody_adapter.last_chunks):
                for suffix, content in zip(
                    ("f32", "wav"), native_bytes(chunk, 48000), strict=True
                ):
                    with (
                        Path("/output") / f"{message['id']}-chunk-{index}.{suffix}"
                    ).open("xb") as stream:
                        stream.write(content)
        emit(
            "result",
            id=message["id"],
            operation="synthesize",
            worker_wall_seconds=time.perf_counter() - started,
            **result,
        )
    raise ValueError("workflow_reading_request_ceiling")
