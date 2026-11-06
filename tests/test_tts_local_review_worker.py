"""Test blind local audio-review request bounds, complete waveform integrity and honest first-response parsing without model inference."""

import hashlib
import json
from types import SimpleNamespace

import numpy as np
import pytest

from scripts import tts_local_review_worker as worker
from scripts.tts_local_review_worker import (
    generation_boundaries,
    memory_snapshot,
    parse_judgement,
    validate_request,
    waveform,
)


def judgement():
    """Provide an authored schema fixture, never a claimed real listening result."""
    return dict(presence="speech", language="english", naturalness="uncertain", confidence="medium", artifacts=[], prosody="Authored fixture", notes="No inference")


def request():
    """Provide nine opaque bounded control identities without references or expected labels."""
    return dict(mode="qualify", cases=[dict(id=f"clip-{i+1:02d}", sample_count=16000, sha256="a"*64) for i in range(9)])


@pytest.mark.parametrize("change", ["reference", "duplicate", "count", "path", "boolean", "hash", "mode"])
def test_untrusted_request_rejected(change):
    """Refuse text leakage, duplicate coverage, traversal and unbounded or noncanonical requests before neural imports."""
    value = request()
    if change == "reference":
        value["cases"][0]["reference"] = "secret label"
    elif change == "duplicate":
        value["cases"][1]["id"] = "clip-01"
    elif change == "count":
        value["cases"].pop()
    elif change == "path":
        value["cases"][0]["id"] = "../private"
    elif change == "boolean":
        value["cases"][0]["sample_count"] = True
    elif change == "hash":
        value["cases"][0]["sha256"] = "a"*63
    else:
        value["mode"] = "arbitrary"
    with pytest.raises(ValueError):
        validate_request(value)


def test_valid_blind_request_and_strict_response():
    """Accept exact declared fields while refusing prose, fabricated flags and invalid observation categories."""
    validate_request(request())
    value = judgement()
    assert parse_judgement(json.dumps(value)) == value
    assert parse_judgement("```json\n" + json.dumps(value) + "\n```") == value
    for bad in ["Heard speech", json.dumps(dict(value, actually_listened=True)), json.dumps(dict(value, naturalness="excellent")), json.dumps(dict(value, artifacts="none"))]:
        with pytest.raises(ValueError):
            parse_judgement(bad)


def test_original_full_timeline_waveform_and_corruption_guards(tmp_path):
    """Read unchanged full float32 inputs and reject mismatches, nonfinite samples and symlink aliases."""
    values = np.zeros(16000, dtype="<f4")
    raw = values.tobytes()
    path = tmp_path / "clip-01.f32"
    path.write_bytes(raw)
    row = dict(id="clip-01", sample_count=16000, sha256=hashlib.sha256(raw).hexdigest())
    assert np.array_equal(waveform(row, tmp_path), values)
    path.write_bytes(raw[:-4])
    with pytest.raises(ValueError):
        waveform(row, tmp_path)
    path.unlink()
    target = tmp_path / "other"
    target.write_bytes(raw)
    path.symlink_to(target)
    with pytest.raises(OSError):
        waveform(row, tmp_path)


def test_memory_snapshots_distinguish_virtual_and_resident_bytes(tmp_path, capsys):
    """Report authored kernel-shaped virtual/RSS samples separately from actual process lifetime peak counters."""
    path = tmp_path / "status"
    path.write_text("VmRSS: 100 kB\nVmSize: 500 kB\nVmPeak: 600 kB\nVmHWM: 120 kB\n")
    memory_snapshot("fixture", path)
    value = json.loads(capsys.readouterr().out)
    assert value["memory"] == dict(VmRSS_KiB=100, VmSize_KiB=500, VmPeak_KiB=600, VmHWM_KiB=120)
    assert value["stage"] == "fixture" and value["lifetime_max_RSS_KiB"] > 0


def test_final_resource_evidence_survives_native_load_failure(monkeypatch, capsys):
    """Retain final actual resource counters on failed loading without emitting a successful complete event or retrying."""
    import io
    from types import SimpleNamespace

    def fail(load):
        """Emulate one native load error without importing or allocating neural parameters."""
        raise RuntimeError("fixture_native_load_failure")
    monkeypatch.setattr(worker.os, "sched_setaffinity", lambda *args: None)
    monkeypatch.setattr(worker, "EXECUTION_ALLOWED", True)
    monkeypatch.setattr(worker.sys, "stdin", SimpleNamespace(buffer=io.BytesIO(b'{"mode":"load","cases":[]}')))
    monkeypatch.setattr(worker, "Runtime", fail)
    with pytest.raises(RuntimeError, match="fixture_native_load_failure"):
        worker.main()
    events = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert [event["event"] for event in events] == ["resources"]
    assert events[0]["stage"] == "worker_finally"


def test_native_thinker_eos_is_explicit_despite_empty_outer_generation_config():
    """Bind generation to the original Thinker/tokenizer end marker so empty outer metadata cannot continue into fabricated chat turns."""
    config = SimpleNamespace(eos_token_id=151645, pad_token_id=151643)
    tokenizer = SimpleNamespace(eos_token_id=151645, pad_token_id=151643)
    outer = SimpleNamespace(eos_token_id=None)
    assert generation_boundaries(config, tokenizer) == dict(eos_token_id=151645, pad_token_id=151643)
    assert outer.eos_token_id is None


@pytest.mark.parametrize("eos,pad", [(None,151643),(151644,151643),(True,151643),(151645,None),(151645,151645)])
def test_foreign_or_missing_original_generation_boundaries_rejected(eos, pad):
    """Reject guessed, missing or substituted stop/padding IDs instead of hiding invalid completion evidence."""
    tokenizer = SimpleNamespace(eos_token_id=151645, pad_token_id=151643)
    with pytest.raises(ValueError, match="original_generation_boundaries"):
        generation_boundaries(SimpleNamespace(eos_token_id=eos,pad_token_id=pad),tokenizer)


def test_owner_pause_blocks_direct_worker_before_sdk_or_input(monkeypatch, capsys):
    """Prevent bypassing the paused controller by invoking the worker directly; do not touch input, affinity or model libraries."""
    def forbidden(*args, **kwargs):
        """Fail if a paused worker reaches affinity setup or native runtime construction."""
        raise AssertionError("paused_worker_side_effect")
    monkeypatch.setattr(worker.os, "sched_setaffinity", forbidden)
    monkeypatch.setattr(worker, "Runtime", forbidden)
    monkeypatch.setattr(worker, "EXECUTION_ALLOWED", False)
    with pytest.raises(ValueError, match="owner_paused_execution"):
        worker.main()
    assert capsys.readouterr().out == ""


@pytest.mark.parametrize("load", [False, True])
def test_owner_pause_blocks_runtime_constructor_before_neural_imports(load, monkeypatch):
    """Reject direct runtime construction as well as CLI entry points while the owner pause is active."""
    monkeypatch.setattr(worker, "EXECUTION_ALLOWED", False)
    with pytest.raises(ValueError, match="owner_paused_execution"):
        worker.Runtime(load)


def test_owner_pause_blocks_review_on_an_existing_runtime(monkeypatch):
    """Prevent a retained runtime object from evaluating another input after execution has been paused."""
    def forbidden(*args, **kwargs):
        """Fail if paused direct review reads a waveform or reaches native inference."""
        raise AssertionError("paused_runtime_input_access")
    monkeypatch.setattr(worker, "waveform", forbidden)
    runtime = object.__new__(worker.Runtime)
    monkeypatch.setattr(worker, "EXECUTION_ALLOWED", False)
    with pytest.raises(ValueError, match="owner_paused_execution"):
        runtime.review({})


@pytest.mark.parametrize("mode", ["imports", "load"])
def test_adr101_allows_only_import_and_load_policy(mode):
    """Reflect the explicit limited owner resume without importing SDKs or claiming model success."""
    worker.require_execution_permission(mode)


def test_adr101_rejects_direct_audio_worker_before_affinity(monkeypatch):
    """Prevent direct worker invocation from bypassing the load-only controller scope."""
    import io

    def forbidden(*args, **kwargs):
        """Fail if an unapproved audio mode reaches affinity changes or neural construction."""
        raise AssertionError("unapproved_audio_side_effect")
    monkeypatch.setattr(worker.os, "sched_setaffinity", forbidden)
    monkeypatch.setattr(worker, "Runtime", forbidden)
    monkeypatch.setattr(worker.sys, "stdin", SimpleNamespace(buffer=io.BytesIO(json.dumps(request()).encode())))
    with pytest.raises(ValueError, match="owner_load_only_scope"):
        worker.main()


def test_adr101_rejects_review_on_retained_runtime():
    """Block inference on already allocated objects even while fresh loading is approved."""
    runtime = object.__new__(worker.Runtime)
    with pytest.raises(ValueError, match="owner_load_only_scope"):
        runtime.review({})
