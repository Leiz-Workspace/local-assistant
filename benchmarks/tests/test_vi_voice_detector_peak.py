"""Verify mathematically bounded peak views and strict native-to-original provenance without changing ASR PCM."""

from dataclasses import replace
from types import SimpleNamespace
from uuid import uuid4

import numpy as np
import pytest

from benchmarks.scripts import vi_voice_detector_peak as target
from benchmarks.scripts.vi_voice_detector_view import ViewObservation
from benchmarks.tests.test_vi_voice_presence import audio
from src.application.services.voice_pipeline import VoiceError, digest


@pytest.mark.parametrize("amplitude", [0, 1, 2, 15, 300, 8192, 16384, 32767, -32768])
def test_fixed_peak_rule_preserves_exact_original_and_never_clips(amplitude):
    """Check numeric extremes including the16384maximum gain implied by one PCM quantum."""
    raw = np.full(32000, amplitude, dtype="<i2").tobytes()
    value = replace(audio(), pcm_s16le=raw, pcm_sha256=digest(raw))
    view = target.detector_view(value)
    peak = abs(amplitude) / 32768
    assert 1 <= view.gain <= 16384 and view.policy == target.POLICY
    assert view.gain == (1 if peak == 0 else max(1, 0.5 / peak))
    assert np.max(np.abs(np.frombuffer(view.waveform_f32, dtype="<f4"))) == (
        0 if peak == 0 else max(0.5, peak)
    )
    assert value.pcm_s16le == raw and value.first_pts == 2500


@pytest.mark.parametrize(
    "field,bad",
    [
        ("waveform_sha256", "b" * 64),
        ("sample_count", True),
        ("model_id", "other"),
        ("complete", False),
        ("segments", ((0, 0),)),
        ("segments", ((1, 10), (9, 20))),
        ("segments", []),
    ],
)
@pytest.mark.asyncio
async def test_malformed_native_view_never_reaches_audit(field, bad):
    """Keep the same strict complete-evidence and sample-bound checks after removing the arbitrary gain ceiling."""
    traces = []

    async def observe(view):
        """Return one corrupted native result field for a source-bound model request."""
        return replace(
            ViewObservation(view.waveform_sha256, view.sample_count, ()), **{field: bad}
        )

    async def audit(trace):
        """Observe any forbidden publication of rejected backend evidence."""
        traces.append(trace)

    with pytest.raises(VoiceError, match="invalid_result"):
        await target.ViewDetector(SimpleNamespace(observe=observe), audit).detect(
            uuid4(), audio()
        )
    assert not traces


@pytest.mark.asyncio
async def test_valid_v2_decision_retains_full_original_binding():
    """Publish the actual v2view hash while returning original owner/PCM/clock provenance."""
    value = audio()
    owner = uuid4()
    traces = []

    async def observe(view):
        """Return valid complete speech evidence for the exact fixed peak view."""
        return ViewObservation(view.waveform_sha256, view.sample_count, ((2, 1000),))

    async def audit(trace):
        """Retain only redacted provenance, never full audio or transcript data."""
        traces.append(trace)

    result = await target.ViewDetector(SimpleNamespace(observe=observe), audit).detect(
        owner, value
    )
    assert result.pcm_sha256 == value.pcm_sha256 and result.first_pts == value.first_pts
    assert result.owner_id == owner and traces[0]["policy"] == target.POLICY
    assert (
        traces[0]["detector_waveform_sha256"]
        == target.detector_view(value).waveform_sha256
    )
