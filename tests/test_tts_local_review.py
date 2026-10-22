"""Test local review source coverage, offline isolation and qualification gates without loading or downloading a model."""

import copy
import json

import pytest

from scripts import tts_local_review as review
from scripts import tts_local_review_worker as worker
from tests.test_tts_local_review_worker import judgement, request


def events():
    """Build complete authored source-bound event fixtures with genuine-shape fields but no inference claims."""
    value = [dict(event="ready")]
    expected = []
    for index, row in enumerate(request()["cases"]):
        label = judgement()
        wanted = dict(presence="speech", language="english")
        if index in {2, 3}:
            label.update(presence="silence" if index == 2 else "non_speech", naturalness="not_applicable")
            wanted = dict(presence=label["presence"], naturalness="not_applicable")
        elif index in {4, 7, 8}:
            label.update(naturalness="unnatural", artifacts=["Declared fixture distortion"])
            wanted = dict(presence="speech", naturalness="unnatural", audible_defects=True)
        elif index in {1, 6}:
            label["language"] = wanted["language"] = "vietnamese"
        value.append(dict(event="review", id=row["id"], source_sha256=row["sha256"], sample_count=row["sample_count"], sample_rate=16000, generation_complete=True, audio_tokens=25, feature_frames=100, raw_text=json.dumps(label), judgement=label))
        expected.append(wanted)
    value.append(dict(event="complete"))
    return value, expected


def test_all_frozen_first_controls_required():
    """Require complete actual-source coverage and every factual/severe-defect condition; no partial control set can qualify."""
    actual, expected = events()
    assert review.qualification_checks(request(), actual, expected)["passed"]
    bad = copy.deepcopy(actual)
    bad[3]["judgement"]["presence"] = "speech"
    bad[3]["raw_text"] = json.dumps(bad[3]["judgement"])
    assert not review.qualification_checks(request(), bad, expected)["passed"]
    assert not review.qualification_checks(request(), actual[:-2], expected)["passed"]


@pytest.mark.parametrize("change", ["duplicate", "source", "eos", "features", "raw"])
def test_invalid_observation_cannot_become_hearing_evidence(change):
    """Reject duplicate, changed, unconditioned, truncated and repaired first responses independently of model exit success."""
    actual, _ = events()
    if change == "duplicate":
        actual[2]["id"] = actual[1]["id"]
    elif change == "source":
        actual[1]["source_sha256"] = "b"*64
    elif change == "eos":
        actual[1]["generation_complete"] = False
    elif change == "features":
        actual[1]["audio_tokens"] = 0
    else:
        actual[1]["raw_text"] = "unparsed"
    assert not review.audit_events(request(), actual)


def test_sealed_cpu_limits_and_no_parent_labels(tmp_path):
    """Keep no network/credentials/GPU and describe the retained12GiB virtual bound without running the paused evaluator."""
    command = review.sandbox("qualify", tmp_path)
    assert "--unshare-all" in command and "--clearenv" in command and "--remount-ro" in command
    assert "--as=12884901888" in command and "--cpu=1200:1201" in command
    assert "--cpu=14400:14401" in review.sandbox("review", tmp_path)
    assert not any("parent-only" in value or "/home/" == value for value in command)
    assert "CUDA_VISIBLE_DEVICES" in command and "HF_HUB_OFFLINE" in command


def test_common_review_blocked_without_passed_first_qualification(tmp_path, monkeypatch):
    """Never prepare or execute common24observations while genuine capability evidence is missing."""
    monkeypatch.setattr(review, "ROOT", tmp_path)
    with pytest.raises(FileNotFoundError):
        review.prepare_review()
    assert not (tmp_path / "review").exists()


def test_first_run_creates_private_synthetic_identity_directory(tmp_path, monkeypatch):
    """Initialize the owned synthetic identity folder before the shared SDK identity helper, retaining evidence without a real subprocess."""
    monkeypatch.setattr(review, "ROOT", tmp_path)
    monkeypatch.setattr(worker, "EXECUTION_ALLOWED", True)
    review.publish_json(tmp_path / "runtime-integrity.json", dict(files={}))
    monkeypatch.setattr(review, "runtime_entries", lambda: {})
    monkeypatch.setattr(review, "specs", lambda: [])
    monkeypatch.setattr(review, "core_snapshot", lambda: dict(pid=1, start_ticks=2, command_sha256="fixture"))
    monkeypatch.setattr(review, "run_worker", lambda *args, **kwargs: (dict(exit_code=0, timed_out=False), b'{"event":"complete","cases":0}\n', b''))
    review.run("imports", tmp_path / "run")
    assert (tmp_path / "runtime-source/passwd").is_file()
    assert (tmp_path / "runtime-source").stat().st_mode & 0o777 == 0o700


def test_neural_run_rejects_low_host_headroom_before_creating_output(tmp_path, monkeypatch):
    """Refuse a load launch when preflight headroom is insufficient without starting a worker or leaving a fake completed result."""
    def denied():
        """Emulate a measured host-headroom failure without allocating memory."""
        raise ValueError("local_review_host_memory_headroom")
    monkeypatch.setattr(review, "require_headroom", denied)
    monkeypatch.setattr(worker, "EXECUTION_ALLOWED", True)
    with pytest.raises(ValueError, match="host_memory_headroom"):
        review.run("load", tmp_path / "run")
    assert not (tmp_path / "run").exists()


@pytest.mark.parametrize("kib,passed", [(18*1024**2, True), (18*1024**2-1, False)])
def test_host_headroom_boundary_is_not_a_ram_measurement(tmp_path, kib, passed):
    """Require exact host MemAvailable units/bounds while explicitly distinguishing the virtual cap and unreserved preflight sample."""
    path = tmp_path / "meminfo"
    path.write_text(f"MemAvailable: {kib} kB\n")
    if passed:
        value = review.require_headroom(path)
        assert value["address_space_cap_bytes"] == 12*1024**3
        assert not value["reserved_memory"]
    else:
        with pytest.raises(ValueError, match="host_memory_headroom"):
            review.require_headroom(path)


def test_pre_repair_qualification_cannot_promote_repaired_protocol(tmp_path, monkeypatch):
    """Require separate native-EOS qualification rather than relabelling a prior capped-response run as corrected listening evidence."""
    monkeypatch.setattr(review, "ROOT", tmp_path)
    old = tmp_path / "qualification-first"
    old.mkdir()
    review.publish_json(old / "result.json", dict(observation_complete=True, qualification=dict(passed=True)))
    with pytest.raises(FileNotFoundError):
        review.require_qualification()


@pytest.mark.parametrize("mode", ["imports", "load", "qualify", "review"])
def test_owner_pause_blocks_every_execution_mode_before_side_effects(tmp_path, monkeypatch, mode):
    """Reject all evaluator runs before model checks, CORE requests, subprocesses or output publication while the owner pause is active."""
    def forbidden(*args, **kwargs):
        """Fail if a paused run reaches a service, model or subprocess operation."""
        raise AssertionError("paused_execution_side_effect")
    monkeypatch.setattr(review, "run_worker", forbidden)
    monkeypatch.setattr(review, "core_snapshot", forbidden)
    monkeypatch.setattr(review, "runtime_entries", forbidden)
    assert not worker.EXECUTION_ALLOWED
    with pytest.raises(ValueError, match="owner_paused_execution"):
        review.run(mode, tmp_path / "run")
    assert not (tmp_path / "run").exists()


def test_owner_pause_blocks_cli_metadata_modes_too(tmp_path, monkeypatch):
    """Honor the current pause at the CLI before preparing a packet or replacing a runtime snapshot."""
    import sys

    monkeypatch.setattr(sys, "argv", ["tts_local_review", "--mode", "snapshot-runtime"])
    with pytest.raises(ValueError, match="owner_paused_execution"):
        review.main()
