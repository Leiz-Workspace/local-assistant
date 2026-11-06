"""Test single-variable reference ablation, exact text token admission and immutable speaker/decoding boundaries."""

from types import SimpleNamespace

import numpy as np
import pytest

from benchmarks.scripts.vi_api_reference_worker import ReferenceAdapter


class Tokenizer:
    """Provide exact public phoneme token roundtrips without private files or neural weights."""

    def encode(self, text, add_special_tokens):
        """Return deterministic distinct public token IDs and retain source text."""
        assert add_special_tokens is False
        self.text = text
        return SimpleNamespace(ids=[44, 45, 46])

    def decode(self, ids, skip_special_tokens):
        """Return unmodified input phonemes with all symbols preserved."""
        assert ids == [44, 45, 46] and skip_special_tokens is False
        return self.text

    def token_to_id(self, value):
        """Identify the reserved unknown token."""
        assert value == "<|unk|>"
        return 43


def fixture():
    """Create an original-style wrapper with observable calls and exact preset objects."""
    speaker = np.array([0.1, 0.2], dtype="float32")
    codes = np.ones((2, 16), dtype="int64")
    waveform = np.array([0.1, 0.2, 0.3], dtype="float32")
    calls = []
    engine = SimpleNamespace(tokenizer=Tokenizer(), tps=3, tpe=4)

    def build(phonemes, ref, style):
        """Build only deterministic prompt rows and optional original reference rows."""
        ids = [style, 3] + [44, 45, 46] + [4]
        extra = 0 if ref is None else len(ref)
        rows = np.full((len(ids) + extra, 17), 1024, dtype="int64")
        rows[: len(ids), 0] = ids
        if extra:
            rows[len(ids) :, 0] = 7
        return rows

    def native(**kwargs):
        """Record one engine request and return the exact native waveform object."""
        calls.append(kwargs)
        return waveform

    def resolve(voice, audio, denoise, use_codes):
        """Require the named preset without cloning and preserve its speaker object."""
        assert voice in {"Trúc Ly", "Ngọc Huyền"} and audio is None and denoise is True
        return speaker, codes if use_codes else None

    engine._build_rows = build
    engine._speaker_anchor = lambda supplied: supplied * 2
    engine._resolve_style_id = lambda: 16
    engine.infer = native
    wrapper = SimpleNamespace(
        engine=engine, _resolve_ref=resolve, _apply_watermark=lambda wav: wav
    )
    return wrapper, speaker, codes, waveform, calls


def test_only_reference_codes_change_and_speaker_sampling_are_exact():
    """Keep the exact speaker/text/sampler across the pair while dropping only reference frames."""
    wrapper, speaker, codes, waveform, calls = fixture()
    traces = []
    for mode in ["with_reference", "without_reference"]:
        adapter = ReferenceAdapter(wrapper, mode, lambda ph: 28, 64)
        assert adapter.infer("ˈeɪ pˈiː ˈaɪ.", voice="Trúc Ly") is waveform
        traces.append(adapter.last_trace)
    assert (
        len(calls) == 2
        and calls[0]["ref_codes"] is codes
        and calls[1]["ref_codes"] is None
    )
    assert calls[0]["speaker_emb"] is calls[1]["speaker_emb"] is speaker
    assert calls[0]["phonemes"] == calls[1]["phonemes"]
    for key in [
        "temperature",
        "top_k",
        "top_p",
        "max_new_frames",
        "repetition_penalty",
        "repetition_window",
    ]:
        assert calls[0][key] == calls[1][key]
    assert calls[0]["temperature"] == 0.8 and calls[0]["max_new_frames"] == 28
    assert (
        traces[0]["speaker_embedding_sha256"] == traces[1]["speaker_embedding_sha256"]
    )
    assert traces[0]["projected_anchor_sha256"] == traces[1]["projected_anchor_sha256"]
    assert traces[0]["reference_rows"] == 2 and traces[1]["reference_rows"] == 0


def test_bad_roundtrip_never_reaches_model():
    """Reject tokenizer text loss before any engine inference."""
    wrapper, _, _, _, calls = fixture()
    wrapper.engine.tokenizer.decode = lambda *a, **kw: "changed"
    with pytest.raises(ValueError, match="roundtrip"):
        ReferenceAdapter(wrapper, "with_reference", lambda ph: 28, 64).infer(
            "ˈeɪ.", voice="Trúc Ly"
        )
    assert calls == []


def test_wrong_prompt_ids_never_reach_model():
    """Reject wrong actual prompt IDs rather than relying only on phoneme logs."""
    wrapper, _, _, _, calls = fixture()
    wrapper.engine._build_rows = lambda *args: np.zeros((6, 17), dtype="int64")
    with pytest.raises(ValueError, match="prompt_text_ids"):
        ReferenceAdapter(wrapper, "without_reference", lambda ph: 28, 64).infer(
            "ˈeɪ.", voice="Trúc Ly"
        )
    assert calls == []


def test_modes_voices_and_input_are_bounded():
    """Forbid alternate modes/presets and unbounded phoneme overrides."""
    wrapper, _, _, _, calls = fixture()
    with pytest.raises(ValueError):
        ReferenceAdapter(wrapper, "unknown", lambda ph: 28, 64)
    adapter = ReferenceAdapter(wrapper, "with_reference", lambda ph: 28, 64)
    for phonemes, voice in [
        ("", "Trúc Ly"),
        ("x" * 1025, "Trúc Ly"),
        ("ˈeɪ.", "default"),
    ]:
        with pytest.raises(ValueError):
            adapter.infer(phonemes, voice=voice)
    assert calls == []
