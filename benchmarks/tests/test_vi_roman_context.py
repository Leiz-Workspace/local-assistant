"""Test contextual reading expectations, immutable API boundaries and bounded original-policy audio verification."""

import asyncio
import base64
import copy
import json

import pytest

from benchmarks.scripts import vi_roman_context as context
from benchmarks.tests.test_vi_speech_review import MediaParser


def frontend_fixture():
    """Provide public independent normalized targets and no private SDK or model dependency."""
    entries = []
    for identity, text, expected, hint in context.CASES:
        entries.append(
            dict(
                id=identity,
                source_text=text,
                normalized=expected or text.lower(),
                chunks=[text.lower()],
                gaps=[],
                phonemes=["pˈaɪθən" if identity.startswith("python") else "vˈi"],
                frame_caps=[100],
                unknown_tokens=0,
            )
        )
    return dict(rows=entries, model_calls=0, python_reference="pˈaɪθən")


def test_fixed_denominator_and_roman_semantics_are_not_guessed_from_case():
    """Require ordinary vi, uppercase VI PHẠM and Roman VI to retain their distinct explicit expectations."""
    frontend = frontend_fixture()
    rows = context.packet(frontend)
    assert len(rows) == 10 and len({row["id"] for row in rows}) == 10
    assert {row["case"] for row in rows} == context.AUDIBLE
    for identity, wrong in [
        ("lower-word", "hành sáu sáu phạm này cần được kiểm tra."),
        ("upper-word", "sáu phạm là cụm từ tiếng việt."),
        ("roman-six", "chương vi có sáu mục."),
        ("roman-mixed", "chương vi nói về hành vi vi phạm."),
    ]:
        bad = copy.deepcopy(frontend)
        next(row for row in bad["rows"] if row["id"] == identity)["normalized"] = wrong
        with pytest.raises(ValueError, match="expected_reading"):
            context.packet(bad)


def test_probe_binding_rejects_source_drift_unknowns_and_inequivalent_python_tags():
    """Prevent a context claim or tag-only pseudo-fix from bypassing exact frontend provenance."""
    for kind in ("source", "unknown", "python"):
        bad = frontend_fixture()
        if kind == "source":
            bad["rows"][0]["source_text"] = "changed"
        elif kind == "unknown":
            bad["rows"][0]["unknown_tokens"] = 1
        else:
            next(row for row in bad["rows"] if row["id"] == "python-tag")[
                "phonemes"
            ] = ["different"]
        with pytest.raises(ValueError):
            context.packet(bad)
    compile(context.PROBE, "roman-probe", "exec")


def test_native_output_cannot_change_context_or_exceed_original_cap(tmp_path):
    """Require actual phoneme trace, genuine EOS, original frame allowance and exact chunk identity."""
    row = context.packet(frontend_fixture())[0]
    raw = b"native fixture"
    (tmp_path / f"{row['id']}-chunk-0.f32").write_bytes(raw)
    trace = {key: row["frontend"][key] for key in ("chunks", "gaps", "phonemes")}
    trace["native_chunk_sha256"] = [context.Q.lifecycle.sha(raw)]
    native = dict(
        prosody_trace=trace,
        chunks=[dict(frames=20, eos=True)],
        generation_complete=True,
    )
    context.verify_native(row, native, tmp_path)
    for kind in ("phones", "eos", "cap"):
        bad = copy.deepcopy(native)
        if kind == "phones":
            bad["prosody_trace"]["phonemes"] = ["wrong"]
        elif kind == "eos":
            bad["chunks"][0]["eos"] = False
        else:
            bad["chunks"][0]["frames"] = 101
        with pytest.raises(ValueError):
            context.verify_native(row, bad, tmp_path)


def test_review_preserves_missing_rows_and_labels_different_context_controls():
    """Publish exact bytes and all ten slots without fabricated quality claims or media capabilities."""
    rows = context.packet(frontend_fixture())
    audio = {rows[0]["id"]: b"current"}
    old = {"old": b"old"}
    page = context.render_review(rows, audio, old)
    parser = MediaParser()
    parser.feed(page)
    assert (
        len(parser.media) == 2
        and not parser.forbidden
        and page.count("Chưa có clip hoàn chỉnh: UNATTEMPTED") == 9
    )
    assert {base64.b64decode(row["src"].split(",", 1)[1]) for row in parser.media} == {
        b"current",
        b"old",
    }
    assert all(
        "autoplay" not in row and row["preload"] == "none" for row in parser.media
    )
    assert "khác ngữ cảnh" in page and "chưa phải bản sửa" in page
    with pytest.raises(ValueError):
        context.render_review(rows[:-1], {}, old)


@pytest.mark.asyncio
async def test_no_automatic_replay_of_retained_study(tmp_path):
    """Reject a retained marker before opening private inputs or loading the original model."""
    (tmp_path / "execution-freeze.json").write_text("{}")
    with pytest.raises(ValueError, match="already_attempted"):
        await context.run(tmp_path)


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [None, ValueError, asyncio.CancelledError])
async def test_ten_request_bound_first_failure_and_cancellation_join(
    tmp_path, monkeypatch, failure
):
    """Exercise the new controller with public observations and ensure failure/cancellation never dispatch another call."""
    project = tmp_path / "project"
    evidence = project / "docs/evidence"
    evidence.mkdir(parents=True)
    (evidence / "d74-roman-context-authorization.json").write_text(
        '{"authorized":true}'
    )
    hashes = {}
    for name in context.SOURCES:
        path = project / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('"""Fixture."""\n')
        hashes[name] = context.Q.assets.digest(path)
    (tmp_path / "probe/native").mkdir(parents=True)
    (tmp_path / "probe/native/frontend.json").write_text(json.dumps(frontend_fixture()))
    (tmp_path / "software-verification.json").write_text(
        json.dumps(dict(status="PASS", source_sha256=hashes))
    )
    monkeypatch.setattr(context.Q.assets, "PROJECT", project)
    monkeypatch.setattr(context, "verify_previous", lambda: None)
    monkeypatch.setattr(context.Q.lifecycle, "prepared_integrity", lambda root: None)
    monkeypatch.setattr(context.Q.lifecycle, "verify_originals", lambda: {"fixture": 1})
    monkeypatch.setattr(context.Q.lifecycle, "local_state", lambda: {"native_pids": []})
    monkeypatch.setattr(context, "verify_native", lambda *args: None)
    calls = []
    closed = []

    class Worker:
        """Supply no-model public requests and retained lifecycle signals."""

        def __init__(self, *args):
            """Bind an initially clean fake worker."""
            self.failure = None

        async def start(self):
            """Represent successful startup without a real process."""
            return self

        async def call(self, message):
            """Record one first attempt and optionally fail or cancel it."""
            calls.append(message)
            if failure:
                self.failure = "fixture"
                raise failure("fixture")
            return dict(chunks=[{}])

        async def close(self, force):
            """Retain explicit cleanup after success, error or cancellation."""
            closed.append(True)

    monkeypatch.setattr(context.Q, "QualityWorker", Worker)
    result = await context.run(tmp_path)
    assert result["tts_attempts"] == len(calls) == (1 if failure else 10)
    assert result["completed_inner_chunks"] == (0 if failure else 10)
    assert result["unattempted"] == (9 if failure else 0)
    assert result["status"] == (
        "STOPPED_NO_RETRY"
        if failure
        else "CONTEXT_CONTROLS_COMPLETE_ACOUSTIC_UNVERIFIED"
    )
    assert result["retries"] == 0 and result["baseline_restored"] and closed == [True]
    assert all("API" not in row["text"] for row in calls)
