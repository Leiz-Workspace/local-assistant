"""Run bounded ADR-154 inference requests inside a credential-free offline CPU namespace."""

import contextlib
import hashlib
import json
import logging
import os
import re
import struct
import sys
import time
from pathlib import Path

LOGGER = logging.getLogger(__name__)
CANDIDATES = {"turbo", "piper-vi", "qwen3-asr-0.6b", "whisper-small-ct2"}
VOICES = {"Trúc Ly", "Ngọc Huyền"}


def emit(event, **fields):
    """Write one bounded JSON protocol event without interleaving SDK console output."""
    print(
        json.dumps(dict(event=event, **fields), ensure_ascii=False, allow_nan=False),
        flush=True,
    )


def validate_message(message):
    """Reject arbitrary operations, file paths, voices and unbounded synthesis requests."""
    if not isinstance(message, dict) or message.get("op") not in {
        "synthesize",
        "transcribe",
        "close",
    }:
        raise ValueError("worker_operation")
    if message["op"] == "close":
        if set(message) != {"op"}:
            raise ValueError("worker_close_fields")
        return
    if not isinstance(message.get("id"), str) or not re.fullmatch(
        r"[a-z0-9_-]{1,100}", message["id"]
    ):
        raise ValueError("worker_identity")
    if message["op"] == "synthesize":
        if set(message) != {"op", "id", "text", "voice"}:
            raise ValueError("worker_tts_fields")
        text = message["text"]
        if (
            not isinstance(text, str)
            or not text.strip()
            or len(text.encode()) > 4096
            or any(ord(c) < 32 for c in text)
        ):
            raise ValueError("worker_text")
        if message["voice"] not in VOICES | {"piper-vi"}:
            raise ValueError("worker_voice")
    else:
        if set(message) != {"op", "id", "filename", "sample_count", "waveform_sha256"}:
            raise ValueError("worker_asr_fields")
        if not re.fullmatch(r"[a-z0-9_-]+\.f32", message["filename"]):
            raise ValueError("worker_input_path")
        if (
            type(message["sample_count"]) is not int
            or not 1 <= message["sample_count"] <= 320000
        ):
            raise ValueError("worker_samples")
        if not re.fullmatch(r"[a-f0-9]{64}", message["waveform_sha256"]):
            raise ValueError("worker_input_hash")
    LOGGER.info(
        "worker_request_validated operation=%s id=%s", message["op"], message["id"]
    )


def native_bytes(values, rate):
    """Validate an unaltered float32 mono native waveform and encode a lossless IEEE-float WAV."""
    import numpy as np

    if (
        not isinstance(values, np.ndarray)
        or values.dtype != np.dtype("float32")
        or values.ndim != 1
    ):
        raise ValueError("native_dtype_shape")
    if (
        rate not in {22050, 48000}
        or not 1 <= len(values) <= rate * 20
        or not np.isfinite(values).all()
    ):
        raise ValueError("native_rate_length_finite")
    raw = values.astype("<f4", copy=False).tobytes()
    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF",
        36 + len(raw),
        b"WAVE",
        b"fmt ",
        16,
        3,
        1,
        rate,
        rate * 4,
        4,
        32,
        b"data",
        len(raw),
    )
    return raw, header + raw


class FrameObserver:
    """Observe original Turbo EOS flags and decoded chunks without changing generated objects or arguments."""

    def __init__(self, engine):
        """Wrap transparent native frame/decode calls to distinguish EOS from frame-budget exhaustion."""
        self.frame, self.decode = engine._acoustic_frame, engine._decode_codes
        self.flags, self.groups = [], []
        engine._acoustic_frame, engine._decode_codes = (
            self.record_frame,
            self.record_decode,
        )

    def reset(self):
        """Reset only the audit record before a new first-attempt synthesis."""
        self.flags.clear()
        self.groups.clear()

    def record_frame(self, *args, **kwargs):
        """Return the exact original frame result while retaining its EOS boolean."""
        result = self.frame(*args, **kwargs)
        self.flags.append(bool(result[1]))
        return result

    def record_decode(self, *args, **kwargs):
        """Retain each original generation termination before returning the exact decoded waveform."""
        self.groups.append(
            dict(frames=len(self.flags), eos=bool(self.flags and self.flags[-1]))
        )
        self.flags.clear()
        return self.decode(*args, **kwargs)


class Runtime:
    """Load one explicitly selected original CPU runtime with no model discovery or fallback."""

    def __init__(self, candidate):
        """Import and load the pinned backend, then expose concrete execution settings for parent verification."""
        self.candidate = candidate
        started = time.perf_counter()
        if candidate == "turbo":
            import numpy as np
            import onnxruntime as ort
            from vieneu.v3turbo import V3TurboVieNeuTTS

            self.numpy = np
            self.import_seconds = time.perf_counter() - started
            started = time.perf_counter()
            self.engine = V3TurboVieNeuTTS(
                backbone_repo="/model",
                onnx_dir="/model/onnx_update",
                device="cpu",
                backend="onnx",
                precision="fp32",
                threads=2,
                babble_retries=0,
            )
            if (
                not VOICES <= self.engine._preset_voices.keys()
                or self.engine.backend != "onnx"
                or self.engine.engine.babble_retries != 0
            ):
                raise ValueError("turbo_voice_backend_binding")
            if self.engine.engine.denoiser is None:
                raise ValueError("turbo_approved_denoiser_not_loaded")
            sessions = []
            for name in [
                "sess_pre",
                "sess_dec",
                "sess_ac",
                "sess_codec_dec",
                "sess_codec_step",
            ]:
                session = getattr(self.engine.engine, name)
                options = session.get_session_options()
                if (
                    session.get_providers() != ["CPUExecutionProvider"]
                    or options.intra_op_num_threads != 2
                    or options.inter_op_num_threads != 1
                ):
                    raise ValueError("turbo_session_cpu_threads")
                sessions.append(
                    dict(
                        name=name,
                        providers=session.get_providers(),
                        intra_threads=options.intra_op_num_threads,
                        inter_threads=options.inter_op_num_threads,
                    )
                )
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
            self.observer = FrameObserver(self.engine.engine)
        elif candidate == "piper-vi":
            from scripts.tts_evaluation_worker import Runtime as OriginalRuntime

            self.engine = OriginalRuntime(candidate, True)
            self.import_seconds, self.load_seconds = (
                self.engine.import_seconds,
                self.engine.load_seconds,
            )
            self.execution = self.engine.execution
        else:
            from scripts.asr_evaluation_worker import Runtime as OriginalRuntime

            self.engine = OriginalRuntime(candidate, True)
            self.import_seconds, self.load_seconds = (
                self.engine.import_seconds,
                self.engine.load_seconds,
            )
            self.execution = self.engine.execution
        LOGGER.info("research_runtime_ready candidate=%s", candidate)

    def predict(self, message):
        """Run one uncached first request and retain complete native audio or unedited ASR output."""
        if message["op"] == "transcribe":
            if self.candidate not in {"qwen3-asr-0.6b", "whisper-small-ct2"}:
                raise ValueError("worker_candidate_operation")
            from scripts.asr_evaluation_worker import load_waveform

            waveform = load_waveform(message)
            result = self.engine.transcribe(waveform, "vi_vn")
            return dict(asr=result)
        if self.candidate == "turbo":
            if message["voice"] not in VOICES:
                raise ValueError("worker_voice_binding")
            self.numpy.random.seed(7)
            self.observer.reset()
            started = time.perf_counter()
            values = self.engine.infer(message["text"], voice=message["voice"])
            seconds, rate = time.perf_counter() - started, self.engine.sample_rate
            metadata = dict(
                full_call_seconds=seconds,
                chunks=list(self.observer.groups),
                generation_complete=bool(self.observer.groups)
                and all(x["eos"] for x in self.observer.groups),
                audio_availability="complete_synchronous_waveform",
            )
        elif self.candidate == "piper-vi" and message["voice"] == "piper-vi":
            values, rate, metadata = self.engine.synthesize(
                dict(
                    id=message["id"],
                    text=message["text"],
                    language="vi",
                    variant="explicit",
                )
            )
        else:
            raise ValueError("worker_voice_binding")
        raw, wav = native_bytes(values, rate)
        for suffix, content in [("f32", raw), ("wav", wav)]:
            descriptor = os.open(
                Path("/output") / (message["id"] + "." + suffix),
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                0o600,
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


def main():
    """Serve bounded nonqueued messages until explicit shutdown or the first failure, without retries."""
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    os.umask(0o077)
    candidate = sys.argv[1]
    if candidate not in CANDIDATES:
        raise ValueError("worker_candidate")
    with contextlib.redirect_stdout(sys.stderr):
        runtime = Runtime(candidate)
    emit(
        "ready",
        candidate=candidate,
        import_seconds=runtime.import_seconds,
        load_seconds=runtime.load_seconds,
        execution=runtime.execution,
    )
    seen = set()
    for _ in range(75):
        raw = sys.stdin.buffer.readline(16385)
        if not raw or len(raw) > 16384 or not raw.endswith(b"\n"):
            raise ValueError("worker_message_bound_or_eof")
        message = json.loads(raw)
        validate_message(message)
        if message["op"] == "close":
            emit("closed", calls=len(seen))
            return
        if message["id"] in seen:
            raise ValueError("worker_duplicate_call")
        seen.add(message["id"])
        started = time.perf_counter()
        with contextlib.redirect_stdout(sys.stderr):
            result = runtime.predict(message)
        emit(
            "result",
            id=message["id"],
            operation=message["op"],
            worker_wall_seconds=time.perf_counter() - started,
            **result,
        )
    raise ValueError("worker_call_ceiling")


if __name__ == "__main__":
    main()
