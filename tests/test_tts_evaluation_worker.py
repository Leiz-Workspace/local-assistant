"""Exercise TTS capability boundaries, untouched generation forwarding and first-attempt evidence without downloading or loading any neural model."""

from types import SimpleNamespace

import numpy as np
import pytest

from scripts.tts_evaluation import cases, worker_request
from scripts.tts_evaluation_worker import (
    QWEN_OPTIONS,
    GenerationObserver,
    observe,
    validate_request,
)
from scripts.tts_waveform import OutputStore


@pytest.mark.parametrize(
    "candidate,count", [("qwen3-tts-0.6b", 18), ("piper-en", 6), ("piper-vi", 6)]
)
def test_fixed_family_coverage_and_no_outcome_dependent_retry(candidate, count):
    """Keep each explicit unsupported-language attempt and Auto diagnostic predeclared with distinct identities."""
    request = worker_request(candidate, "predict", dict(cases=cases()))
    assert len(request["cases"]) == count
    assert len({row["id"] for row in request["cases"]}) == count
    validate_request(request)
    if candidate.startswith("qwen"):
        assert sum(row["variant"] == "auto_diagnostic" for row in request["cases"]) == 6
        assert len({row["text"] for row in request["cases"]}) == 12


@pytest.mark.parametrize(
    "field,value",
    [("mode", "retry"), ("candidate", "qwen-1.7b"), ("cases", []), ("voice", "other")],
)
def test_unsupported_request_scope_is_rejected(field, value):
    """Refuse arbitrary SDK/model or synthesis overrides before any runtime import."""
    request = worker_request("piper-en", "smoke", {})
    request[field] = value
    with pytest.raises(ValueError):
        validate_request(request)


@pytest.mark.parametrize(
    "field,value",
    [
        ("id", "../../escape"),
        ("text", "x" * 161),
        ("text", "line\nbreak"),
        ("text", ""),
        ("language", "ar"),
        ("variant", "fallback"),
        ("filename", "foreign"),
    ],
)
def test_case_injection_or_unbounded_text_is_rejected(field, value):
    """Keep the request free of filesystem references, unsupported helper languages and unbounded text."""
    request = worker_request("piper-en", "smoke", {})
    request["cases"][0][field] = value
    with pytest.raises(ValueError):
        validate_request(request)


def test_duplicate_and_missing_qwen_language_coverage_is_rejected():
    """Do not count duplicated easy cases or English-only output as complete bilingual coverage."""
    request = worker_request("qwen3-tts-0.6b", "predict", dict(cases=cases()))
    request["cases"][-1] = dict(request["cases"][0])
    with pytest.raises(ValueError):
        validate_request(request)
    request["cases"][-1]["id"] = "unique-but-wrong"
    with pytest.raises(ValueError):
        validate_request(request)


class Scalar:
    """Provide the minimal original tensor scalar interface to test observation without a Torch dependency."""

    def __init__(self, value):
        """Retain one authored token value."""
        self.value = value

    def item(self):
        """Return the authored scalar exactly."""
        return self.value


class Sequence:
    """Expose a fixed one-row generation shape and final token for transparent wrapper tests."""

    shape = (1, 7)

    def __init__(self, final):
        """Retain an explicit EOS or capped non-EOS token."""
        self.final = final

    def __getitem__(self, key):
        """Require the observer to inspect only the last genuine generated token."""
        assert key == (0, -1)
        return Scalar(self.final)


@pytest.mark.parametrize("final,complete", [(99, True), (98, False)])
def test_generation_observer_preserves_original_objects_arguments_and_eos(
    final, complete
):
    """Protect against duplicate return_dict flags and treating token-budget exhaustion as complete speech."""
    inner_result = SimpleNamespace(sequences=Sequence(final))
    outer_result = ([np.zeros((6, 16), dtype=np.int64)], ["hidden"])
    calls = []

    def inner(*args, **kwargs):
        """Record exact forwarded arguments and return the original generated object."""
        calls.append((args, kwargs))
        return inner_result

    def outer(*args, **kwargs):
        """Return original codec and hidden-state containers unchanged."""
        calls.append((args, kwargs))
        return outer_result

    engine = SimpleNamespace(
        model=SimpleNamespace(
            talker=SimpleNamespace(generate=inner),
            generate=outer,
            config=SimpleNamespace(
                talker_config=SimpleNamespace(codec_eos_token_id=99)
            ),
        )
    )
    observer = GenerationObserver(engine)
    assert (
        engine.model.talker.generate("token", return_dict_in_generate=True)
        is inner_result
    )
    assert calls[-1] == (("token",), dict(return_dict_in_generate=True))
    assert engine.model.generate(max_new_tokens=192) is outer_result
    assert observer.metadata()["generation_complete"] is complete
    assert observer.metadata()["codec_frames"] == [6]
    observer.reset()
    assert not observer.metadata()["generation_complete"]
    assert QWEN_OPTIONS["do_sample"] is True
    assert "return_dict_in_generate" not in QWEN_OPTIONS


@pytest.mark.parametrize(
    "message,status",
    [
        ("Unsupported languages: ['Vietnamese']", "unsupported_language"),
        ("arbitrary failure", "error"),
    ],
)
def test_real_sdk_capability_refusal_is_retained_once(tmp_path, message, status):
    """Classify only the genuine explicit Vietnamese language refusal without synthesizing placeholder audio or retrying Auto."""
    calls = []

    def fail(case):
        """Raise one original-style SDK exception and count attempts."""
        calls.append(case)
        raise ValueError(message)

    runtime = SimpleNamespace(candidate="qwen3-tts-0.6b", synthesize=fail)
    case = dict(id="vi-01", text="Xin chào.", language="vi", variant="explicit")
    result = observe(runtime, case, OutputStore(tmp_path))
    assert result["status"] == status and len(calls) == 1
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize(
    "complete,finite,status",
    [
        (True, True, "ok"),
        (False, True, "invalid_or_incomplete_audio"),
        (True, False, "invalid_or_incomplete_audio"),
    ],
)
def test_first_native_output_and_failed_audio_remain_unchanged(
    tmp_path, complete, finite, status
):
    """Persist complete raw bits even when EOS or finite-signal acceptance fails, with no repair or resynthesis."""
    values = np.array([0.1, 0.2 if finite else np.nan], dtype="<f4")

    def synthesize(case):
        """Return one authored native SDK waveform and first timing."""
        return (
            values,
            24000,
            dict(
                generation_complete=complete,
                first_available_audio_seconds=0.1,
                full_call_seconds=0.1,
                chunks=1,
            ),
        )

    result = observe(
        SimpleNamespace(candidate="qwen3-tts-0.6b", synthesize=synthesize),
        dict(id="en-01", text="Hello.", language="en", variant="explicit"),
        OutputStore(tmp_path),
    )
    assert result["status"] == status
    assert (tmp_path / "en-01.f32").read_bytes() == values.tobytes()
