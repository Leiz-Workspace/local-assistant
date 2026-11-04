"""Test the VAD-only operator's native evidence, fixed finite scope, cleanup and immutable first outcomes."""

import copy
import json
import subprocess

import numpy as np
import pytest

from benchmarks.scripts import vi_voice_presence_check as target
from benchmarks.tests.test_vi_voice_presence import audio


def events(cases, reverse=True):
    """Create deterministic authored native-shaped observations for software validation only."""
    result = [
        dict(
            event="ready",
            execution=dict(providers=["CPUExecutionProvider"]),
            logical_CPU_affinity=[0, 1],
        )
    ]
    passes = (
        [("forward", cases), ("reverse", list(reversed(cases)))]
        if reverse
        else [("qualification", cases)]
    )
    for name, rows in passes:
        for row in rows:
            probabilities = np.zeros((row["sample_count"] + 511) // 512, dtype="<f4")
            result.append(
                dict(
                    event="observation",
                    pass_name=name,
                    id=row["id"],
                    status="ok",
                    sample_count=row["sample_count"],
                    waveform_sha256=row["waveform_sha256"],
                    source_samples_modified=False,
                    external_recording_resets=1,
                    segments=[dict(start=4, end=500)],
                    window_probabilities=probabilities.tolist(),
                    probability_sha256=target.sha(probabilities.tobytes()),
                    wall_seconds=0.01,
                )
            )
    return result + [dict(event="complete")]


def case(identity="one"):
    """Describe a finite synthetic source without relying on private evaluation artifacts."""
    value = audio()
    return dict(
        id=identity,
        filename=identity + ".f32",
        sample_count=value.sample_count,
        waveform_sha256=target.sha(target.floats(value)),
        expected_speech=True,
        kind="independent_public_speech",
        language="vi",
    )


def test_complete_forward_reverse_native_shape_is_reconciled():
    """Require exactly matching native input and recurrent-state replay for both planned passes."""
    cases = [case("a"), case("b")]
    result = target.validate_events(cases, events(cases), reverse=True)
    assert set(result) == {"a", "b"}


@pytest.mark.parametrize(
    "mutation",
    [
        "missing",
        "duplicate",
        "wrong_owner_source",
        "sample_count",
        "modified",
        "reset",
        "overlap",
        "probability",
        "provider",
        "affinity",
        "reverse_drift",
        "incomplete",
    ],
)
def test_incomplete_or_tampered_native_evidence_is_refused(mutation):
    """Reject invalid receipts before a forged result can become a speech-admission decision."""
    cases = [case()]
    rows = events(cases)
    if mutation == "missing":
        del rows[1]
    elif mutation == "duplicate":
        rows.insert(1, copy.deepcopy(rows[1]))
    elif mutation == "wrong_owner_source":
        rows[1]["waveform_sha256"] = "b" * 64
    elif mutation == "sample_count":
        rows[1]["sample_count"] += 1
    elif mutation == "modified":
        rows[1]["source_samples_modified"] = True
    elif mutation == "reset":
        rows[1]["external_recording_resets"] = True
    elif mutation == "overlap":
        rows[1]["segments"] = [dict(start=0, end=10), dict(start=9, end=20)]
    elif mutation == "probability":
        rows[1]["window_probabilities"][0] = float("nan")
    elif mutation == "provider":
        rows[0]["execution"]["providers"] = ["CUDAExecutionProvider"]
    elif mutation == "affinity":
        rows[0]["logical_CPU_affinity"] = [2]
    elif mutation == "reverse_drift":
        rows[2]["segments"] = [dict(start=5, end=500)]
    elif mutation == "incomplete":
        rows = rows[:-1]
    with pytest.raises(ValueError, match="presence_|vad_"):
        target.validate_events(cases, rows, reverse=True)


@pytest.mark.parametrize("accepted", [False, True])
@pytest.mark.asyncio
async def test_native_replay_reaches_only_explicit_downstream_sentinel(accepted):
    """Distinguish real detector evidence from mocked ASR/CORE/TTS and retain whole PCM on acceptance."""
    row = case()
    event = events([row], reverse=False)[1]
    if not accepted:
        event["segments"] = []
    result = await target.replay_pipeline(row, audio(), event)
    assert result["accepted"] == accepted and result["asr_sentinel_calls"] == int(
        accepted
    )
    assert (
        result["actual_asr_calls"] == result["core_calls"] == result["tts_calls"] == 0
    )
    assert result["full_pcm_preserved"] and result["original_clock_preserved"]


def test_native_call_count_uses_observed_logs_and_marks_malformed_unknown(tmp_path):
    """Never replace partial or malformed native observations with the planned100total."""
    worker = tmp_path / "worker-0"
    worker.mkdir()
    log = worker / "stdout.jsonl"
    log.write_text('{"event":"ready"}\n{"event":"observation"}\n')
    assert target.observed_calls(tmp_path) == 1
    log.write_text('{"event":"observation"}\ntruncated')
    assert target.observed_calls(tmp_path) is None


@pytest.mark.parametrize("failure", [None, "timeout", "interrupt", "exit", "headroom"])
def test_worker_joins_and_preserves_first_outputs(monkeypatch, tmp_path, failure):
    """Retain failed process bytes and reap the exact owned child before propagating failure."""
    killed = []

    class Child:
        """Model only process ownership and communication for operator lifecycle verification."""

        pid = 123456
        returncode = None

        def __init__(self, *args, **kwargs):
            """Assert the native command receives explicit pipes and isolated session ownership."""
            assert kwargs["start_new_session"] is True
            self.calls = 0

        def poll(self):
            """Expose whether the owned fake process has actually been reaped."""
            return self.returncode

        def communicate(self, *args, **kwargs):
            """Return retained bytes after a first synthetic interruption, without starting another child."""
            self.calls += 1
            if self.calls == 1 and failure == "timeout":
                raise subprocess.TimeoutExpired("vad", 1)
            if self.calls == 1 and failure == "interrupt":
                raise KeyboardInterrupt()
            self.returncode = -9 if killed else (1 if failure == "exit" else 0)
            return b'{"event":"complete"}\n', b"worker log"

    def headroom():
        """Refuse loading before any process is created when the memory preflight fails."""
        if failure == "headroom":
            raise ValueError("headroom")
        return {"MemAvailable_bytes": 16 * 1024**3}

    monkeypatch.setattr(target, "require_headroom", headroom)
    monkeypatch.setattr(target, "sandbox", lambda: [str(target.VAD_ROOT / "samples")])
    monkeypatch.setattr(target.subprocess, "Popen", Child)
    monkeypatch.setattr(target.os, "killpg", lambda pid, sig: killed.append(pid))
    if failure:
        with pytest.raises(KeyboardInterrupt if failure == "interrupt" else ValueError):
            target.run_vad(tmp_path, "worker-0", dict(mode="smoke", cases=[]))
    else:
        _, receipt = target.run_vad(tmp_path, "worker-0", dict(mode="smoke", cases=[]))
        assert receipt["exit_code"] == 0
    if failure == "headroom":
        assert not (tmp_path / "worker-0/process.json").exists()
    else:
        receipt = json.loads((tmp_path / "worker-0/process.json").read_text())
        assert receipt["reaped"]
        assert (tmp_path / "worker-0/stderr.log").read_bytes() == b"worker log"
    assert killed == ([123456] if failure in ("timeout", "interrupt") else [])


def setup_execution(monkeypatch, tmp_path):
    """Prepare an isolated software-only53case scope without any native artifacts or dependencies."""
    source = tmp_path / "source.py"
    source.write_text("source")
    source_sha = target.sha(source.read_bytes())
    monkeypatch.setattr(target, "PROJECT", tmp_path)
    monkeypatch.setattr(target, "SOURCES", ("source.py",))
    monkeypatch.setattr(target, "verify_snapshot", lambda value: None)
    monkeypatch.setattr(target, "verify_provision", lambda: None)
    monkeypatch.setattr(target.prior, "local_state", lambda: {"native_pids": []})
    monkeypatch.setattr(target, "load_audio", lambda root, row: audio())
    cases = [case("c" + str(i)) for i in range(53)]
    samples = tmp_path / "samples"
    samples.mkdir()
    for row in cases:
        (samples / row["filename"]).write_bytes(target.floats(audio()))
    freeze = dict(
        source_sha256={"source.py": source_sha},
        original_source_sha256={},
        before={"native_pids": []},
        cases=cases,
    )
    target.publish(tmp_path / "execution-freeze.json", freeze)
    target.publish(
        tmp_path / "software-verification.json",
        dict(status="PASS", source_sha256={"source.py": source_sha}),
    )
    return cases


@pytest.mark.parametrize("fail_first", [False, True])
def test_execute_fixed_batches_stops_on_first_fault_and_never_retries(
    monkeypatch, tmp_path, fail_first
):
    """Freeze all53rows, run at most7workers and retain every unattempted row after first failure."""
    setup_execution(monkeypatch, tmp_path)
    sizes = []

    def run(root, identity, request, **kwargs):
        """Generate native-shaped test logs with no speech models or external requests."""
        sizes.append(len(request["cases"]))
        if fail_first:
            raise ValueError("first fault")
        data = events(request["cases"], reverse=request["mode"] == "predict")
        directory = root / identity
        directory.mkdir()
        (directory / "stdout.jsonl").write_text(
            "".join(json.dumps(x) + "\n" for x in data)
        )
        return data, dict(exit_code=0, reaped=True)

    monkeypatch.setattr(target, "run_vad", run)
    if fail_first:
        with pytest.raises(ValueError, match="first fault"):
            target.execute(tmp_path)
    else:
        target.execute(tmp_path)
    result = json.loads((tmp_path / "result.json").read_text())
    assert sizes == ([47] if fail_first else [47, 1, 1, 1, 1, 1, 1])
    assert len(result["unattempted"]) == (53 if fail_first else 0)
    assert result["actual_calls"]["vad_observations"] == (0 if fail_first else 100)
    assert (
        result["actual_calls"]["asr"]
        == result["actual_calls"]["core"]
        == result["actual_calls"]["tts"]
        == 0
    )
    with pytest.raises(FileExistsError):
        target.execute(tmp_path)
    assert sizes == ([47] if fail_first else [47, 1, 1, 1, 1, 1, 1])


def test_unverified_software_cannot_start_native_workers(monkeypatch, tmp_path):
    """Keep a finite source-bound software gate ahead of every neural loading attempt."""
    setup_execution(monkeypatch, tmp_path)
    path = tmp_path / "software-verification.json"
    path.write_text(json.dumps(dict(status="FAIL")))
    with pytest.raises(ValueError, match="presence_software_gate"):
        target.execute(tmp_path)
    assert not (tmp_path / "run-start.json").exists()


def test_pcm_capability_refuses_changed_bytes(tmp_path):
    """Reconstruct only exact normalized audio rather than trusting stored hash fields."""
    from dataclasses import asdict

    value = audio()
    row = case()
    row["audio"] = {k: v for k, v in asdict(value).items() if k != "pcm_s16le"}
    (tmp_path / "pcm").mkdir()
    path = tmp_path / "pcm/one.s16le"
    path.write_bytes(value.pcm_s16le)
    assert target.load_audio(tmp_path, row) == value
    path.write_bytes(b"\0" * len(value.pcm_s16le))
    with pytest.raises(Exception, match="invalid_input"):
        target.load_audio(tmp_path, row)


def test_prepare_freezes_original_panel_and_exact_six_quiet_derivatives(
    monkeypatch, tmp_path
):
    """Keep fixed corpus order and whole-recording lengths while distinguishing six derived gains from new speech sources."""
    from types import SimpleNamespace

    project = tmp_path / "project"
    project.mkdir()
    corpus = project / "old-corpus"
    corpus.mkdir()
    original = project / "old-workflow"
    original.mkdir()
    value = audio()
    rows = []
    raw = target.floats(value)
    for index in range(47):
        identity = "c" + str(index)
        path = corpus / (identity + ".f32")
        path.write_bytes(raw)
        rows.append(
            dict(
                id=identity,
                waveform_path=str(path),
                waveform_sha256=target.sha(raw),
                sample_count=value.sample_count,
                kind="independent_public_speech"
                if index < 40
                else (
                    "authored_no_speech" if index < 45 else "padded_source_composite"
                ),
                language="vi_vn" if index < 20 else "en_us",
            )
        )
    (corpus / "corpus.json").write_text(json.dumps(dict(cases=rows)))
    bindings = {
        row["id"]: dict(request=dict(waveform_sha256=target.sha(raw)))
        for row in rows[:6]
    }
    (original / "execution-freeze.json").write_text(
        json.dumps(dict(input_conversion=bindings))
    )
    source = project / "source.py"
    source.write_text("source")
    monkeypatch.setattr(target, "PROJECT", project)
    monkeypatch.setattr(target, "CORPUS_ROOT", corpus)
    monkeypatch.setattr(target, "SOURCES", ("source.py",))
    monkeypatch.setattr(target, "ADR", "source.py")
    monkeypatch.setattr(target, "previous_snapshot", lambda: {})
    monkeypatch.setattr(target.prior, "ROOT", original)
    monkeypatch.setattr(target.prior, "local_state", lambda: {})
    monkeypatch.setattr(
        target.prior,
        "NativeAudioNormalizer",
        lambda: SimpleNamespace(normalize=lambda raw: value),
    )
    freeze = target.prepare(project / "new")
    assert len(freeze["cases"]) == 53 and freeze["prior_D74_exact_inputs"] == 6
    assert [row["id"] for row in freeze["cases"][:47]] == [row["id"] for row in rows]
    derived = freeze["cases"][47:]
    assert [row["gain"] for row in derived] == [0.5, 0.1, 0.03] * 2
    assert [row["language"] for row in derived] == ["vi"] * 3 + ["en"] * 3
    assert all(
        row["sample_count"] == value.sample_count and row["expected_speech"]
        for row in derived
    )
    assert all(
        target.load_audio(project / "new", row).sample_count == value.sample_count
        for row in freeze["cases"]
    )
    assert all(
        target.sha((corpus / (row["id"] + ".f32")).read_bytes())
        == row["waveform_sha256"]
        for row in rows
    )
    with pytest.raises(FileExistsError):
        target.prepare(project / "new")
