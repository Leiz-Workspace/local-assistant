"""Test isolated US term edits, conservative caps, accepted API preservation and unchanged voice/native joining."""

from types import SimpleNamespace

import numpy as np
import pytest

from benchmarks.scripts import vi_us_terms_worker as worker
from benchmarks.scripts.vi_api_stress_worker import SOURCE, TARGET


def test_python_edit_preserves_api_and_every_surrounding_phone():
    """Retain the accepted API stresses and exact context while changing only the US Python vowel."""
    case = worker.CASES[0]
    raw = "prefix pˈaɪθən middle " + SOURCE + " suffix?"
    plan = worker.phone_plan(raw, case, len)
    assert plan["baseline"] == "prefix pˈaɪθən middle " + TARGET + " suffix?"
    assert plan["us"] == "prefix pˈaɪθɑːn middle " + TARGET + " suffix?"
    assert plan["shared_cap"] == len(plan["baseline"]) < len(plan["us"])
    assert plan["api_replacements"] == 1 and [r["term"] for r in plan["edits"]] == [
        "python"
    ]
    with pytest.raises(ValueError):
        worker.phone_plan(raw + " pˈaɪθən", case, len)
    with pytest.raises(ValueError):
        worker.phone_plan(raw.replace(SOURCE, "missing"), case, len)


def test_compound_caps_never_increase_and_control_terms_are_not_rewritten():
    """Reduce a shorter compound's common budget and preserve already retained control phones exactly."""
    case = worker.CASES[3]
    plan = worker.phone_plan("prefix ɡˈɪt hˈʌb suffix.", case, len)
    assert plan["shared_cap"] == len(plan["us"]) < len(plan["baseline"])
    for index, term in [(2, "docker"), (4, "browser")]:
        raw = "prefix " + worker.CONTROLS[term] + " suffix."
        plan = worker.phone_plan(raw, worker.CASES[index], len)
        assert (
            plan["same_input"]
            and plan["baseline"] == plan["us"] == raw
            and plan["edits"] == []
        )
    raw = "sˈɜːvɚ prefix " + worker.CONTROLS["database"] + "."
    plan = worker.phone_plan(raw, worker.CASES[5], len)
    assert plan["us"] == raw.replace("sˈɜːvɚ", "sˈɜːɹvɚ")
    assert worker.CONTROLS["database"] in plan["us"]


@pytest.mark.parametrize("mode", ["baseline", "us"])
def test_original_adapter_keeps_voice_references_sampling_and_native_samples(mode):
    """Use the exact original speaker/code objects and joining path under both declared phone roles."""
    calls = []
    speaker = np.array([0.1, 0.2], dtype=np.float32)
    codes = np.array([[1, 2]], dtype=np.int64)
    wave = np.array([0.1, 0.2, 0.3], dtype=np.float32)

    def resolve(voice, reference, denoise, use_codes):
        """Return original preset objects only with the retained reference policy."""
        assert voice == "Trúc Ly" and reference is None and denoise is use_codes is True
        return speaker, codes

    def infer(**kwargs):
        """Capture every original decoding control without running any model."""
        calls.append(kwargs)
        return wave

    def join(waves, rate, silence_ps):
        """Require the exact returned native object to reach original-style joining."""
        assert waves[0] is wave and rate == 48000 and silence_ps == []
        return wave

    raw = "pˈaɪθən " + SOURCE + "?"
    deps = dict(
        normalize=lambda t, **k: t,
        split=lambda t: [t],
        pack=lambda rows, **k: rows,
        classify=lambda t: "sentence",
        phonemize=lambda t, **k: raw,
        frame_cap=len,
        repetition_window=64,
        join=join,
        pauses=lambda gaps: [],
    )
    wrapper = SimpleNamespace(
        engine=SimpleNamespace(infer=infer),
        _resolve_ref=resolve,
        _apply_watermark=lambda value: value,
        sample_rate=48000,
    )
    adapter = worker.TermsAdapter(wrapper, mode, deps)
    assert adapter.infer(worker.CASES[0]["text"], voice="Trúc Ly") is wave
    call = calls[0]
    assert (
        len(calls) == 1
        and call["speaker_emb"] is speaker
        and call["ref_codes"] is codes
    )
    assert call["use_ref_codes"] is True and call["max_new_frames"] == len(raw)
    assert (
        call["temperature"],
        call["top_k"],
        call["top_p"],
        call["repetition_penalty"],
        call["repetition_window"],
    ) == (0.8, 25, 0.95, 1.2, 64)
    assert TARGET in call["phonemes"] and adapter.last_trace["term_mode"] == mode
    assert set(adapter.last_trace["voice_binding"]) == {
        "speaker_sha256",
        "reference_codes_sha256",
    }
    with pytest.raises(ValueError, match="unlisted"):
        adapter.infer("unlisted", voice="Trúc Ly")
