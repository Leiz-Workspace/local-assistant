"""Test exact-corpus Ngoc Huyen admission, original voice generation, bounded execution and genuine review coverage."""

import asyncio
import base64
import copy
import json
from types import SimpleNamespace

import numpy as np
import pytest

from benchmarks.scripts import vi_ngoc_huyen_validation as trial
from benchmarks.scripts import vi_ngoc_huyen_validation_worker as worker
from benchmarks.tests.test_vi_speech_review import MediaParser
from benchmarks.tests.test_vi_truc_ly_validation import frontend_fixture


def test_matched_packet_changes_only_voice_and_keeps_I_API_caps_and_semantics():
    """Use the exact original measured fields without treating another voice as a pronunciation correction."""
    frontend = frontend_fixture()
    before = copy.deepcopy(frontend)
    original = trial.retained.packet(frontend)
    rows = trial.packet_rows(frontend)
    assert frontend == before and len(rows) == 10
    assert rows == [dict(row, voice="Ngọc Huyền") for row in original]
    assert sum(len(row["phone_plans"]) for row in rows) == 12
    assert rows[0]["phone_plans"][0]["us"].startswith("ˈaɪ")
    with pytest.raises(ValueError, match="packet_voice"):
        worker.validate_packet(dict(voice="Trúc Ly", rows=rows))
    rows[0]["voice"] = "Trúc Ly"
    with pytest.raises(ValueError, match="packet_voice"):
        worker.validate_packet(dict(voice="Ngọc Huyền", rows=rows))


def test_prepared_packet_refuses_semantic_phone_voice_and_source_binding_drift(
    tmp_path, monkeypatch
):
    """Reject modified prepared observations before model startup even when their superficial schema is valid."""
    old = tmp_path / "old"
    (old / "probe/native").mkdir(parents=True)
    frontend = frontend_fixture()
    path = old / "probe/native/frontend.json"
    path.write_text(json.dumps(frontend))
    monkeypatch.setattr(trial.retained, "ROOT", old)
    approved = dict(
        voice="Ngọc Huyền",
        rows=trial.packet_rows(frontend),
        original_frontend_sha256=trial.Q.assets.digest(path),
    )
    out = tmp_path / "new"
    out.mkdir()
    packet = out / "approved-packet.json"
    packet.write_text(json.dumps(approved))
    assert trial.read_packet(out) == approved["rows"]
    for kind in ("source", "phone", "binding", "voice"):
        bad = copy.deepcopy(approved)
        if kind == "source":
            bad["rows"][0]["source_text"] = "different"
        elif kind == "phone":
            bad["rows"][0]["phone_plans"][0]["us"] += " extra"
        elif kind == "binding":
            bad["original_frontend_sha256"] = "other"
        else:
            bad["voice"] = "Trúc Ly"
        packet.write_text(json.dumps(bad))
        with pytest.raises(ValueError):
            trial.read_packet(out)


def test_admission_requires_first_exact_ID_text_voice_and_request_budget():
    """Refuse cross-case text, repeated IDs and wrong presets without calling the model."""
    rows = trial.packet_rows(frontend_fixture())
    first = rows[0]
    message = dict(
        op="synthesize", id=first["id"], text=first["rendered_text"], voice="Ngọc Huyền"
    )
    worker.admit(message, rows, set())
    worker.admit(dict(op="close"), rows, set())
    for change in [
        dict(id="unlisted"),
        dict(text=rows[1]["rendered_text"]),
        dict(voice="Trúc Ly"),
    ]:
        with pytest.raises(ValueError):
            worker.admit(dict(message, **change), rows, set())
    with pytest.raises(ValueError):
        worker.admit(message, rows, {first["id"]})
    with pytest.raises(ValueError):
        worker.admit(message, rows, {str(i) for i in range(10)})


def test_namespace_mounts_new_worker_and_read_only_packet_without_changing_original_entrypoint(
    tmp_path,
):
    """Retain offline CPU/model guards while mounting the new voice boundary instead of altering frozen source."""
    output = tmp_path / "out"
    output.mkdir(mode=0o700)
    packet = tmp_path / "packet.json"
    packet.write_text("{}")
    args = trial.command(output, packet, "a" * 64)
    assert "--unshare-all" in args and args[-2:] == ["--run", "a" * 64]
    assert args[args.index("/venv/bin/python") + 1].endswith(
        "vi_ngoc_huyen_validation_worker.py"
    )
    index = args.index("/approved-validation.json")
    assert args[index - 2 : index] == ["--ro-bind", str(packet)]
    assert "/app/benchmarks/scripts/vi_truc_ly_validation_worker.py" in args
    with pytest.raises(ValueError):
        trial.command(output, packet, "invalid")


def test_authority_requires_voice_budget_and_exact_bound_documents(
    tmp_path, monkeypatch
):
    """Refuse unapproved scope or altered decision artifacts before loading a worker."""
    authority = tmp_path / trial.AUTHORITY
    authority.parent.mkdir(parents=True)
    decision = tmp_path / "decision.md"
    decision.write_text("Approved fixed scope")
    monkeypatch.setattr(trial.Q.assets, "PROJECT", tmp_path)
    receipt = dict(
        authorized=True,
        voice="Ngọc Huyền",
        tts_ceiling=10,
        inner_chunks_ceiling=16,
        retries=0,
        bindings={"decision.md": trial.Q.assets.digest(decision)},
    )
    authority.write_text(json.dumps(receipt))
    assert trial.authorization() == authority
    for change in [
        dict(authorized=False),
        dict(voice="Trúc Ly"),
        dict(tts_ceiling=11),
        dict(retries=1),
    ]:
        authority.write_text(json.dumps(dict(receipt, **change)))
        with pytest.raises(ValueError):
            trial.authorization()
    authority.write_text(json.dumps(receipt))
    decision.write_text("Altered scope")
    with pytest.raises(ValueError, match="authority_drift"):
        trial.authorization()


def test_review_labels_only_Ngoc_and_preserves_every_real_or_missing_slot():
    """Keep exact original WAV bytes with4/3/3groups and explicit missing outcomes, no scripts or autoplay."""
    rows = trial.packet_rows(frontend_fixture())
    audio = {row["id"]: row["id"].encode() for row in rows}
    for group, count in [(None, 10), ("EN", 4), ("MIXED", 3), ("VI", 3)]:
        text = trial.render_review(rows, audio, group)
        parser = MediaParser()
        parser.feed(text)
        assert len(parser.media) == count and not parser.forbidden
        assert "Ngọc Huyền" in text and "Trúc Ly" not in text
        assert all("autoplay" not in item for item in parser.media)
        assert all(
            base64.b64decode(item["src"].split(",", 1)[1]) in audio.values()
            for item in parser.media
        )
    assert (
        trial.render_review(rows, {}).count("Chưa có clip hoàn chỉnh: UNATTEMPTED")
        == 10
    )
    rows[0]["voice"] = "Trúc Ly"
    with pytest.raises(ValueError, match="review_voice"):
        trial.render_review(rows, audio)


def test_packet_bound_adapter_preserves_multichunk_order_joining_and_reference():
    """Use the original native objects, speaker/code objects and decoding controls for all approved chunks."""
    front = frontend_fixture()
    row = next(r for r in front["rows"] if r["id"] == "mixed-time")
    speaker = np.array([0.1], dtype=np.float32)
    codes = np.array([[1]], dtype=np.int64)
    waves = [np.array([0.1, 0.2], dtype=np.float32), np.array([0.3], dtype=np.float32)]
    calls = []

    def resolve(voice, reference, denoise, use_codes):
        """Require the existing Ngoc Huyen reference path without cloning or reference ablation."""
        assert (
            voice == "Ngọc Huyền" and reference is None and denoise is use_codes is True
        )
        return speaker, codes

    def phonemize(text, **kwargs):
        """Supply exact frozen original phones without a model or SDK import."""
        return row["phone_plans"][row["chunks"].index(text)]["raw"]

    def infer(**kwargs):
        """Record exact native generation arguments for both independent chunks."""
        calls.append(kwargs)
        return waves[len(calls) - 1]

    def join(chunks, rate, silence_ps):
        """Verify ordered original arrays reach the unchanged joining dependency."""
        assert (
            all(a is b for a, b in zip(chunks, waves, strict=True))
            and rate == 48000
            and silence_ps == [0.2]
        )
        return np.concatenate(chunks)

    deps = dict(
        normalize=lambda t, **kw: t,
        split=lambda t: row["chunks"],
        pack=lambda r, **kw: r,
        classify=lambda t: "sentence",
        phonemize=phonemize,
        frame_cap=lambda p: 100,
        repetition_window=64,
        pauses=lambda g: [0.2],
        join=join,
    )
    wrapper = SimpleNamespace(
        engine=SimpleNamespace(infer=infer),
        _resolve_ref=resolve,
        _apply_watermark=lambda value: value,
        sample_rate=48000,
    )
    adapter = worker.NgocHuyenAdapter(wrapper, front["rows"], deps)
    result = adapter.infer(row["rendered_text"], voice="Ngọc Huyền")
    assert np.array_equal(result, np.concatenate(waves)) and len(calls) == 2
    for call in calls:
        assert (
            call["speaker_emb"] is speaker
            and call["ref_codes"] is codes
            and call["use_ref_codes"] is True
        )
        assert (
            call["temperature"],
            call["top_k"],
            call["top_p"],
            call["repetition_penalty"],
            call["max_new_frames"],
        ) == (0.8, 25, 0.95, 1.2, 100)
    assert adapter.last_trace["validation_plans"] == row["phone_plans"]
    with pytest.raises(ValueError, match="voice_only"):
        adapter.infer(row["rendered_text"], voice="Trúc Ly")
    with pytest.raises(ValueError, match="unapproved_text"):
        adapter.infer("unlisted", voice="Ngọc Huyền")
    assert len(calls) == 2


@pytest.mark.asyncio
async def test_consumed_root_refuses_a_second_attempt_before_authorization(tmp_path):
    """Prevent replay of a retained first result before any private read or model startup."""
    (tmp_path / "execution-freeze.json").write_text("{}")
    with pytest.raises(ValueError, match="already_attempted"):
        await trial.run(tmp_path)


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [None, ValueError, asyncio.CancelledError])
async def test_ten_requests_original_chunk_budget_first_failure_and_join(
    tmp_path, monkeypatch, failure
):
    """Run the real controller with synthetic responses to prove exact preset scope and stop/join behavior."""
    project = tmp_path / "project"
    project.mkdir()
    authority = project / "authority.json"
    authority.write_text("{}")
    hashes = {}
    for name in trial.SOURCES:
        p = project / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text('"""Fixture."""\n')
        hashes[name] = trial.Q.assets.digest(p)
    rows = trial.packet_rows(frontend_fixture())
    (tmp_path / "approved-packet.json").write_text("{}")
    (tmp_path / "software-verification.json").write_text(
        json.dumps(dict(status="PASS", source_sha256=hashes))
    )
    monkeypatch.setattr(trial.Q.assets, "PROJECT", project)
    monkeypatch.setattr(trial.Q.assets, "ROOT", tmp_path)
    monkeypatch.setattr(trial, "authorization", lambda: authority)
    monkeypatch.setattr(
        trial,
        "verify_previous",
        lambda: dict(speaker_sha256="s", reference_codes_sha256="r"),
    )
    monkeypatch.setattr(trial, "read_packet", lambda root: copy.deepcopy(rows))
    monkeypatch.setattr(trial.Q.lifecycle, "prepared_integrity", lambda root: None)
    monkeypatch.setattr(trial.Q.lifecycle, "verify_originals", lambda: {"fixture": 1})
    monkeypatch.setattr(trial.Q.lifecycle, "local_state", lambda: {"native_pids": []})
    monkeypatch.setattr(trial.retained, "verify_native", lambda *args: None)
    calls, closed = [], []

    class FakeWorker:
        """Expose only first synthetic outcomes and the controller's owned cleanup request."""

        def __init__(self, *args):
            """Start in an unused state without any process or model."""
            self.failure = None

        async def start(self):
            """Represent exact readiness without native execution."""
            return self

        async def call(self, message):
            """Record the first admitted request and optional fatal/cancelled outcome."""
            calls.append(message)
            if failure:
                self.failure = "fixture"
                raise failure("fixture")
            row = next(row for row in rows if row["id"] == message["id"])
            return dict(chunks=[{}] * len(row["phone_plans"]))

        async def close(self, force):
            """Confirm owned cleanup even after first failure or cancellation."""
            closed.append(True)

    monkeypatch.setattr(trial, "ValidationWorker", FakeWorker)
    result = await trial.run(tmp_path)
    assert len(calls) == result["tts_attempts"] == (1 if failure else 10)
    assert result["completed_inner_chunks"] == (0 if failure else 12)
    assert result["unattempted"] == (9 if failure else 0)
    assert result["status"] == (
        "STOPPED_NO_RETRY" if failure else "NGOC_CONTEXTS_COMPLETE_ACOUSTIC_UNVERIFIED"
    )
    assert closed == [True] and result["baseline_restored"] and result["retries"] == 0
    assert all(message["voice"] == "Ngọc Huyền" for message in calls)
