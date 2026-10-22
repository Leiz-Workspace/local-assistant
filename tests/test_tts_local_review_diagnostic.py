"""Test proposed factual diagnostic isolation, held-out provenance and first-response accounting without original-model inference."""

import copy
import hashlib
import json
from contextlib import nullcontext
from types import SimpleNamespace

import numpy as np
import pytest

from scripts import tts_local_review as controller
from scripts import tts_local_review_diagnostic as diagnostic
from scripts import tts_local_review_worker as worker


@pytest.mark.parametrize("raw,expected", [("yes", "yes"), ("\nno\n", "no"), ("uncertain", "uncertain")])
def test_exact_factual_answers_only(raw, expected):
    """Accept canonical factual labels while preserving uncertainty rather than relabelling it as known speech/no-speech."""
    assert diagnostic.parse_answer(raw) == expected


@pytest.mark.parametrize("raw", ["Yes", "yes.", "There is speech", "{'presence': 'speech'}", "", None])
def test_no_output_coercion_or_old_json_repair(raw):
    """Refuse prose, punctuation, Python dictionaries and missing content instead of repairing a failed reviewer."""
    with pytest.raises(ValueError, match="diagnostic_answer"):
        diagnostic.parse_answer(raw)


def authored_sources(project, monkeypatch):
    """Provide tiny authored source fixtures instead of reading the real held-out public corpus during unit tests."""
    directory = project / "data/backups/d68-asr-evaluation/prepared"
    directory.mkdir(parents=True)
    sources = {}
    for index, identity in enumerate(["en_us-0001", "vi_vn-0001"]):
        values = np.full(16000 + index * 8000, 0.1 + index * 0.1, dtype="<f4")
        raw = values.tobytes()
        (directory / (identity + ".f32")).write_bytes(raw)
        sources[identity] = (len(values), hashlib.sha256(raw).hexdigest())
    monkeypatch.setattr(diagnostic, "SOURCES", sources)
    monkeypatch.setattr(worker, "ALLOWED_EXECUTION_MODES", frozenset({"prepare-diagnose"}))
    return directory


def test_packet_is_private_blind_exclusive_and_source_bound(tmp_path, monkeypatch):
    """Freeze four deterministic authored controls without references or expected labels in worker requests, retaining complete source bits."""
    project, root = tmp_path / "project", tmp_path / "evaluation"
    root.mkdir()
    directory = authored_sources(project, monkeypatch)
    before = {path.name: path.read_bytes() for path in directory.iterdir()}
    diagnostic.prepare_packet(root, project, controller.publish_json)
    packet = root / "diagnostic-103"
    request = json.loads((packet / "request.json").read_text())
    parent = json.loads((packet / "parent-only.json").read_text())
    worker.validate_request(request)
    assert len(request["cases"]) == 4 and parent["question"] == diagnostic.QUESTION
    assert set(request) == {"mode", "cases"} and packet.stat().st_mode & 0o777 == 0o700
    assert sorted(row["expected"] for row in parent["mapping"]) == ["no", "no", "yes", "yes"]
    for row in request["cases"]:
        assert set(row) == {"id", "sample_count", "sha256"}
        signal = packet / "inputs" / (row["id"] + ".f32")
        assert signal.stat().st_mode & 0o777 == 0o600
        assert hashlib.sha256(signal.read_bytes()).hexdigest() == row["sha256"]
    assert {path.name: path.read_bytes() for path in directory.iterdir()} == before
    with pytest.raises(FileExistsError):
        diagnostic.prepare_packet(root, project, controller.publish_json)


def test_bad_heldout_source_cannot_create_a_packet(tmp_path, monkeypatch):
    """Reject changed source bytes before creating model inputs or publishing a seemingly frozen diagnostic."""
    project, root = tmp_path / "project", tmp_path / "evaluation"
    root.mkdir()
    directory = authored_sources(project, monkeypatch)
    (directory / "en_us-0001.f32").write_bytes(b"changed")
    with pytest.raises(ValueError, match="heldout_source"):
        diagnostic.prepare_packet(root, project, controller.publish_json)
    assert list(root.iterdir()) == []


def test_unapproved_diagnostic_paths_remain_blocked(tmp_path):
    """Keep preparation, controller execution and retained-runtime inference blocked under the current load-only owner permission."""
    with pytest.raises(ValueError, match="owner_load_only_scope"):
        diagnostic.prepare_packet(tmp_path, tmp_path, controller.publish_json)
    with pytest.raises(ValueError, match="owner_load_only_scope"):
        controller.run("diagnose", tmp_path / "run")
    with pytest.raises(ValueError, match="owner_load_only_scope"):
        object.__new__(worker.Runtime).diagnose({})
    assert list(tmp_path.iterdir()) == []


def observations():
    """Build complete authored response receipts without claiming that a real model heard any audio."""
    request = dict(mode="diagnose", cases=[dict(id=f"clip-{index+1:02d}", sample_count=16000, sha256="a" * 64) for index in range(4)])
    events = [dict(event="ready")]
    for row in request["cases"]:
        events.append(dict(event="diagnostic", id=row["id"], sample_count=16000, source_sha256=row["sha256"], sample_rate=16000, generation_complete=True, question=diagnostic.QUESTION, maximum_new_tokens=16, generated_token_ids=[100, 151645], audio_tokens=2, feature_frames=3, feature_shape=[1, 128, 3], feature_sha256="b" * 64, raw_text="yes", answer="yes", parse_error=None))
    events.append(dict(event="complete"))
    return request, events


@pytest.mark.parametrize("change", ["missing", "duplicate", "hash", "eos", "raw", "frames", "question", "features", "review"])
def test_missing_unconditioned_or_repaired_diagnostics_fail(change):
    """Reject incomplete coverage, altered sources, absent EOS/features, foreign prompts and accidental naturalness-review events."""
    request, events = observations()
    assert diagnostic.audit_events(request, events)
    bad = copy.deepcopy(events)
    if change == "missing": bad.pop(1)
    elif change == "duplicate": bad[2]["id"] = bad[1]["id"]
    elif change == "hash": bad[1]["source_sha256"] = "c" * 64
    elif change == "eos": bad[1]["generated_token_ids"] = [100]
    elif change == "raw": bad[1]["raw_text"] = "yes."
    elif change == "frames": bad[1]["feature_frames"] = 0
    elif change == "question": bad[1]["question"] = "favourable alternative"
    elif change == "features": bad[1]["feature_sha256"] = "missing"
    else: bad.append(dict(event="review"))
    assert not diagnostic.audit_events(request, bad)


def test_factual_generation_retains_raw_eos_and_audio_provenance(monkeypatch, capsys):
    """Exercise the actual new worker method using tiny authored processor/model doubles and require16tokens/native EOS without neural imports."""
    class Features:
        """Expose a tiny authored feature array through the same zero-copy-facing interface used by the native processor."""
        shape = (1, 128, 3)

        def numpy(self):
            """Return an authored float32 feature fixture, not a real audio-encoder result."""
            return np.zeros(self.shape, dtype=np.float32)

    class Inputs(dict):
        """Emulate processor input movement without allocating neural parameters."""

        def to(self, device, dtype):
            """Require the retained CPU BF16 execution plan in the authored test."""
            assert device == "cpu" and dtype == "fixture_BF16"
            return self

    class Processor:
        """Record the fixed question and supplied waveform while returning authored feature/token fixtures."""

        def apply_chat_template(self, conversation, **kwargs):
            """Verify diagnostic scope without exposing parent-only expected answers or source IDs."""
            assert conversation[1]["content"][1]["text"] == diagnostic.QUESTION
            return "authored template"

        def __call__(self, **kwargs):
            """Preserve the complete authored waveform and expected16k input rate."""
            assert len(kwargs["audio"][0]) == 16000 and kwargs["sampling_rate"] == 16000
            return Inputs(input_features=Features(), input_ids=np.array([[1, 151646, 2]]), feature_attention_mask=np.ones((1, 3), dtype=int))

        def decode(self, tokens, **kwargs):
            """Return one authored canonical response while checking retained actual generated token boundaries."""
            assert tokens == [100, 151645]
            return "yes"

    def generate(**kwargs):
        """Emulate deterministic generation and reject altered length/stop parameters before returning authored tokens."""
        assert kwargs["max_new_tokens"] == 16 and kwargs["eos_token_id"] == 151645 and not kwargs["do_sample"]
        return np.array([[1, 151646, 2, 100, 151645]])

    monkeypatch.setattr(worker, "ALLOWED_EXECUTION_MODES", frozenset({"diagnose"}))
    monkeypatch.setattr(worker, "waveform", lambda row: np.zeros(16000, dtype=np.float32))
    runtime = object.__new__(worker.Runtime)
    runtime.processor = Processor()
    runtime.torch = SimpleNamespace(bfloat16="fixture_BF16", inference_mode=nullcontext)
    runtime.model = SimpleNamespace(config=SimpleNamespace(audio_token_index=151646), generate=generate)
    runtime.boundaries = dict(eos_token_id=151645, pad_token_id=151643)
    runtime.diagnose(dict(id="clip-01", sha256="a" * 64))
    event = json.loads(capsys.readouterr().out)
    assert event["event"] == "diagnostic" and event["answer"] == "yes" and event["generation_complete"]
    assert event["sample_count"] == 16000 and event["maximum_new_tokens"] == 16
    assert "naturalness" not in event and "qualification_passed" not in event
