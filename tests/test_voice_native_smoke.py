"""Verify native voice evaluation conversion, candidate coverage and ownership without importing or executing original model weights."""

import asyncio
import io
import wave

import numpy as np
import pytest

from scripts.voice_native_smoke import MATRIX, EvaluationLLM, joined_io, pcm_wave
from src.application.ports.inference import CompletionResult


def test_pcm_conversion_retains_duration_and_declares_exact_native_samples():
    """Quantize a known public authored signal without changing rate, length, gain or order."""
    data = np.array([-1, 0, 1, 0.5], dtype="<f4")
    raw = pcm_wave(data.tobytes(), 16000)
    with wave.open(io.BytesIO(raw)) as audio:
        assert (
            audio.getframerate() == 16000
            and audio.getnframes() == 4
            and audio.getnchannels() == 1
        )
        actual = np.frombuffer(audio.readframes(4), dtype="<i2")
    assert actual.tolist() == [-32768, 0, 32767, 16384]


@pytest.mark.parametrize(
    "values,rate",
    [
        (np.array([np.nan], dtype="<f4"), 16000),
        (np.array([1.1], dtype="<f4"), 16000),
        (np.array([], dtype="<f4"), 16000),
        (np.zeros(1, dtype="<f4"), 48000),
    ],
)
def test_invalid_native_audio_is_not_repaired(values, rate):
    """Reject nonfinite, amplified, empty or unexpected-rate signals instead of normalizing a favourable output."""
    with pytest.raises(ValueError):
        pcm_wave(values.tobytes(), rate)


def test_matrix_covers_both_asr_and_all_supported_nominated_voice_paths():
    """Declare compatible evaluation paths without claiming Qwen explicit-Vietnamese support or choosing a default."""
    assert len(MATRIX) == 6
    assert len(set(MATRIX)) == 6
    assert all(
        not (tts == "qwen3-tts-0.6b" and lang == "vi") for _, tts, lang in MATRIX
    )


@pytest.mark.asyncio
async def test_thread_cancellation_waits_for_real_native_exit():
    """Hold a blocked native thread until it actually exits despite repeated caller cancellation."""
    import threading

    entered, release, finished = threading.Event(), threading.Event(), threading.Event()

    def native():
        """Emulate owned bounded native work with observable real-thread cleanup."""
        entered.set()
        release.wait(5)
        finished.set()

    task = asyncio.create_task(joined_io(native))
    await asyncio.to_thread(entered.wait, 2)
    task.cancel()
    await asyncio.sleep(0)
    task.cancel()
    await asyncio.sleep(0)
    assert not task.done() and not finished.is_set()
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert finished.is_set()


@pytest.mark.asyncio
async def test_first_llm_result_is_retained_before_downstream_failure(tmp_path):
    """Preserve a complete first CORE result even if later voice synthesis rejects its text length."""
    import json

    adapter = EvaluationLLM(tmp_path)

    async def reply(**kwargs):
        """Return one complete oversized public fixture reply without making a model request."""
        assert kwargs["preset"] == "fast"
        return CompletionResult("x" * 180, "core-fixture", "fast", "stop")

    adapter.adapter.complete = reply
    result = await adapter.complete(preset="fast", messages=[])
    assert result.content == "x" * 180
    assert (
        json.loads((tmp_path / "llm-response.json").read_text())["content"]
        == result.content
    )
    assert json.loads((tmp_path / "llm-request.json").read_text())["preset"] == "fast"
