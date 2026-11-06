"""Test reference diagnostic coverage, sealed model mounts, pair invariants and local media publication."""

import copy
import base64

import pytest

from benchmarks.scripts import vi_api_reference_trial as trial
from benchmarks.tests.test_vi_speech_review import MediaParser


def frontend():
    """Provide an independent public phoneme fixture for four minimal controls."""
    return dict(
        reference_a="ˈeɪ",
        reference_api="ˈeɪ pˈiː ˈaɪ",
        rows=[
            dict(
                id=identity,
                source_text=text,
                native_g2p_phonemes=(
                    "ˌeɪpˌiːˈaɪ." if identity == "api-compact" else "ˈeɪ pˈiː ˈaɪ."
                ),
                phonemes=(
                    "ˈeɪ."
                    if identity == "letter-a"
                    else "ˌeɪpˌiːˈaɪ."
                    if identity == "api-compact"
                    else "ˈeɪ pˈiː ˈaɪ."
                ),
                decoded=(
                    "ˈeɪ."
                    if identity == "letter-a"
                    else "ˌeɪpˌiːˈaɪ."
                    if identity == "api-compact"
                    else "ˈeɪ pˈiː ˈaɪ."
                ),
                unknown_tokens=0,
            )
            for identity, text, _ in trial.CASES
        ],
    )


def completed():
    """Build complete fake paired observations with identical text and speaker anchors."""
    rows = trial.packet(frontend())
    for row in rows:
        enabled = row["mode"] == "with_reference"
        row.update(
            status="NATIVE_COMPLETE_AWAITING_OWNER_REVIEW",
            native=dict(
                reference_trace=dict(
                    phonemes=row["phonemes"],
                    token_ids=[44, 45],
                    speaker_embedding_sha256="a" * 64,
                    projected_anchor_sha256="b" * 64,
                    prompt_text_ids=[16, 3, 44, 45, 4],
                    use_ref_codes=enabled,
                    reference_rows=2 if enabled else 0,
                )
            ),
        )
    return rows


def test_exact_pair_denominator_and_frontend_binding():
    """Preregister sixteen slots without wrong English targets, duplicate cases or hidden missing rows."""
    rows = trial.packet(frontend())
    assert len(rows) == 16 and len({row["id"] for row in rows}) == 16
    assert len([row for row in rows if row["mode"] == "with_reference"]) == 8
    assert all(row["status"] == "UNATTEMPTED" for row in rows)
    bad = frontend()
    bad["reference_a"] = "a"
    with pytest.raises(ValueError):
        trial.packet(bad)
    bad = frontend()
    bad["rows"][0]["source_text"] = "not the approved text"
    with pytest.raises(ValueError):
        trial.packet(bad)


def test_actual_speaker_or_text_drift_fails_paired_result():
    """Prohibit an apparent ref-code comparison that changes the speaker or actual model token input."""
    rows = completed()
    trial.verify_pairs(rows)
    for key in [
        "speaker_embedding_sha256",
        "projected_anchor_sha256",
        "token_ids",
        "prompt_text_ids",
        "phonemes",
    ]:
        bad = copy.deepcopy(rows)
        bad[-1]["native"]["reference_trace"][key] = "changed"
        with pytest.raises(ValueError, match="pair_changed"):
            trial.verify_pairs(bad)
    bad = completed()
    bad[-1]["native"]["reference_trace"]["reference_rows"] = 3
    with pytest.raises(ValueError, match="audio_condition"):
        trial.verify_pairs(bad)


def test_native_command_only_changes_research_worker(tmp_path):
    """Retain original CPU/offline/resource settings and the pinned checkpoint mount."""
    out = tmp_path / "out"
    out.mkdir(mode=0o700)
    command = trial.native_command(out, "without_reference")
    assert "--unshare-all" in command and "--as=8589934592" in command
    assert "/model" in command and command[-2:] == [
        "/app/reference_worker.py",
        "without_reference",
    ]
    assert "--share-net" not in command
    with pytest.raises(ValueError):
        trial.native_command(out, "other")
    compile(trial.PROBE, "reference-probe", "exec")


def test_local_page_preserves_sixteen_native_payloads_and_labels():
    """Embed exact public fixture bytes without executable content, recording or external resources."""
    rows = trial.packet(frontend())
    audio = {row["id"]: row["id"].encode() for row in rows}
    page = trial.render_page(rows, audio)
    parser = MediaParser()
    parser.feed(page)
    assert len(parser.media) == 16 and not parser.forbidden and "https://" not in page
    assert {
        base64.b64decode(item["src"].split(",", 1)[1]) for item in parser.media
    } == set(audio.values())
    with pytest.raises(ValueError):
        trial.render_page(rows[:-1], audio)


@pytest.mark.asyncio
async def test_completed_control_panel_never_retries(tmp_path, monkeypatch):
    """Reject an old execution marker before touching assets or creating a native model process."""
    (tmp_path / "execution-freeze.json").write_text("{}")
    monkeypatch.setattr(trial, "verify_previous", lambda: pytest.fail("must not load"))
    with pytest.raises(ValueError, match="already_attempted"):
        await trial.run(tmp_path)


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [False, "native", "pair"])
async def test_controller_exact16_admission_first_failure_and_pair_integrity(
    tmp_path, monkeypatch, failure
):
    """Exercise the actual paired controller with public fixtures and no neural assets or private evidence."""
    import json
    import hashlib

    actual_project = trial.Q.assets.PROJECT
    project = tmp_path / "project"
    evidence = project / "docs/evidence"
    evidence.mkdir(parents=True)
    (evidence / "d74-api-reference-authorization.json").write_text(
        '{"authorized":true}'
    )
    hashes = {}
    names = [
        "benchmarks/scripts/vi_api_reference_trial.py",
        "benchmarks/scripts/vi_api_reference_worker.py",
        "benchmarks/tests/test_vi_api_reference_trial.py",
        "benchmarks/tests/test_vi_api_reference_worker.py",
    ]
    for name in names:
        path = project / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes((actual_project / name).read_bytes())
        hashes[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    root = tmp_path / "root"
    (root / "accepted-probe/native").mkdir(parents=True)
    (root / "accepted-probe/native/frontend.json").write_text(json.dumps(frontend()))
    (root / "software-verification.json").write_text(
        json.dumps(dict(status="PASS", source_sha256=hashes))
    )
    monkeypatch.setattr(trial.Q.assets, "PROJECT", project)
    monkeypatch.setattr(trial.Q.assets, "ROOT", root)
    monkeypatch.setattr(trial, "verify_previous", lambda: {})
    monkeypatch.setattr(trial.Q.lifecycle, "prepared_integrity", lambda root: None)
    monkeypatch.setattr(trial.Q.lifecycle, "verify_originals", lambda: {"fixture": 1})
    monkeypatch.setattr(trial.Q.lifecycle, "local_state", lambda: {"native_pids": []})
    calls, retirements = [], []

    class Worker:
        """Provide complete fake observed token/anchor traces for paired-controller validation."""

        def __init__(self, mode, directory, deadline):
            """Bind only the declared conditioning mode."""
            self.mode, self.failure = mode, None

        async def start(self):
            """Represent fake readiness without starting a model process."""
            return self

        async def call(self, message):
            """Return the first fake generation or inject a native failure/paired drift."""
            calls.append(message)
            if failure == "native":
                self.failure = "fixture_native_failure"
                raise ValueError(self.failure)
            enabled = self.mode == "with_reference"
            trace = dict(
                mode=self.mode,
                voice=message["voice"],
                phonemes=message["text"],
                use_ref_codes=enabled,
                reference_rows=2 if enabled else 0,
                token_ids=[44, 45],
                prompt_text_ids=[16, 3, 44, 45, 4],
                speaker_embedding_sha256="a" * 64,
                projected_anchor_sha256="b" * 64,
            )
            if failure == "pair" and self.mode == "without_reference":
                trace["projected_anchor_sha256"] = "changed"
            return dict(reference_trace=trace, generation_complete=True)

        async def close(self, force):
            """Record joined retirement once per fake condition."""
            retirements.append(self.mode)

    monkeypatch.setattr(trial, "ReferenceWorker", Worker)
    result = await trial.run(root)
    assert (
        len(result["rows"]) == 16 and result["asr_calls"] == result["core_calls"] == 0
    )
    assert result["baseline_restored"]
    if failure == "native":
        assert len(calls) == result["tts_attempts"] == 1 and result["unattempted"] == 15
        assert result["status"] == "STOPPED_NO_RETRY" and retirements == [
            "with_reference"
        ]
    else:
        assert len(calls) == result["tts_attempts"] == 16 and result["unattempted"] == 0
        assert retirements == list(trial.MODES)
        assert result["status"] == (
            "STOPPED_NO_RETRY"
            if failure
            else "PAIRED_DIAGNOSTIC_COMPLETE_QUALITY_UNVERIFIED"
        )


@pytest.mark.asyncio
async def test_reference_ready_mismatch_joins_real_owned_fixture(tmp_path, monkeypatch):
    """Reject mismatched readiness and join the exact local fixture process without neural imports."""
    import sys
    import time

    code = 'import json,time;print(json.dumps(dict(event="ready",candidate="turbo",mode="wrong")),flush=True);time.sleep(30)'
    monkeypatch.setattr(
        trial, "native_command", lambda *args: [sys.executable, "-c", code]
    )
    monkeypatch.setattr(
        trial.Q.lifecycle, "mem_available", lambda: 20 * trial.Q.lifecycle.GIB
    )
    monkeypatch.setattr(trial.os, "sched_getaffinity", lambda pid: {0, 1})
    monkeypatch.setattr(trial.Q.assets, "budget", lambda root: 0)
    worker = trial.ReferenceWorker(
        "with_reference", tmp_path / "worker", time.monotonic() + 10
    )
    with pytest.raises(ValueError, match="ready_binding"):
        await worker.start()
    assert (
        worker.process.returncode is not None
        and worker not in trial.Q.lifecycle.WORKERS
    )
    assert (worker.directory / "retirement.json").exists()


@pytest.mark.asyncio
async def test_no_headroom_prevents_reference_model_load(tmp_path, monkeypatch):
    """Enforce the retained host RAM floor before creating the output capability or starting a worker."""
    import time

    monkeypatch.setattr(trial.Q.lifecycle, "mem_available", lambda: 0)
    worker = trial.ReferenceWorker(
        "without_reference", tmp_path / "worker", time.monotonic() + 10
    )
    with pytest.raises(ValueError, match="preflight"):
        await worker.start()
    assert worker.process is None and not worker.directory.exists()
