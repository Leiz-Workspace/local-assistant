"""Test XI word/numeral context expectations and the bounded unchanged-policy study lifecycle."""

import asyncio
import base64
import copy
import json

import pytest

from benchmarks.scripts import vi_xi_context as xi
from benchmarks.tests.test_vi_speech_review import MediaParser


def frontend_fixture():
    """Create public normalized context controls without any private model or SDK files."""
    return dict(
        model_calls=0,
        rows=[
            dict(
                id=identity,
                source_text=text,
                normalized=expected or text.lower(),
                unknown_tokens=0,
                chunks=[text.lower()],
                gaps=[],
                phonemes=["fixture"],
                frame_caps=[100],
            )
            for identity, text, expected, hint in xi.CASES
        ],
    )


def test_numerals_and_vietnamese_words_require_distinct_context_targets():
    """Reject eleven mang and literal xi in an explicit Roman chapter before native admission."""
    rows = xi.packet(frontend_fixture())
    assert len(rows) == 6 and len({r["id"] for r in rows}) == 6
    for identity, wrong in [
        ("xi-word", "mười một măng được dùng để xây nhà."),
        ("xi-uppercase", "mười một măng được dùng để xây nhà."),
        ("roman-eleven", "chương xi có mười một mục."),
        ("xi-mixed", "chương xi nói về xi măng và cách sử dụng."),
        ("xi-uppercase-mixed", "chương mười một nói về mười một măng."),
    ]:
        bad = frontend_fixture()
        next(r for r in bad["rows"] if r["id"] == identity)["normalized"] = wrong
        with pytest.raises(ValueError, match="expected_reading"):
            xi.packet(bad)


def test_ambiguous_controls_are_observations_and_source_drift_is_rejected():
    """Keep undefined identifier readings unscored without weakening input provenance or token checks."""
    front = frontend_fixture()
    for row in front["rows"]:
        if row["id"] in {"identifier", "bare", "noncanonical", "lower-identifier"}:
            row["normalized"] = "observation"
    assert len(xi.packet(front)) == 6
    for field, value in [("source_text", "changed"), ("unknown_tokens", 1)]:
        bad = copy.deepcopy(front)
        bad["rows"][0][field] = value
        with pytest.raises(ValueError):
            xi.packet(bad)


def test_review_keeps_all_slots_exact_bytes_and_no_capture_or_script():
    """Show missing controls honestly and embed only supplied original audio payloads."""
    rows = xi.packet(frontend_fixture())
    audio = {rows[0]["id"]: b"native"}
    page = xi.render_review(rows, audio)
    parser = MediaParser()
    parser.feed(page)
    assert (
        len(parser.media) == 1
        and not parser.forbidden
        and page.count("Chưa có clip hoàn chỉnh: UNATTEMPTED") == 5
    )
    assert base64.b64decode(parser.media[0]["src"].split(",", 1)[1]) == b"native"
    assert "autoplay" not in parser.media[0] and parser.media[0]["preload"] == "none"
    with pytest.raises(ValueError):
        xi.render_review(rows[:-1], audio)


@pytest.mark.asyncio
async def test_no_replay_after_retained_freeze(tmp_path):
    """Refuse a consumed study before opening private state or creating a model worker."""
    (tmp_path / "execution-freeze.json").write_text("{}")
    with pytest.raises(ValueError, match="already_attempted"):
        await xi.run(tmp_path)


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [None, ValueError, asyncio.CancelledError])
async def test_six_first_attempts_first_failure_and_cancellation_join(
    tmp_path, monkeypatch, failure
):
    """Exercise the real controller without models and preserve every request denominator and cleanup boundary."""
    project = tmp_path / "project"
    evidence = project / "docs/evidence"
    evidence.mkdir(parents=True)
    (evidence / "d74-xi-context-authorization.json").write_text('{"authorized":true}')
    hashes = {}
    for name in xi.SOURCES:
        path = project / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('"""Fixture."""\n')
        hashes[name] = xi.Q.assets.digest(path)
    (tmp_path / "probe/native").mkdir(parents=True)
    (tmp_path / "probe/native/frontend.json").write_text(json.dumps(frontend_fixture()))
    (tmp_path / "software-verification.json").write_text(
        json.dumps(dict(status="PASS", source_sha256=hashes))
    )
    monkeypatch.setattr(xi.Q.assets, "PROJECT", project)
    monkeypatch.setattr(xi, "verify_previous", lambda: None)
    monkeypatch.setattr(xi.Q.lifecycle, "prepared_integrity", lambda root: None)
    monkeypatch.setattr(xi.Q.lifecycle, "verify_originals", lambda: {"fixture": 1})
    monkeypatch.setattr(xi.Q.lifecycle, "local_state", lambda: {"native_pids": []})
    monkeypatch.setattr(xi.previous, "verify_native", lambda *args: None)
    calls = []
    closed = []

    class Worker:
        """Provide public request observations and lifecycle receipts without native processes."""

        def __init__(self, *args):
            """Bind a clean fake failure signal."""
            self.failure = None

        async def start(self):
            """Represent successful original-worker readiness."""
            return self

        async def call(self, message):
            """Record exactly one attempt and optionally stop it before any following request."""
            calls.append(message)
            if failure:
                self.failure = "fixture"
                raise failure("fixture")
            return dict(chunks=[{}])

        async def close(self, force):
            """Record joined cleanup for success, error and cancellation."""
            closed.append(True)

    monkeypatch.setattr(xi.Q, "QualityWorker", Worker)
    result = await xi.run(tmp_path)
    assert len(calls) == result["tts_attempts"] == (1 if failure else 6)
    assert result["completed_inner_chunks"] == (0 if failure else 6) and result[
        "unattempted"
    ] == (5 if failure else 0)
    assert result["status"] == (
        "STOPPED_NO_RETRY" if failure else "XI_CONTROLS_COMPLETE_ACOUSTIC_UNVERIFIED"
    )
    assert result["baseline_restored"] and result["retries"] == 0 and closed == [True]
