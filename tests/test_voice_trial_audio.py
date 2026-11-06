"""Test strict browser WAV admission and unmodified sample clocks without models or device access."""

import pytest

from apps.voice_trial.audio import decode_wave, encode_wave
from src.application.services.voice_pipeline import VoiceError, normalized


@pytest.mark.parametrize("samples", [16000, 81600, 320000])
def test_canonical_pcm_is_identical_and_source_clock_is_preserved(samples):
    """Admit complete one-to-twenty-second recordings without repair, resampling or changed original PCM."""
    pcm = b"\x01\x02" * samples
    raw = encode_wave(pcm)
    audio = normalized(decode_wave(raw))
    assert audio.pcm_s16le == pcm and audio.sample_count == samples
    assert (audio.first_pts, audio.time_base_num, audio.time_base_den) == (0, 1, 16000)
    assert not audio.persisted


@pytest.mark.parametrize(
    "bad",
    ["short", "long", "odd", "rate", "codec", "channels", "size", "extra", "empty"],
)
def test_noncanonical_or_out_of_scope_audio_is_rejected(bad):
    """Refuse invalid size/format rather than clipping, padding or accepting compressed media."""
    raw = bytearray(encode_wave(b"\0\0" * 16000))
    if bad == "short":
        raw = bytearray(encode_wave(b"\0\0" * 15999))
    elif bad == "long":
        raw = bytearray(encode_wave(b"\0\0" * 320001))
    elif bad == "odd":
        raw.pop()
    elif bad == "rate":
        raw[24:28] = (48000).to_bytes(4, "little")
    elif bad == "codec":
        raw[20:22] = (3).to_bytes(2, "little")
    elif bad == "channels":
        raw[22:24] = (2).to_bytes(2, "little")
    elif bad == "size":
        raw[4:8] = b"\0" * 4
    elif bad == "extra":
        raw.extend(b"secret")
    else:
        raw = bytearray()
    with pytest.raises(VoiceError):
        decode_wave(bytes(raw))
