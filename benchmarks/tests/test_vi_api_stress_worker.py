"""Verify term-only stress edits and unchanged clause, voice, frame and native joining behavior."""

from types import SimpleNamespace

import numpy as np
import pytest

from benchmarks.scripts.vi_api_stress_worker import (
    ApiStressAdapter,
    SOURCE,
    TARGET,
    replace_api,
)


def test_only_api_stress_changes_and_ambiguous_inputs_fail():
    """Preserve exact context, Python phones, punctuation, length and non-target chunks."""
    text = "pˈaɪθən " + SOURCE + "?"
    changed, count = replace_api(text)
    assert changed == "pˈaɪθən " + TARGET + "?" and count == 1
    assert len(changed) == len(text)
    assert replace_api("unchanged date.") == ("unchanged date.", 0)
    for bad in (SOURCE + SOURCE, TARGET):
        with pytest.raises(ValueError):
            replace_api(bad)


def adapter_fixture(frame_cap=len):
    """Create a public two-clause engine fixture without loading SDK or model artifacts."""
    calls = []
    speaker, codes = object(), object()
    waves = [np.array([0.1, 0.2], dtype=np.float32), np.array([0.3], dtype=np.float32)]

    def infer(**kwargs):
        """Return independent original samples and capture every decoding parameter."""
        calls.append(kwargs)
        return waves[len(calls) - 1]

    def resolve(voice, reference, denoise, use_codes):
        """Reject any reference-off or different voice route before the fake neural call."""
        assert voice == "Trúc Ly" and reference is None and denoise is use_codes is True
        return speaker, codes

    def phonemize(text, punc_norm):
        """Return an unchanged date chunk followed by the one target acronym chunk."""
        assert punc_norm is False
        return "date phones." if text == "Date." else "pˈaɪθən " + SOURCE + "?"

    def join(values, rate, silence_ps):
        """Require the exact returned native objects and original gap to reach joining."""
        assert all(a is b for a, b in zip(values, waves, strict=True))
        assert rate == 48000 and silence_ps == [0.2]
        return np.concatenate(values)

    deps = dict(
        normalize=lambda text, **kw: text,
        split=lambda text: ["Date.", "API?"],
        pack=lambda rows, **kw: rows,
        classify=lambda text: "sentence",
        phonemize=phonemize,
        frame_cap=frame_cap,
        repetition_window=64,
        pauses=lambda gaps: [0.2],
        join=join,
    )
    wrapper = SimpleNamespace(
        engine=SimpleNamespace(infer=infer),
        sample_rate=48000,
        _resolve_ref=resolve,
        _apply_watermark=lambda values: values,
    )
    return ApiStressAdapter(wrapper, deps), calls, waves, speaker, codes


def test_original_adapter_owns_every_nonterm_decoding_and_join_boundary():
    """Change API stresses only while preserving first date waveform and original sampling/reference settings."""
    adapter, calls, waves, speaker, codes = adapter_fixture()
    result = adapter.infer("Original date and API?", voice="Trúc Ly")
    assert np.array_equal(result, np.concatenate(waves)) and len(calls) == 2
    assert calls[0]["phonemes"] == "date phones."
    assert calls[1]["phonemes"] == "pˈaɪθən " + TARGET + "?"
    for call in calls:
        assert call["speaker_emb"] is speaker and call["ref_codes"] is codes
        assert call["use_ref_codes"] is True
        assert (
            call["temperature"],
            call["top_k"],
            call["top_p"],
            call["repetition_penalty"],
            call["repetition_window"],
        ) == (0.8, 25, 0.95, 1.2, 64)
        assert call["max_new_frames"] == len(call["phonemes"])
    assert adapter.last_trace["chunks"] == ["Date.", "API?"]
    assert [row["replacements"] for row in adapter.last_trace["api_stress"]] == [0, 1]
    assert adapter.last_chunks[0] is waves[0]


def test_frame_drift_is_rejected_before_any_neural_call():
    """Refuse a stress edit if the original frame computation would change its allowance."""
    adapter, calls, *_ = adapter_fixture(lambda ph: 10 if TARGET not in ph else 11)
    with pytest.raises(ValueError, match="frame_cap_changed"):
        adapter.infer("Original date and API?", voice="Trúc Ly")
    assert calls == []
