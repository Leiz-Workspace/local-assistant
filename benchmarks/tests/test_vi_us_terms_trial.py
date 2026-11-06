"""Test planned reuse, unique native budgets, paired voice integrity and truthful local before/after media."""

import asyncio
import base64
import copy
import json

import pytest

from benchmarks.scripts import vi_us_terms_trial as trial
from benchmarks.scripts.vi_us_terms_worker import CASES, TERMS, CONTROLS
from benchmarks.scripts.vi_api_stress_worker import SOURCE
from benchmarks.tests.test_vi_speech_review import MediaParser


def frontend_fixture():
    """Create public paired-phone fixtures with the same explicit identical-control decisions as the protocol."""
    entries = []
    for case in CASES:
        phones = (
            "prefix "
            + " ".join(
                [TERMS[t][0] for t in case["terms"]]
                + [CONTROLS[t] for t in case["controls"]]
            )
            + (" " + SOURCE if "API" in case["text"] else "")
            + "."
        )
        entries.append(
            dict(
                id=case["id"],
                source_text=case["text"],
                chunks=[case["text"]],
                gaps=[],
                phone_plan=trial.phone_plan(phones, case, lambda ph: 100),
                unknown_tokens=0,
            )
        )
    return dict(rows=entries, model_calls=0)


def test_exact_pair_reuse_plan_rejects_source_term_and_cap_drift():
    """Bind twelve pairs without inventing extra candidate calls for unchanged controls."""
    front = frontend_fixture()
    rows = trial.packet(front)
    assert (
        len(rows) == 12
        and sum(r["us"]["status"] == "SHARED_CONTROL_PENDING" for r in rows) == 4
    )
    for field, value in [("source_text", "wrong"), ("unknown_tokens", 1)]:
        bad = copy.deepcopy(front)
        bad["rows"][0][field] = value
        with pytest.raises(ValueError):
            trial.packet(bad)
    bad = copy.deepcopy(front)
    bad["rows"][0]["phone_plan"]["us"] = "unrelated"
    with pytest.raises((ValueError, KeyError)):
        trial.packet(bad)
    bad = copy.deepcopy(front)
    bad["rows"][0]["phone_plan"]["shared_cap"] = 101
    with pytest.raises(ValueError):
        trial.packet(bad)


def test_identical_controls_share_only_an_existing_complete_baseline():
    """Retain missing controls until actual baseline completion instead of fabricating successful audio."""
    rows = trial.packet(frontend_fixture())
    trial.share_controls(rows)
    assert sum(r["us"]["status"] == "SHARED_CONTROL_COMPLETE" for r in rows) == 0
    for row in rows:
        if row["frontend"]["phone_plan"]["same_input"]:
            row["baseline"].update(status="NATIVE_COMPLETE", native={"fixture": True})
    trial.share_controls(rows)
    assert sum(r["us"]["status"] == "SHARED_CONTROL_COMPLETE" for r in rows) == 4
    assert all(
        r["us"]["native"] == r["baseline"]["native"]
        for r in rows
        if r["us"]["status"] == "SHARED_CONTROL_COMPLETE"
    )


def test_new_pair_voice_binding_drift_fails(tmp_path, monkeypatch):
    """Reject an apparent word improvement that secretly changes the speaker or reference codes."""
    row = next(r for r in trial.packet(frontend_fixture()) if r["case"] == "github")
    row["baseline"].update(
        status="NATIVE_COMPLETE",
        native=dict(
            prosody_trace=dict(
                voice_binding=dict(speaker_sha256="s", reference_codes_sha256="r")
            )
        ),
    )
    monkeypatch.setattr(trial.previous.previous, "verify_native", lambda *args: None)
    native = dict(
        prosody_trace=dict(
            us_terms=row["frontend"]["phone_plan"],
            term_mode="us",
            voice_binding=dict(speaker_sha256="s", reference_codes_sha256="r"),
        )
    )
    trial.verify_native(row, "us", native, tmp_path, "fixture")
    native["prosody_trace"]["voice_binding"]["speaker_sha256"] = "other"
    with pytest.raises(ValueError, match="pair_voice_changed"):
        trial.verify_native(row, "us", native, tmp_path, "fixture")


def test_media_shows_retained_and_shared_controls_without_duplicate_players():
    """Embed authentic bytes, retain missing slots and keep smaller voice-specific pages script-free."""
    rows = trial.packet(frontend_fixture())
    audio = {}
    for row in rows:
        row["baseline"]["status"] = "NATIVE_COMPLETE"
        audio[(row["id"], "baseline")] = (row["id"] + "base").encode()
        if row["us"]["status"] == "UNATTEMPTED":
            row["us"]["status"] = "NATIVE_COMPLETE"
            audio[(row["id"], "us")] = (row["id"] + "us").encode()
    trial.share_controls(rows)
    page = trial.render_review(rows, audio)
    parser = MediaParser()
    parser.feed(page)
    assert (
        len(parser.media) == 20
        and not parser.forbidden
        and page.count("dùng chung clip bên trái") == 4
    )
    assert {base64.b64decode(r["src"].split(",", 1)[1]) for r in parser.media} == set(
        audio.values()
    )
    for _, voice in trial.Q.VOICES:
        parser = MediaParser()
        parser.feed(trial.render_review(rows, audio, voice))
        assert len(parser.media) == 10 and not parser.forbidden
    with pytest.raises(ValueError):
        trial.render_review(rows[:-1], audio)
    assert (
        trial.render_review(trial.packet(frontend_fixture()), {}).count(
            "Chưa có clip hoàn chỉnh"
        )
        == 24
    )


def test_original_namespace_remains_offline_and_probe_has_no_weight_mount(tmp_path):
    """Expose only the new worker plus frozen API helper under original process and filesystem guards."""
    out = tmp_path / "out"
    out.mkdir(mode=0o700)
    for probe in (False, True):
        args = trial.command(out, "us", probe)
        mounts = {args[i + 2] for i, v in enumerate(args) if v == "--ro-bind"}
        assert (
            "--unshare-all" in args
            and "--as=8589934592" in args
            and "--share-net" not in args
        )
        assert "/app/benchmarks/scripts/vi_api_stress_worker.py" in mounts
        if probe:
            assert "/model" not in mounts and "/hf/hub" not in mounts


@pytest.mark.asyncio
async def test_no_repeat_after_retained_marker(tmp_path):
    """Reject consumed scope before private inputs or model creation."""
    (tmp_path / "execution-freeze.json").write_text("{}")
    with pytest.raises(ValueError, match="already_attempted"):
        await trial.run(tmp_path)


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [None, ValueError, asyncio.CancelledError])
async def test_unique_request_accounting_reuse_first_failure_and_join(
    tmp_path, monkeypatch, failure
):
    """Run the paired controller with public no-model observations and exact retained/shared accounting."""
    project = tmp_path / "project"
    evidence = project / "docs/evidence"
    evidence.mkdir(parents=True)
    (evidence / "d74-us-terms-authorization.json").write_text('{"authorized":true}')
    hashes = {}
    for name in trial.SOURCES:
        p = project / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text('"""Fixture."""\n')
        hashes[name] = trial.Q.assets.digest(p)
    (tmp_path / "probe/native").mkdir(parents=True)
    (tmp_path / "probe/native/frontend.json").write_text(json.dumps(frontend_fixture()))
    (tmp_path / "software-verification.json").write_text(
        json.dumps(dict(status="PASS", source_sha256=hashes))
    )
    monkeypatch.setattr(trial.Q.assets, "PROJECT", project)
    monkeypatch.setattr(trial, "verify_previous", lambda: None)
    monkeypatch.setattr(trial.Q.lifecycle, "prepared_integrity", lambda root: None)
    monkeypatch.setattr(trial.Q.lifecycle, "verify_originals", lambda: {"fixture": 1})
    monkeypatch.setattr(trial.Q.lifecycle, "local_state", lambda: {"native_pids": []})
    monkeypatch.setattr(trial, "verify_native", lambda *args: None)

    def retained(rows):
        """Represent four exact old Python baselines without generating or accessing private audio."""
        for row in rows:
            if row["case"].startswith("python"):
                row["baseline"]["status"] = "RETAINED_COMPLETE"

    monkeypatch.setattr(trial, "bind_retained", retained)
    calls = []
    closed = []

    class Worker:
        """Return public first-attempt responses and retain role-specific cleanup."""

        def __init__(self, role, *args):
            """Bind a role without a real model/process."""
            self.role, self.failure = role, None

        async def start(self):
            """Represent readiness without any native call."""
            return self

        async def call(self, message):
            """Record a unique request or stop at its first error/cancellation."""
            calls.append((self.role, message))
            if failure:
                self.failure = "fixture"
                raise failure("fixture")
            return dict(chunks=[{}])

        async def close(self, force):
            """Record joined role retirement for every created worker."""
            closed.append(self.role)

    monkeypatch.setattr(trial, "TermsWorker", Worker)
    result = await trial.run(tmp_path)
    assert result["planned_native_requests"] == 16
    assert result["tts_attempts"] == len(calls) == (1 if failure else 16)
    assert result["completed_inner_chunks"] == (0 if failure else 16)
    assert result["logical_complete"] == (4 if failure else 24)
    assert result["unattempted_native"] == (15 if failure else 0)
    assert closed == (["baseline"] if failure else ["baseline", "us"])
    assert result["status"] == (
        "STOPPED_NO_RETRY" if failure else "US_TERM_PAIRS_COMPLETE_ACOUSTIC_UNVERIFIED"
    )
    assert result["retries"] == 0 and result["baseline_restored"]
