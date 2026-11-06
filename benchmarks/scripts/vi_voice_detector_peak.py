"""Normalize only detector-copy peaks without an arbitrary gain ceiling, preserving original ASR PCM and audit binding."""

import asyncio
import hashlib
import logging
from uuid import UUID

import numpy as np

from benchmarks.scripts.vi_voice_detector_view import DetectorView, ViewObservation
from benchmarks.scripts.vi_voice_presence import (
    VAD_MODEL,
    SpeechPresence,
    validate_presence,
)
from src.application.services.voice_pipeline import VoiceError, normalized

LOGGER = logging.getLogger(__name__)
POLICY = "detector-peak-half-v2"


def detector_view(audio):
    """Boost the detector copy to peak0.5; PCM quantization bounds gain mathematically by16384 without clipping."""
    normalized(audio)
    values = np.frombuffer(audio.pcm_s16le, dtype="<i2").astype(np.float64) / 32768
    peak = float(np.max(np.abs(values)))
    gain = 1.0 if peak == 0 else max(1.0, 0.5 / peak)
    raw = (values * gain).astype("<f4").tobytes()
    LOGGER.info(
        "voice_peak_view_created samples=%d gain=%.6f policy=%s",
        audio.sample_count,
        gain,
        POLICY,
    )
    return DetectorView(
        audio.pcm_sha256,
        hashlib.sha256(raw).hexdigest(),
        audio.sample_count,
        gain,
        raw,
        POLICY,
    )


class ViewDetector:
    """Verify native normalized-view evidence and publish source provenance before original ASR admission."""

    def __init__(self, backend, audit):
        """Inject the fixed existing detector backend and mandatory trace sink without model selection."""
        self.backend, self.audit = backend, audit
        LOGGER.info("voice_peak_detector_initialized product_activation=False")

    async def detect(self, owner, audio):
        """Rebind only complete exact-view observations, using the unchanged strict source/interval verifier."""
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
        ):
            raise VoiceError("invalid_result")
        presence = SpeechPresence(
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
        validate_presence(presence, owner, audio)
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
        LOGGER.info("voice_peak_detector_verified full_original_pcm_preserved=True")
        return presence
