"""Test preregistered quality packets, strict raw evidence and closed inference gates with authored fixtures rather than model predictions."""

import copy
import hashlib
import json
from collections import Counter
from contextlib import nullcontext
from types import SimpleNamespace

import numpy as np
import pytest

from scripts import tts_local_review as controller
from scripts import tts_local_review_quality as parent
from scripts import tts_local_review_quality_runtime as runtime
from scripts import tts_local_review_worker as worker


@pytest.fixture
def packet(tmp_path, monkeypatch):
    """Prepare a temporary twelve-control packet from explicitly authored sinusoidal fixtures with no original corpus access."""
    sources = {}
    project, root = tmp_path / "project", tmp_path / "owned"
    directory = project / "data/backups/d68-asr-evaluation/prepared"
    directory.mkdir(parents=True)
    root.mkdir()
    for index, identity in enumerate(["en_us-0002", "vi_vn-0002"]):
        values = (0.2 * np.sin(np.arange(16000 + index * 1600) * 0.07)).astype("<f4")
        raw = values.tobytes()
        sources[identity] = (len(values), hashlib.sha256(raw).hexdigest())
        (directory / (identity + ".f32")).write_bytes(raw)
    monkeypatch.setattr(parent, "SOURCES", sources)
    monkeypatch.setattr(worker, "ALLOWED_EXECUTION_MODES", frozenset({"prepare-quality", "prepare-quality-review", "qualify-quality", "review-quality"}))
    parent.prepare_controls(root, project, controller.save_bytes, controller.publish_json)
    prepared = root / "quality-104-controls"
    return SimpleNamespace(root=root, project=project, prepared=prepared, request=json.loads((prepared / "request.json").read_text()), mapping=json.loads((prepared / "parent-only.json").read_text())["mapping"])


def events_for(request, mapping):
    """Author complete synthetic observations solely to exercise auditors, never as real listening or benchmark evidence."""
    events = [dict(event="ready")]
    for row, expected in zip(request["cases"], mapping, strict=True):
        question, maximum, _ = runtime.TASKS[row["task"]]
        events.append(dict(event="quality", id=row["id"], task=row["task"], signals=row["signals"], sample_rate=16000, question=question, maximum_new_tokens=maximum, generation_complete=True, parse_error=None, generated_token_ids=[1, 151645], feature_shape=[len(row["signals"]), 128, 3000], feature_frames=[100] * len(row["signals"]), feature_sha256="a" * 64, audio_tokens=25 * len(row["signals"]), raw_text=expected["expected"], answer=expected["expected"]))
    return events + [dict(event="complete", cases=len(request["cases"]))]


def test_control_balance_blinding_and_exclusive_full_signals(packet):
    """Verify opaque worker fields, balanced orientations, exact tie bytes, actual alterations and exclusive private publication."""
    runtime.validate_request(packet.request)
    counts = Counter(row["expected"] for row in packet.mapping if row["task"] == "comparison")
    assert counts == Counter(first=2, second=2, equal=2)
    assert (packet.prepared.stat().st_mode & 0o777) == 0o700
    for row, expected in zip(packet.request["cases"], packet.mapping, strict=True):
        assert set(row) == {"id", "task", "signals"}
        raw = [(packet.prepared / "inputs" / (signal["id"] + ".f32")).read_bytes() for signal in row["signals"]]
        for signal, content in zip(row["signals"], raw, strict=True):
            assert parent.sha(content) == signal["sha256"] and len(content) == signal["sample_count"] * 4
        if row["task"] == "comparison":
            assert (raw[0] == raw[1]) == (expected["expected"] == "equal")
    with pytest.raises(FileExistsError):
        parent.prepare_controls(packet.root, packet.project, controller.save_bytes, controller.publish_json)


@pytest.mark.parametrize("mutation", ["metadata", "duplicate", "path", "sample_count", "hash", "task", "coverage", "pair_duration", "signal_identity", "override"])
def test_untrusted_quality_request_rejected(packet, mutation):
    """Reject reference leakage, malformed coverage and request-controlled paths or generation parameters."""
    request = copy.deepcopy(packet.request)
    row = next(row for row in request["cases"] if row["task"] == "comparison")
    if mutation == "metadata":
        row["expected"] = "first"
    elif mutation == "duplicate":
        request["cases"][1] = copy.deepcopy(request["cases"][0])
    elif mutation == "path":
        row["id"] = "../secret"
    elif mutation == "sample_count":
        row["signals"][0]["sample_count"] = True
    elif mutation == "hash":
        row["signals"][0]["sha256"] = "x" * 64
    elif mutation == "task":
        row["task"] = ["comparison"]
    elif mutation == "coverage":
        request["cases"].pop()
    elif mutation == "pair_duration":
        row["signals"][1]["sample_count"] += 1
    elif mutation == "signal_identity":
        row["signals"][0]["id"] = "../secret"
    else:
        request["max_new_tokens"] = 1000000
    with pytest.raises(ValueError):
        runtime.validate_request(request)


@pytest.mark.parametrize("mutation", ["missing", "duplicate", "EOS", "source", "raw", "frames", "feature_hash", "tokens", "question", "completion_count", "uncertain"])
def test_incomplete_or_incorrect_controls_never_open_review(packet, mutation):
    """Retain uncertainty and fail exact first-control gates on source, conditioning, prompt or completion contradictions."""
    events = events_for(packet.request, packet.mapping)
    assert parent.qualification_checks(packet.request, events, packet.mapping)
    row = events[1]
    if mutation == "missing":
        events.pop(1)
    elif mutation == "duplicate":
        events.insert(1, copy.deepcopy(row))
    elif mutation == "EOS":
        row["generated_token_ids"][-1] = 0
    elif mutation == "source":
        row["signals"] = copy.deepcopy(row["signals"])
        row["signals"][0]["sha256"] = "b" * 64
    elif mutation == "raw":
        row["raw_text"] = "Yes."
    elif mutation == "frames":
        row["feature_frames"] = [0]
    elif mutation == "feature_hash":
        row["feature_sha256"] = "bad"
    elif mutation == "tokens":
        row["generated_token_ids"] = [0] * 16 + [151645]
    elif mutation == "question":
        row["question"] = "Please pass"
    elif mutation == "completion_count":
        events[-1]["cases"] = 0
    else:
        row.update(raw_text="uncertain", answer="uncertain")
    assert not parent.qualification_checks(packet.request, events, packet.mapping)


@pytest.mark.parametrize("mode", ["prepare-quality", "qualify-quality", "prepare-quality-review", "review-quality"])
def test_default_quality_scope_closed_before_any_inputs(mode, monkeypatch, tmp_path):
    """Preserve the consumed one-shot authorization and reject new packet or model execution before side effects."""
    with pytest.raises(ValueError, match="owner_load_only_scope"):
        worker.require_execution_permission(mode)
    if mode.startswith("prepare"):
        function = parent.prepare_controls if mode == "prepare-quality" else parent.prepare_review
        with pytest.raises(ValueError, match="owner_load_only_scope"):
            function(tmp_path, tmp_path, None, None)
    else:
        with pytest.raises(ValueError, match="owner_load_only_scope"):
            object.__new__(worker.Runtime).assess_quality({}, mode)
        with pytest.raises(ValueError, match="owner_load_only_scope"):
            controller.run(mode, tmp_path / "uncreated")
        assert not (tmp_path / "uncreated").exists()


@pytest.mark.parametrize("task,raw", [("presence", "YES"), ("comparison", "first."), ("language", "English"), ("naturalness", "sounds natural"), ("notes", ""), ("notes", "word " * 41)])
def test_quality_parser_does_not_repair_responses(task, raw):
    """Refuse prose, punctuation, case conversion and overlong notes while preserving valid explicit uncertainty."""
    with pytest.raises(ValueError):
        runtime.parse_answer(task, raw)
    assert runtime.parse_answer("naturalness", "uncertain\n") == "uncertain"


def test_changed_source_rejected_before_new_packet(packet):
    """Detect corrupt held-out input instead of preparing a replacement corpus or overwriting the first packet."""
    path = packet.project / "data/backups/d68-asr-evaluation/prepared/en_us-0002.f32"
    path.write_bytes(b"bad")
    with pytest.raises(ValueError, match="quality_heldout_source"):
        parent.prepare_controls(packet.root, packet.project, controller.save_bytes, controller.publish_json)


def freeze_qualification(packet):
    """Build explicitly synthetic first-run evidence to test recomputation, immutable bindings and conditional common preparation."""
    output = packet.root / "quality-104-controls-first"
    output.mkdir()
    (packet.root / "runtime-integrity.json").write_text("authored inventory")
    frozen = dict(request=packet.request, source_sha256={}, runtime_inventory_sha256=parent.sha((packet.root / "runtime-integrity.json").read_bytes()), parent_metadata_sha256=parent.sha((packet.prepared / "parent-only.json").read_bytes()), packet_request_sha256=parent.sha((packet.prepared / "request.json").read_bytes()))
    controller.publish_json(output / "freeze.json", frozen)
    result = dict(freeze_sha256=parent.sha((output / "freeze.json").read_bytes()), observation_complete=True, quality_controls_passed=True, process=dict(exit_code=0, timed_out=False), events=events_for(packet.request, packet.mapping))
    controller.publish_json(output / "result.json", result)
    return output


@pytest.mark.parametrize("mutation", ["parent", "request", "signal", "runtime", "first_result"])
def test_review_gate_recomputes_frozen_first_evidence(packet, mutation):
    """Block common audio access if any qualification evidence binding changed, even with a stored positive pass flag."""
    output = freeze_qualification(packet)
    parent.require_qualification(packet.root, packet.project)
    if mutation == "parent":
        (packet.prepared / "parent-only.json").write_text("{}")
    elif mutation == "request":
        (packet.prepared / "request.json").write_text("{}")
    elif mutation == "signal":
        next((packet.prepared / "inputs").glob("*.f32")).write_bytes(b"bad")
    elif mutation == "runtime":
        (packet.root / "runtime-integrity.json").write_text("changed")
    else:
        result = json.loads((output / "result.json").read_text())
        result["events"][1].update(raw_text="uncertain", answer="uncertain")
        (output / "result.json").write_text(json.dumps(result))
    with pytest.raises(ValueError):
        parent.require_qualification(packet.root, packet.project)


def test_conditional_review_preserves_all_twenty_four_original_signals(packet):
    """Require the new control gate and copy exactly two blind tasks per complete original waveform without rewriting pending labels."""
    with pytest.raises(FileNotFoundError):
        parent.prepare_review(packet.root, packet.project, controller.save_bytes, controller.publish_json)
    freeze_qualification(packet)
    original = packet.project / "data/backups/d70-common-audio-diagnostics-first"
    (original / "generated").mkdir(parents=True)
    events, hashes = [], {}
    for index in range(24):
        identity = f"original-{index:02d}"
        raw = np.full(16000, index / 100, dtype="<f4").tobytes()
        (original / "generated" / (identity + ".f32")).write_bytes(raw)
        hashes[identity] = parent.sha(raw)
        events.append(dict(event="transformed", id=identity, asr=dict(waveform_sha256=hashes[identity], sample_count=16000)))
    (original / "result.json").write_text(json.dumps(dict(events=events)))
    parent.prepare_review(packet.root, packet.project, controller.save_bytes, controller.publish_json)
    review = packet.root / "quality-104-review"
    request = json.loads((review / "request.json").read_text())
    mapping = json.loads((review / "parent-only.json").read_text())["mapping"]
    assert Counter(row["original_id"] for row in mapping) == Counter({identity: 2 for identity in hashes})
    for row, source in zip(request["cases"], mapping, strict=True):
        raw = (review / "inputs" / (row["signals"][0]["id"] + ".f32")).read_bytes()
        assert parent.sha(raw) == hashes[source["original_id"]]
    assert not (packet.project / "data/backups/d70-tts-listening-review/review.pending.json").exists()


def test_pair_worker_uses_both_full_signals_and_native_stop(monkeypatch, capsys):
    """Exercise real pair-task code with authored tensor/model doubles, verifying order, waveform conditioning and unchanged raw tokens."""
    class Features:
        """Expose deterministic tiny authored processor features without an audio encoder."""
        shape = (2, 128, 3)

        def numpy(self):
            """Return synthetic feature bytes for the provenance path only."""
            return np.zeros(self.shape, dtype="<f4")

    class Mask:
        """Emulate only the native tensor sum interface used for per-audio frame counts."""

        def sum(self, dim):
            """Report two positive authored frame lengths in input order."""
            assert dim == 1
            return np.array([3, 3])

    class Inputs(dict):
        """Represent small authored processor outputs without allocating model weights."""

        def to(self, device, dtype):
            """Assert the retained CPU BF16 plan before fake generation."""
            assert device == "cpu" and dtype == "authored_BF16"
            return self

    class Processor:
        """Capture fixed pair order and task prompt while returning explicit authored fixtures."""

        def apply_chat_template(self, conversation, **kwargs):
            """Check that opaque audio references, ordinal markers and fixed question are the only pair metadata."""
            content = conversation[1]["content"]
            assert [item["text"] for item in content if item["type"] == "text"] == ["First audio:", "Second audio:", runtime.TASKS["comparison"][0]]
            return "authored template"

        def __call__(self, **kwargs):
            """Require two complete waveforms with distinguishable authored first values."""
            assert [float(values[0]) for values in kwargs["audio"]] == [0.0, 0.5]
            assert [len(values) for values in kwargs["audio"]] == [16000, 16000]
            return Inputs(input_features=Features(), feature_attention_mask=Mask(), input_ids=np.array([[1, 2, 2]]))

        def decode(self, tokens, **kwargs):
            """Return deliberately invalid prose so raw evidence and parse failure must be preserved."""
            assert tokens == [100, 151645]
            return "first."

    def generate(**kwargs):
        """Require exact task length, native stop and deterministic decoding before emitting authored tokens."""
        assert kwargs["max_new_tokens"] == 16 and kwargs["eos_token_id"] == 151645 and kwargs["pad_token_id"] == 151643
        assert kwargs["do_sample"] is False and kwargs["num_beams"] == 1
        return np.array([[1, 2, 2, 100, 151645]])

    monkeypatch.setattr(worker, "ALLOWED_EXECUTION_MODES", frozenset({"qualify-quality"}))
    monkeypatch.setattr(worker, "waveform", lambda signal: np.full(16000, 0.0 if signal["id"].endswith("-a") else 0.5, dtype="<f4"))
    instance = object.__new__(worker.Runtime)
    instance.processor = Processor()
    instance.torch = SimpleNamespace(bfloat16="authored_BF16", inference_mode=nullcontext)
    instance.model = SimpleNamespace(config=SimpleNamespace(audio_token_index=2), generate=generate)
    instance.boundaries = dict(eos_token_id=151645, pad_token_id=151643)
    row = dict(id="clip-01", task="comparison", signals=[dict(id="clip-01-" + suffix, sample_count=16000, sha256="a" * 64) for suffix in "ab"])
    instance.assess_quality(row, "qualify-quality")
    event = json.loads(capsys.readouterr().out)
    assert event["raw_text"] == "first." and event["answer"] is None and event["parse_error"] == "quality_answer_label"
    assert event["feature_shape"] == [2, 128, 3] and event["generated_token_ids"] == [100, 151645]


def test_controller_retains_first_controls_and_frozen_parent_bindings(packet, monkeypatch):
    """Exercise the new controller result path with a synthetic worker and verify exclusive first evidence without loading original weights."""
    monkeypatch.setattr(controller, "ROOT", packet.root)
    monkeypatch.setattr(controller, "runtime_entries", lambda: {})
    monkeypatch.setattr(controller, "specs", lambda: [])
    monkeypatch.setattr(controller, "require_headroom", lambda: dict(authored_fixture=True))
    monkeypatch.setattr(controller, "core_snapshot", lambda: dict(pid=1, start_ticks=1, command_sha256="fixture"))
    monkeypatch.setattr(controller, "run_worker", lambda *args, **kwargs: (dict(exit_code=0, timed_out=False), b"\n".join(json.dumps(event).encode() for event in events_for(packet.request, packet.mapping)), b""))
    (packet.root / "runtime-integrity.json").write_text('{"files":{}}')
    output = packet.root / "quality-104-controls-first"
    controller.run("qualify-quality", output)
    result = json.loads((output / "result.json").read_text())
    assert result["quality_controls_passed"] and result["observation_complete"]
    assert not result["reviewer_qualification_passed"] and not result["D70_complete"] and result["human_MOS"] is None
    frozen = json.loads((output / "freeze.json").read_text())
    assert frozen["parent_metadata_sha256"] == parent.sha((packet.prepared / "parent-only.json").read_bytes())
    assert frozen["prompt"] is None and frozen["task_protocol"]["comparison"]["maximum_new_tokens"] == 16
    with pytest.raises(FileExistsError):
        controller.run("qualify-quality", output)
