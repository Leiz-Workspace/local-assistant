"""Seal complete native TTS float32/WAV outputs and describe separate ASR/listening transformations without repairing original model audio."""

import hashlib
import logging
import math
import os
import re
import struct
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)


def validate_samples(values, rate):
    """Accept only bounded native mono float32 arrays and known output rates, retaining nonfinite signals for explicit failure evidence."""
    if (
        type(rate) is not int
        or rate not in {16000, 22050, 24000}
        or not isinstance(values, np.ndarray)
        or values.dtype != np.dtype("float32")
        or values.ndim != 1
        or not 1 <= len(values) <= rate * 20
    ):
        raise ValueError("tts_waveform_shape_rate_length")


def describe(values, rate):
    """Measure original samples exactly and label invalid signals without clipping, removing silence or concealing nonfinite values."""
    validate_samples(values, rate)
    raw = np.ascontiguousarray(values, dtype="<f4").tobytes()
    finite = bool(np.isfinite(values).all())
    peak = float(np.max(np.abs(values))) if finite else None
    active = (
        np.flatnonzero(np.abs(values) > 0.0001) if finite else np.array([], dtype=int)
    )
    result = dict(
        sample_rate=rate,
        channels=1,
        sample_count=len(values),
        duration_seconds=len(values) / rate,
        dtype="float32_le",
        waveform_sha256=hashlib.sha256(raw).hexdigest(),
        finite=finite,
        absolute_peak=peak,
        RMS=float(np.sqrt(np.mean(values.astype(np.float64) ** 2))) if finite else None,
        full_scale_or_above_samples=int(np.count_nonzero(np.abs(values) >= 1))
        if finite
        else None,
        leading_low_amplitude_samples=int(active[0]) if len(active) else len(values),
        trailing_low_amplitude_samples=int(len(values) - 1 - active[-1])
        if len(active)
        else len(values),
        low_amplitude_threshold=0.0001,
        signal_valid=finite and peak <= 16,
        native_sample_transform=False,
    )
    logger.info(
        "tts_native_waveform_described samples=%d rate=%d signal_valid=%s",
        len(values),
        rate,
        result["signal_valid"],
    )
    return result


def wave_bytes(values, rate):
    """Encode exact little-endian IEEEfloat32 sample bits into a complete RIFF/WAVE without a codec, quantization or metadata."""
    validate_samples(values, rate)
    raw = np.ascontiguousarray(values, dtype="<f4").tobytes()
    fmt = struct.pack("<HHIIHH", 3, 1, rate, rate * 4, 4, 32)
    body = (
        b"WAVEfmt "
        + struct.pack("<I", 16)
        + fmt
        + b"fact"
        + struct.pack("<II", 4, len(values))
        + b"data"
        + struct.pack("<I", len(raw))
        + raw
    )
    return b"RIFF" + struct.pack("<I", len(body)) + body


def write_exclusive(path, raw):
    """Publish only a bounded owned result file with no symlink adoption, overwrite or permissive mode."""
    if type(raw) is not bytes or len(raw) > 16 * 1024**2:
        raise ValueError("tts_output_file_bound")
    descriptor = os.open(
        path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600
    )
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    logger.info("tts_owned_result_written bytes=%d", len(raw))


class OutputStore:
    """Restrict native audio persistence to fixed leaf names and a finite empty per-run private output capability."""

    def __init__(self, root):
        """Refuse foreign/wide-open output roots and initialize an explicit aggregate byte/file budget."""
        self.root = Path(root)
        if (
            self.root.is_symlink()
            or not self.root.is_dir()
            or self.root.stat().st_mode & 0o077
        ):
            raise ValueError("tts_output_root")
        self.total_bytes = 0
        self.waveforms = 0
        logger.info("tts_owned_output_store_opened")

    def save(self, values, rate, stem):
        """Retain complete native raw/WAV signals, including invalid-float failure evidence, without modifying previous outputs."""
        if type(stem) is not str or re.fullmatch(r"[a-z0-9_-]{1,80}", stem) is None:
            raise ValueError("tts_output_name")
        metadata = describe(values, rate)
        raw = np.ascontiguousarray(values, dtype="<f4").tobytes()
        wav = wave_bytes(values, rate)
        if (
            self.waveforms >= 30
            or self.total_bytes + len(raw) + len(wav) > 64 * 1024**2
        ):
            raise ValueError("tts_output_total_bound")
        raw_path, wav_path = self.root / (stem + ".f32"), self.root / (stem + ".wav")
        if os.path.lexists(raw_path) or os.path.lexists(wav_path):
            raise FileExistsError("tts_owned_result_exists")
        write_exclusive(raw_path, raw)
        write_exclusive(wav_path, wav)
        self.total_bytes += len(raw) + len(wav)
        self.waveforms += 1
        return dict(
            metadata,
            raw_filename=raw_path.name,
            wav_filename=wav_path.name,
            wav_sha256=hashlib.sha256(wav).hexdigest(),
            raw_bytes=len(raw),
            wav_bytes=len(wav),
        )


def asr_input(values, rate, resample_poly):
    """Use a supplied genuine rational anti-alias resampler and record separate unit-peak ASR normalization without altering native audio."""
    validate_samples(values, rate)
    if not np.isfinite(values).all() or float(np.max(np.abs(values))) > 16:
        raise ValueError("tts_asr_input_signal")
    common = math.gcd(rate, 16000)
    up, down = 16000 // common, rate // common
    converted = (
        np.asarray(resample_poly(values, up, down), dtype="<f4")
        if rate != 16000
        else values.copy()
    )
    expected = (len(values) * 16000 + rate - 1) // rate
    if (
        converted.ndim != 1
        or len(converted) != expected
        or not np.isfinite(converted).all()
    ):
        raise ValueError("tts_asr_resampler_contract")
    peak = float(np.max(np.abs(converted)))
    scale = 1.0 / peak if peak > 1 else 1.0
    if scale != 1:
        converted = (converted * scale).astype("<f4")
    raw = np.ascontiguousarray(converted, dtype="<f4").tobytes()
    logger.info(
        "tts_separate_asr_input_prepared source_rate=%d samples=%d unit_peak_scaled=%s",
        rate,
        len(converted),
        scale != 1,
    )
    return converted, dict(
        source_waveform_sha256=hashlib.sha256(
            np.ascontiguousarray(values, dtype="<f4").tobytes()
        ).hexdigest(),
        source_sample_rate=rate,
        source_sample_count=len(values),
        waveform_sha256=hashlib.sha256(raw).hexdigest(),
        sample_rate=16000,
        sample_count=len(converted),
        rational_up=up,
        rational_down=down,
        resample_method="scipy.signal.resample_poly",
        unit_peak_scale=scale,
        native_original_modified=False,
    )
