"""Run bounded ADR-154 inference requests inside a credential-free offline CPU namespace."""

import json
import logging
import re
import struct

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
        "[a-z0-9_-]{1,100}", message["id"]
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
            or any((ord(c) < 32 for c in text))
        ):
            raise ValueError("worker_text")
        if message["voice"] not in VOICES | {"piper-vi"}:
            raise ValueError("worker_voice")
    else:
        if set(message) != {"op", "id", "filename", "sample_count", "waveform_sha256"}:
            raise ValueError("worker_asr_fields")
        if not re.fullmatch("[a-z0-9_-]+\\.f32", message["filename"]):
            raise ValueError("worker_input_path")
        if (
            type(message["sample_count"]) is not int
            or not 1 <= message["sample_count"] <= 320000
        ):
            raise ValueError("worker_samples")
        if not re.fullmatch("[a-f0-9]{64}", message["waveform_sha256"]):
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
        or (not np.isfinite(values).all())
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
    return (raw, header + raw)


class FrameObserver:
    """Observe original Turbo EOS flags and decoded chunks without changing generated objects or arguments."""

    def __init__(self, engine):
        """Wrap transparent native frame/decode calls to distinguish EOS from frame-budget exhaustion."""
        self.frame, self.decode = (engine._acoustic_frame, engine._decode_codes)
        self.flags, self.groups = ([], [])
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
