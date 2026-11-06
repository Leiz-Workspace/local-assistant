"""Test fixed same-text controls, provenance failures, replay exclusion and truthful local media publication."""

import base64
import copy
import json

import pytest

from benchmarks.scripts import vi_api_stress_trial as trial
from benchmarks.tests.test_vi_speech_review import MediaParser


def fixture_rows():
    """Build independent public one/two-chunk baselines for all four required voice/case pairs."""
    rows = []
    frontend = []
    for case, text in trial.CASES:
        before = (
            ["date.", trial.SOURCE + "?"]
            if case == "english-04"
            else [trial.SOURCE + "?"]
        )
        chunks = ["Date.", "API?"] if len(before) == 2 else ["API?"]
        traces = [
            dict(
                before=ph,
                after=ph.replace(trial.SOURCE, trial.TARGET),
                replacements=int(trial.SOURCE in ph),
                frame_cap=100,
            )
            for ph in before
        ]
        entry = dict(
            speech_text=text,
            chunks=chunks,
            gaps=["sentence"] * (len(chunks) - 1),
            api_stress=traces,
        )
        frontend.append(entry)
        for label, voice in trial.Q.VOICES:
            rows.append(
                dict(
                    id=f"{label}-{case}",
                    case=case,
                    voice=voice,
                    source_text=text,
                    speech_text=text,
                    status="UNATTEMPTED",
                    baseline=dict(
                        prosody_trace=dict(
                            chunks=chunks,
                            gaps=entry["gaps"],
                            phonemes=before,
                            native_chunk_sha256=["old"] * len(chunks),
                        )
                    ),
                )
            )
    return rows, dict(rows=frontend, model_calls=0)


def test_frontend_rejects_context_chunk_and_nonterm_mutation():
    """Bind the unchanged earlier text path and reject unrelated phoneme changes before loading."""
    rows, front = fixture_rows()
    trial.bind_frontend(rows, front)
    for mutate in ("chunks", "phones", "edit"):
        bad = copy.deepcopy(front)
        if mutate == "chunks":
            bad["rows"][0]["chunks"] = ["changed"]
        elif mutate == "phones":
            bad["rows"][0]["api_stress"][0]["before"] = "wrong"
        else:
            bad["rows"][0]["api_stress"][0]["after"] = "unrelated"
        with pytest.raises(ValueError):
            trial.bind_frontend(copy.deepcopy(rows), bad)


def test_native_requires_original_date_audio_and_frozen_term_trace(tmp_path):
    """Reject changes in the otherwise identical first date chunk and actual phoneme output."""
    rows, front = fixture_rows()
    trial.bind_frontend(rows, front)
    row = next(row for row in rows if row["case"] == "english-04")
    hashes = []
    for index, raw in enumerate((b"date", b"api")):
        (tmp_path / f"{row['id']}-chunk-{index}.f32").write_bytes(raw)
        hashes.append(trial.Q.lifecycle.sha(raw))
    row["baseline"]["prosody_trace"]["native_chunk_sha256"][0] = hashes[0]
    native = dict(
        chunks=[{}, {}],
        prosody_trace=dict(
            row["frontend"],
            phonemes=[r["after"] for r in row["frontend"]["api_stress"]],
            native_chunk_sha256=hashes,
        ),
    )
    trial.verify_native(row, native, tmp_path)
    row["baseline"]["prosody_trace"]["native_chunk_sha256"][0] = "changed"
    with pytest.raises(ValueError, match="unchanged_date_audio"):
        trial.verify_native(row, native, tmp_path)


def test_command_retains_cpu_isolation_and_no_weights_in_probe(tmp_path):
    """Ensure the new entry point cannot acquire network or extra assets through the model-free probe."""
    out = tmp_path / "out"
    out.mkdir(mode=0o700)
    for probe in (False, True):
        args = trial.command(out, probe)
        assert "--unshare-all" in args and "--share-net" not in args
        assert "--as=8589934592" in args and args[-1] == (
            "--probe" if probe else "api-stress"
        )
        if probe:
            mounts = {
                args[index + 2]
                for index, value in enumerate(args)
                if value == "--ro-bind"
            }
            assert "/model" not in mounts and "/hf/hub" not in mounts


def test_review_keeps_all_old_baselines_and_missing_slots():
    """Show exact retained bytes and missing candidates without capture, scripts, autoplay or hidden network."""
    rows, _ = fixture_rows()
    old = {row["id"]: row["id"].encode() for row in rows}
    page = trial.render_review(rows, {}, old)
    parser = MediaParser()
    parser.feed(page)
    assert (
        len(parser.media) == 4
        and not parser.forbidden
        and page.count("Chưa có clip hoàn chỉnh: UNATTEMPTED") == 4
    )
    assert {
        base64.b64decode(row["src"].split(",", 1)[1]) for row in parser.media
    } == set(old.values())
    assert all(
        "autoplay" not in row and row["preload"] == "none" for row in parser.media
    )
    with pytest.raises(ValueError):
        trial.render_review(rows[:-1], {}, old)


@pytest.mark.asyncio
async def test_retained_marker_prevents_a_second_native_attempt(tmp_path):
    """Refuse reuse of the study root before reading private artifacts or loading any model."""
    (tmp_path / "execution-freeze.json").write_text("{}")
    with pytest.raises(ValueError, match="already_attempted"):
        await trial.run(tmp_path)


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [False, True])
async def test_controller_fixed_budget_failure_stop_and_join(
    tmp_path, monkeypatch, failure
):
    """Exercise actual controller first-failure, six-chunk ceiling and cleanup without model assets."""
    rows, front = fixture_rows()
    project = tmp_path / "project"
    evidence = project / "docs/evidence"
    evidence.mkdir(parents=True)
    (evidence / "d74-api-stress-authorization.json").write_text('{"authorized":true}')
    hashes = {}
    for name in trial.SOURCES:
        path = project / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('"""Fixture."""\n')
        hashes[name] = trial.Q.assets.digest(path)
    (tmp_path / "probe/native").mkdir(parents=True)
    (tmp_path / "probe/native/frontend.json").write_text(json.dumps(front))
    (tmp_path / "software-verification.json").write_text(
        json.dumps(dict(status="PASS", source_sha256=hashes))
    )
    monkeypatch.setattr(trial.Q.assets, "PROJECT", project)
    monkeypatch.setattr(trial, "verify_previous", lambda: None)
    monkeypatch.setattr(trial.Q.lifecycle, "prepared_integrity", lambda root: None)
    monkeypatch.setattr(trial.Q.lifecycle, "verify_originals", lambda: {"fixture": 1})
    monkeypatch.setattr(trial.Q.lifecycle, "local_state", lambda: {"native_pids": []})
    monkeypatch.setattr(trial, "packet", lambda: copy.deepcopy(rows))
    monkeypatch.setattr(trial, "verify_native", lambda *args: None)
    calls = []
    closed = []

    class Worker:
        """Return bounded public observations and retain joined fake lifecycle coverage."""

        def __init__(self, *args):
            """Initialize a failure signal without any process or model."""
            self.failure = None

        async def start(self):
            """Represent a successful isolated readiness boundary."""
            return self

        async def call(self, message):
            """Record one attempt and optionally fail before further requests."""
            calls.append(message)
            if failure:
                self.failure = "fixture"
                raise ValueError("fixture")
            return dict(chunks=[{}] * (1 if message["id"].endswith("01") else 2))

        async def close(self, force):
            """Record explicit retirement of the only owned worker."""
            closed.append(True)

    monkeypatch.setattr(trial, "StressWorker", Worker)
    result = await trial.run(tmp_path)
    assert len(calls) == result["tts_attempts"] == (1 if failure else 4)
    assert result["completed_inner_chunks"] == (0 if failure else 6)
    assert result["unattempted"] == (3 if failure else 0)
    assert result["status"] == (
        "STOPPED_NO_RETRY"
        if failure
        else "STRESS_CANDIDATES_COMPLETE_QUALITY_UNVERIFIED"
    )
    assert closed == [True] and result["baseline_restored"] and result["retries"] == 0
