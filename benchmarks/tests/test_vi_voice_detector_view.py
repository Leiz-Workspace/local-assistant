"""Test fixed detector-only boosting, exact source/view binding and fail-closed whole-clip integration."""

import asyncio
import hashlib
from dataclasses import replace
from types import SimpleNamespace
from uuid import uuid4

import numpy as np
import pytest

from benchmarks.scripts.vi_voice_detector_view import (
    ViewDetector,
    ViewObservation,
    detector_view,
)
from benchmarks.scripts.vi_voice_presence import WholeClipASR
from benchmarks.tests.test_vi_voice_presence import audio
from src.application.services.voice_pipeline import VoiceError, digest


@pytest.mark.parametrize(
    "samples",
    [[0] * 32000, [1, -1] * 16000, [100, -200] * 16000, [32767, -32768] * 16000],
)
def test_detector_copy_never_changes_pcm_length_clock_or_clips(samples):
    """Check silence, tiny signals and full-scale asymmetric PCM against the fixed numeric policy."""
    source = audio()
    raw = np.array(samples, dtype="<i2").tobytes()
    source = replace(source, pcm_s16le=raw, pcm_sha256=digest(raw))
    view = detector_view(source)
    assert source.pcm_s16le == raw and source.first_pts == 2500
    original = np.array(samples, dtype=np.float64) / 32768
    peak = max(abs(original))
    expected = 1.0 if peak == 0 else min(32.0, max(1.0, 0.5 / peak))
    assert view.gain == expected and len(view.waveform_f32) == len(samples) * 4
    values = np.frombuffer(view.waveform_f32, dtype="<f4")
    assert np.isfinite(values).all() and np.max(np.abs(values)) <= max(0.5, peak)
    assert view.waveform_f32 == (original * expected).astype("<f4").tobytes()
    assert hashlib.sha256(view.waveform_f32).hexdigest() == view.waveform_sha256
    assert view.pcm_sha256 == source.pcm_sha256


@pytest.mark.asyncio
@pytest.mark.parametrize("segments", [(), ((2, 1000),)])
async def test_verified_view_projects_to_original_owner_and_clock(segments, caplog):
    """Require one redacted audit before the old gate sees a source-bound native-view decision."""
    caplog.set_level("INFO")
    value, owner = audio(), uuid4()
    traces = []

    async def observe(view):
        """Return authored backend evidence bound to the exact detector-only bytes."""
        return ViewObservation(view.waveform_sha256, view.sample_count, segments)

    async def audit(trace):
        """Collect only declared provenance without retaining PCM or transcript content."""
        traces.append(trace)

    result = await ViewDetector(SimpleNamespace(observe=observe), audit).detect(
        owner, value
    )
    assert result.owner_id == owner and result.pcm_sha256 == value.pcm_sha256
    assert result.first_pts == value.first_pts and result.segments == segments
    assert (
        len(traces) == 1
        and traces[0]["detector_waveform_sha256"]
        == detector_view(value).waveform_sha256
    )
    assert "waveform_f32" not in traces[0] and "pcm_s16le" not in traces[0]
    assert "waveform_f32" not in repr(detector_view(value))


@pytest.mark.parametrize(
    "field,bad",
    [
        ("waveform_sha256", "b" * 64),
        ("sample_count", 32001),
        ("sample_count", True),
        ("model_id", "other"),
        ("complete", False),
        ("complete", 1),
        ("segments", []),
        ("segments", ((0, 0),)),
        ("segments", ((False, 10),)),
        ("segments", ((1, 100), (99, 200))),
        ("segments", ((0, 32001),)),
    ],
)
@pytest.mark.asyncio
async def test_invalid_observation_cannot_be_rebound_or_audited(field, bad):
    """Reject wrong views and model evidence rather than relabeling them as the original PCM."""
    traces = []

    async def observe(view):
        """Return one individually corrupted observation field."""
        return replace(
            ViewObservation(view.waveform_sha256, view.sample_count, ()), **{field: bad}
        )

    async def audit(trace):
        """Fail validation if rejected backend evidence reaches publication."""
        traces.append(trace)

    with pytest.raises(VoiceError, match="invalid_result"):
        await ViewDetector(SimpleNamespace(observe=observe), audit).detect(
            uuid4(), audio()
        )
    assert not traces


@pytest.mark.asyncio
async def test_missing_audit_cannot_forward_original_audio():
    """Keep audit publication inside the fail-closed boundary of the existing ASR wrapper."""
    called = []

    async def observe(view):
        """Return valid speech evidence so only the audit fault decides the result."""
        return ViewObservation(view.waveform_sha256, view.sample_count, ((0, 1000),))

    async def audit(trace):
        """Simulate an unavailable audit sink without leaking backend error details."""
        raise RuntimeError("private audit detail")

    async def transcribe(*args):
        """Record any forbidden downstream inference after the audit failure."""
        called.append(True)

    wrapper = WholeClipASR(
        detector=ViewDetector(SimpleNamespace(observe=observe), audit),
        asr=SimpleNamespace(transcribe=transcribe),
        asr_model="fixture-asr",
    )
    with pytest.raises(VoiceError, match="dependency_failed"):
        await wrapper.transcribe(uuid4(), audio(), "vi")
    assert not called


@pytest.mark.asyncio
async def test_backend_cancellation_is_joined_before_original_audio_can_forward():
    """Retain the old wrapper's ownership semantics while the new detector backend is active."""
    entered, retired = asyncio.Event(), asyncio.Event()
    called = []

    async def observe(view):
        """Expose deterministic entry and retirement of a cancelled detector backend."""
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            retired.set()

    async def audit(trace):
        """Reject publication after an interrupted model observation."""
        called.append("audit")

    wrapper = WholeClipASR(
        detector=ViewDetector(SimpleNamespace(observe=observe), audit),
        asr=None,
        asr_model="fixture-asr",
    )
    task = asyncio.create_task(wrapper.transcribe(uuid4(), audio(), "vi"))
    await asyncio.wait_for(entered.wait(), 1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert retired.is_set() and not called and wrapper.active is None


@pytest.mark.asyncio
async def test_invalid_source_never_reaches_model():
    """Reuse the application normalized-audio contract before constructing a detector view."""
    with pytest.raises(VoiceError, match="invalid_input"):
        detector_view(replace(audio(), pcm_sha256="b" * 64))
    with pytest.raises(VoiceError, match="invalid_input"):
        await ViewDetector(None, None).detect("owner", audio())
