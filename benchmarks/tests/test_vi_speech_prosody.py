"""Test question-preserving phoneme routing and exact original sampling/voice/codec boundaries without models."""

from types import SimpleNamespace

import numpy as np
import pytest

from benchmarks.scripts.vi_speech_prosody import ProsodyAdapter, preserving_chunks


def test_short_question_survives_normalization_and_chunking():
    """Prevent the known short-question-to-period transformation at the research boundary."""
    flags = []

    def normalize(text, punc_norm):
        """Require punctuation preservation for every sentence."""
        flags.append(punc_norm)
        return text.lower()

    chunks, gaps = preserving_chunks(
        "Bạn đồng ý chứ?",
        normalize,
        lambda text: [text],
        lambda rows, max_chars: rows,
        lambda text: "sentence",
    )
    assert chunks == ["bạn đồng ý chứ?"] and gaps == [] and flags == [False]


def test_sentence_boundaries_never_split_a_time_or_date_phrase():
    """Keep normalized time/date phrases intact and split only at declared sentence boundaries."""
    sentence = "Hẹn lúc chín giờ mười lăm phút ngày mười bốn tháng mười một."
    chunks, gaps = preserving_chunks(
        sentence + " Bạn đồng ý chứ?",
        lambda text, **kwargs: text,
        lambda text: [sentence, "Bạn đồng ý chứ?"],
        lambda rows, max_chars: rows,
        lambda text: "sentence",
    )
    assert chunks == [sentence, "Bạn đồng ý chứ?"] and gaps == ["sentence"]
    with pytest.raises(ValueError, match="too_long"):
        preserving_chunks(
            "x" * 257,
            lambda text, **kwargs: text,
            lambda text: [text],
            lambda rows, max_chars: rows,
            lambda text: "minor",
        )
    with pytest.raises(ValueError, match="packing_changed"):
        preserving_chunks(
            "hẹn lúc 09:15",
            lambda text, **kwargs: text,
            lambda text: [text],
            lambda rows, max_chars: ["hẹn lúc", "09:15"],
            lambda text: "minor",
        )


def test_native_adapter_keeps_original_voice_sampling_caps_and_order():
    """Forward exact preset objects, use each original chunk once and leave returned native samples unchanged."""
    speaker, codes = object(), object()
    waveforms = [
        np.array([0.1, 0.2], dtype="float32"),
        np.array([0.3, 0.4], dtype="float32"),
    ]
    calls = []

    def infer(**kwargs):
        """Record native parameters and return original independent waveform objects."""
        calls.append(kwargs)
        return waveforms[len(calls) - 1]

    def resolve(voice, reference, denoise, use_codes):
        """Require an allowed preset without any cloning or reference audio."""
        assert (
            voice == "Trúc Ly"
            and reference is None
            and denoise is True
            and use_codes is True
        )
        return speaker, codes

    def phonemize(text, punc_norm):
        """Preserve the actual question mark in the explicit phoneme request."""
        assert punc_norm is False
        return "ph:" + text

    def join(rows, rate, silence_ps):
        """Verify exact native objects reach the original-style joining boundary."""
        assert rows[0] is waveforms[0] and rows[1] is waveforms[1]
        assert rate == 48000 and silence_ps == [0.2]
        return np.concatenate(rows)

    wrapper = SimpleNamespace(
        engine=SimpleNamespace(infer=infer),
        sample_rate=48000,
        _resolve_ref=resolve,
        _apply_watermark=lambda values: values,
    )
    dependencies = dict(
        normalize=lambda text, **kwargs: text,
        split=lambda text: ["Chị hiểu.", "Bạn đồng ý chứ?"],
        pack=lambda rows, max_chars: rows,
        classify=lambda text: "sentence",
        phonemize=phonemize,
        pauses=lambda gaps: [0.2],
        join=join,
        frame_cap=lambda ph: 28,
        repetition_window=64,
    )
    adapter = ProsodyAdapter(wrapper, dependencies)
    result = adapter.infer("Chị hiểu. Bạn đồng ý chứ?", voice="Trúc Ly")
    assert len(calls) == 2 and calls[1]["phonemes"].endswith("?")
    for call in calls:
        assert call["speaker_emb"] is speaker and call["ref_codes"] is codes
        assert (
            call["temperature"] == 0.8 and call["top_k"] == 25 and call["top_p"] == 0.95
        )
        assert call["max_new_frames"] == 28 and call["repetition_penalty"] == 1.2
    assert np.array_equal(result, np.concatenate(waveforms))
    assert adapter.last_chunks[0] is waveforms[0]
    assert adapter.last_trace["short_question_punctuation_preserved"] is True
    with pytest.raises(ValueError):
        adapter.infer("text", voice="default")
