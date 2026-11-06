"""Validate canonical browser PCM WAV and encode complete returned speech without resampling captured audio."""

import logging
import struct

from src.application.ports.audio import NormalizedAudio
from src.application.services.voice_pipeline import VoiceError, digest

LOGGER = logging.getLogger(__name__)
MAX_BODY = 44 + 320000 * 2


def encode_wave(pcm):
    """Wrap bounded complete mono16k PCM16 bytes in the canonical browser WAV header."""
    if type(pcm) is not bytes or len(pcm) % 2 or not 2 <= len(pcm) <= 960000:
        raise VoiceError("invalid_result")
    LOGGER.info("trial_wave_encoded samples=%d", len(pcm) // 2)
    return (
        struct.pack(
            "<4sI4s4sIHHIIHH4sI",
            b"RIFF",
            36 + len(pcm),
            b"WAVE",
            b"fmt ",
            16,
            1,
            1,
            16000,
            32000,
            2,
            16,
            b"data",
            len(pcm),
        )
        + pcm
    )


def decode_wave(raw):
    """Accept only1–20seconds of the explicit recorder's exact uncompressed PCM with no gain, trimming or clock changes."""
    if type(raw) is not bytes or not 32044 <= len(raw) <= MAX_BODY:
        raise VoiceError("invalid_input")
    pcm = raw[44:]
    if encode_wave(pcm) != raw:
        raise VoiceError("invalid_input")
    LOGGER.info("trial_browser_audio_validated samples=%d", len(pcm) // 2)
    return NormalizedAudio(
        digest(raw),
        digest(pcm),
        pcm,
        len(pcm) // 2,
        "pcm_s16le",
        16000,
        1,
        len(pcm) // 2,
        1,
        16000,
        0,
    )
