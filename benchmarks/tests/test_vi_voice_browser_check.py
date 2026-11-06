"""Test exact HTTP preflight acceptance boundaries without starting the web surface or model runtimes."""

import base64

import pytest

from apps.voice_trial.audio import encode_wave
from benchmarks.scripts.vi_voice_browser_check import verify_answer


@pytest.mark.parametrize("seconds", [0.1, 4.0])
def test_exact_complete_output_within_maximum_is_accepted(seconds):
    """Keep the full response/audio and allow the exact4second boundary."""
    pcm = b"\0\0" * 16000
    verify_answer(
        dict(
            transcript="speech",
            answer="answer",
            audio_base64=base64.b64encode(encode_wave(pcm)).decode(),
            server_seconds=seconds,
        ),
        "speech",
        "answer",
        pcm,
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("server_seconds", 4.0001),
        ("server_seconds", True),
        ("server_seconds", float("nan")),
        ("transcript", "changed"),
        ("answer", "shortened"),
        ("audio_base64", "AAAA"),
    ],
)
def test_changed_or_slow_outputs_never_become_PASS(field, value):
    """Refuse truncation, different ASR/audio, boolean timing and out-of-bound maximum latency."""
    pcm = b"\0\0" * 16000
    result = dict(
        transcript="speech",
        answer="answer",
        audio_base64=base64.b64encode(encode_wave(pcm)).decode(),
        server_seconds=1.0,
    )
    result[field] = value
    with pytest.raises(ValueError, match="voice_HTTP"):
        verify_answer(result, "speech", "answer", pcm)
