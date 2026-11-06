"""Create bounded detector-only amplitude views while retaining original PCM for the research ASR gate."""

import asyncio
import hashlib
import logging
import math
from dataclasses import dataclass
from uuid import UUID

import numpy as np

from benchmarks.scripts.vi_voice_presence import SpeechPresence, VAD_MODEL
from src.application.services.voice_pipeline import VoiceError, normalized

LOGGER = logging.getLogger(__name__)
POLICY = "detector-peak-half-boost32-v1"


@dataclass(frozen=True, slots=True, repr=False)
class DetectorView:
    """Bind one full-length detector copy to the original PCM and a fixed non-clipping gain policy."""

    pcm_sha256: str
    waveform_sha256: str
    sample_count: int
    gain: float
    waveform_f32: bytes
    policy: str = POLICY


@dataclass(frozen=True, slots=True, repr=False)
class ViewObservation:
    """Describe a complete model observation of one exact detector-view waveform."""

    waveform_sha256: str
    sample_count: int
    segments: tuple[tuple[int, int], ...]
    model_id: str = VAD_MODEL
    complete: bool = True


def detector_view(audio):
    """Boost only the detector copy toward peak 0.5 with gain at most32, preserving length and source PCM."""
    normalized(audio)
    values = np.frombuffer(audio.pcm_s16le, dtype="<i2").astype(np.float64) / 32768
    peak = float(np.max(np.abs(values)))
    gain = 1.0 if peak == 0 else min(32.0, max(1.0, 0.5 / peak))
    raw = (values * gain).astype("<f4").tobytes()
    LOGGER.info(
        "voice_detector_view_created samples=%d gain=%.6f policy=%s",
        audio.sample_count,
        gain,
        POLICY,
    )
    return DetectorView(
        audio.pcm_sha256, hashlib.sha256(raw).hexdigest(), audio.sample_count, gain, raw
    )


class ViewDetector:
    """Rebind only verified native-view observations to original audio without altering the ASR input."""

    def __init__(self, backend, audit):
        """Require explicit trusted model execution and redacted audit sinks without loading any model."""
        self.backend, self.audit = backend, audit
        LOGGER.info("voice_view_detector_initialized product_activation=False")

    async def detect(self, owner, audio):
        """Verify view provenance and publish its trace before returning source-bound speech evidence."""
        if type(owner) is not UUID:
            raise VoiceError("invalid_input")
        view = detector_view(audio)
        result = await self.backend.observe(view)
        if asyncio.current_task().cancelling():
            raise asyncio.CancelledError()
        if (
            type(result) is not ViewObservation
            or result.complete is not True
            or type(result.sample_count) is not int
            or (result.waveform_sha256, result.sample_count, result.model_id)
            != (view.waveform_sha256, audio.sample_count, VAD_MODEL)
            or type(result.segments) is not tuple
            or len(result.segments) > 128
        ):
            raise VoiceError("invalid_result")
        end = 0
        for span in result.segments:
            if (
                type(span) is not tuple
                or len(span) != 2
                or any(type(x) is not int for x in span)
                or not end <= span[0] < span[1] <= audio.sample_count
            ):
                raise VoiceError("invalid_result")
            end = span[1]
        if not math.isfinite(view.gain) or not 1 <= view.gain <= 32:
            raise VoiceError("invalid_result")
        await self.audit(
            dict(
                policy=POLICY,
                owner_id=str(owner),
                source_sha256=audio.source_sha256,
                pcm_sha256=audio.pcm_sha256,
                sample_count=audio.sample_count,
                first_pts=audio.first_pts,
                time_base_num=audio.time_base_num,
                time_base_den=audio.time_base_den,
                detector_waveform_sha256=view.waveform_sha256,
                gain=view.gain,
                segments=len(result.segments),
            )
        )
        if asyncio.current_task().cancelling():
            raise asyncio.CancelledError()
        LOGGER.info("voice_view_detector_verified original_pcm_preserved=True")
        return SpeechPresence(
            owner,
            audio.source_sha256,
            audio.pcm_sha256,
            audio.sample_count,
            audio.first_pts,
            audio.time_base_num,
            audio.time_base_den,
            VAD_MODEL,
            result.segments,
        )
