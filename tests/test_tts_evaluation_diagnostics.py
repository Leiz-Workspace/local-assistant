"""Validate reference-blind diagnostic authority and authored-text ASR proxy scope without fabricating independent speech or listening ratings."""

import pytest

from scripts.tts_audio_diagnostics import validate_request
from scripts.tts_evaluation_diagnostics import (
    diagnostic_identity,
    diagnostic_namespace,
    proxy_metrics,
)


@pytest.mark.parametrize("candidate", ["qwen3-tts-0.6b", "piper-en", "piper-vi"])
def test_actual_pinned_candidate_names_fit_safe_diagnostic_leaf_names(candidate):
    """Cover the genuine decimal Qwen model ID before preparing native copies, without widening path permissions."""
    identity = diagnostic_identity(candidate, "qualification-en")
    validate_request(
        dict(
            cases=[
                dict(
                    id=identity,
                    filename=identity + ".f32",
                    sample_rate=24000,
                    sample_count=48000,
                    waveform_sha256="a" * 64,
                )
            ]
        )
    )
    assert "." not in identity


def test_diagnostic_namespace_exposes_no_model_reference_or_credentials(tmp_path):
    """Mount only selected native inputs/private outputs and DSP sources with finite CPU/memory and no model authority."""
    output = tmp_path / "output"
    output.mkdir(mode=0o700)
    command = diagnostic_namespace(tmp_path / "samples", output)
    assert command.count("--bind") == 1
    assert "/model" not in command and "/sources" not in command
    assert "--unshare-all" in command and "--as=3221225472" in command
    assert not any(
        "corpus" in item or "freeze.json" in item or "d68" in item for item in command
    )


def test_proxy_preserves_d68_text_normalization_and_declares_authored_bias_scope():
    """Compute exact accent-preserving error rates while keeping VI-Auto distinct and naturalness explicitly unscored."""
    references = [
        dict(
            id="one",
            candidate="qwen",
            language="vi",
            variant="auto_diagnostic",
            authored_text="Xin chào.",
        ),
        dict(
            id="two",
            candidate="piper",
            language="en",
            variant="explicit",
            authored_text="Blue book.",
        ),
    ]
    predictions = [
        dict(id="one", status="ok", text="xin CHÀO!"),
        dict(id="two", status="ok", text="blue cook"),
    ]
    result = proxy_metrics(references, predictions)
    assert result["complete"]
    assert result["groups"]["qwen/vi/auto_diagnostic"]["WER"] == 0
    assert result["groups"]["piper/en/explicit"]["WER"] == 0.5
    assert result["naturalness_score"] is None and result["model_selected"] is None


def test_missing_or_failed_proxy_predictions_never_become_zero_error_success():
    """Retain incomplete coverage independently from observed transcript error rates."""
    references = [
        dict(
            id="one",
            candidate="qwen",
            language="en",
            variant="explicit",
            authored_text="Hello.",
        )
    ]
    assert proxy_metrics(references, [])["complete"] is False
    assert (
        proxy_metrics(references, [dict(id="one", status="error")])["complete"] is False
    )


@pytest.mark.parametrize(
    "kind", ["duplicate_reference", "duplicate_prediction", "foreign_prediction"]
)
def test_proxy_rejects_duplicate_or_foreign_evidence(kind):
    """Prevent double counting repeated successes or mixing transcripts from an unrelated native waveform."""
    references = [
        dict(
            id="one",
            candidate="qwen",
            language="en",
            variant="explicit",
            authored_text="Hello.",
        )
    ]
    predictions = [dict(id="one", status="ok", text="Hello.")]
    if kind == "duplicate_reference":
        references *= 2
    elif kind == "duplicate_prediction":
        predictions *= 2
    else:
        predictions[0]["id"] = "foreign"
    with pytest.raises(ValueError):
        proxy_metrics(references, predictions)
