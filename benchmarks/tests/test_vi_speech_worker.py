"""Test isolated quality profile configuration and normalization probes without model execution."""

from types import SimpleNamespace

import pytest

from benchmarks.scripts.vi_speech_worker import configure_runtime, probe_rows


def test_original_runtime_arguments_and_profile_are_explicit():
    """Forward identical synthesis inputs and change only the declared chunk argument."""
    calls = []

    def infer(*args, **kwargs):
        """Record exact calls without generating any waveform."""
        calls.append((args, kwargs))
        return marker

    def factory(candidate):
        """Construct an unmodified fake CPU runtime for profile wiring checks."""
        assert candidate == "turbo"
        return SimpleNamespace(
            engine=SimpleNamespace(infer=infer), execution=dict(device="cpu")
        )

    marker = object()
    runtime = configure_runtime("reading", factory)
    assert runtime.engine.infer("text", voice="Trúc Ly") is marker
    assert calls == [(("text",), dict(voice="Trúc Ly", max_chars=256))]
    assert runtime.execution["sampling_unchanged"] is True
    with pytest.raises(ValueError):
        configure_runtime("unreviewed", factory)


def test_model_free_probe_tracks_raw_and_rendered_text():
    """Require three labelled rows per source without constructing an inference runtime."""

    class Normalizer:
        """Expose explicit punctuation normalization flags for a public fixture."""

        def normalize(self, text, punc_norm):
            """Return the supplied text while asserting preservation of punctuation."""
            assert punc_norm is False
            return text

    def chunker(text, max_chars):
        """Keep fixture text unmodified and expose the supported argument."""
        assert max_chars in {64, 256}
        return [text], []

    rows = probe_rows(
        ["Hẹn lúc 09:15, học Python và API."], Normalizer(), chunker, lambda text: text
    )
    assert len(rows) == 3 and rows[0]["profile"] == "raw"
    assert "09:15" in rows[0]["speech_text"]
    assert "chín giờ mười lăm phút" in rows[1]["speech_text"]
    assert "ây pi ai" in rows[1]["speech_text"]
    assert rows[2]["max_chars"] == 256
    with pytest.raises(ValueError):
        probe_rows([], Normalizer(), chunker, lambda text: text)


def test_question_profile_uses_explicit_adapter_not_global_sdk_patching():
    """Bind the additional phoneme route only for the declared prosody profile."""
    marker = object()
    wrapper = SimpleNamespace(infer=lambda *args, **kwargs: None)

    class Adapter:
        """Provide a distinct callable for the experimental profile."""

        def __init__(self, supplied):
            """Require the same already loaded wrapper without replacing its weights."""
            assert supplied is wrapper

        def infer(self, text, *, voice):
            """Return an observable adapter result without native execution."""
            return marker

    runtime = configure_runtime(
        "clauses",
        lambda candidate: SimpleNamespace(engine=wrapper, execution={}),
        Adapter,
    )
    assert runtime.engine.infer("question?", voice="Trúc Ly") is marker
    assert runtime.execution["question_preserving_phoneme_api"] is True
    assert runtime.execution["original_text_normalization"] is False
