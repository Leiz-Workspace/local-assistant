"""Test frozen-policy multi-clause validation, semantic/source guards and bounded original native lifecycle."""

import asyncio
import base64
import copy
import json
from types import SimpleNamespace

import numpy as np
import pytest

from benchmarks.scripts import vi_truc_ly_validation as trial
from benchmarks.scripts import vi_truc_ly_validation_worker as worker
from benchmarks.scripts.vi_api_stress_worker import SOURCE, TARGET
from benchmarks.scripts.vi_us_terms_worker import TERMS
from benchmarks.tests.test_vi_speech_review import MediaParser

REFS = {
    "think": "θˈɪŋk",
    "this": "ðˈɪs",
    "right": "ɹˈaɪt",
    "ship": "ʃˈɪp",
    "sheep": "ʃˈiːp",
    "light": "lˈaɪt",
}


def frontend_fixture():
    """Create independent public semantic/phoneme fixtures without loading SDK or private model assets."""
    rows = trial.source_packet()
    for row in rows:
        text = " ".join(row["required_pieces"]) or row["rendered_text"]
        if row["id"] in {"mixed-time", "vi-context"}:
            chunks = [
                text.rstrip("?.") + ".",
                "<en>a p i</en>?" if row["expected_api"] else "tiếp theo.",
            ]
        else:
            chunks = [text.rstrip("?.") + ("?" if row["question"] else ".")]
        if row["expected_api"] and row["id"] != "mixed-time":
            chunks[0] = "<en>a p i</en> " + chunks[0]
        plans = []
        for index, chunk in enumerate(chunks):
            raw = "ˈaɪ " if row["initial_i"] and index == 0 else ""
            if index == 0:
                raw += " ".join(
                    [REFS[r] for r in row["references"]]
                    + [TERMS[t][0] for t in row["expected_terms"]]
                )
            if "<en>a p i</en>" in chunk:
                raw += " " + SOURCE
            raw = (raw.strip() or "fixture") + ("?" if chunk.endswith("?") else ".")
            plans.append(worker.chunk_plan(chunk, raw, lambda ph: 100))
        row.update(
            chunks=chunks,
            gaps=["sentence"] * (len(chunks) - 1),
            phone_plans=plans,
            unknown_tokens=0,
            reference_phones={r: REFS[r] for r in row["references"]},
        )
    return dict(rows=rows, model_calls=0, voice="Trúc Ly")


def test_new_sources_keep_old_renderer_and_are_not_replayed_old_sentences():
    """Preserve accepted question/date rendering and avoid adding an old test sentence as supposed new evidence."""
    rows = trial.source_packet()
    assert len(rows) == 10 and len({r["source_text"] for r in rows}) == 10
    assert all(
        r["source_text"] not in {c["text"] for c in trial.previous.CASES} for r in rows
    )
    time = next(r for r in rows if r["id"] == "mixed-time")
    assert (
        "chín giờ mười lăm phút" in time["rendered_text"]
        and "hai nghìn không trăm hai mươi sáu" in time["rendered_text"]
    )
    assert time["rendered_text"].endswith("?") and "API" in time["rendered_text"]
    assert not any(e["kind"] == "lexicon" for r in rows for e in r["render_edits"])


def test_policy_uses_only_frozen_edits_and_accepts_already_target_forms():
    """Retain original API/US dictionaries and shared cap rather than tuning them for a new sentence."""
    raw = "pˈaɪθən " + SOURCE + " sˈɜːvɚ?"
    plan = worker.chunk_plan("python <en>a p i</en> server?", raw, len)
    assert plan["us"] == "pˈaɪθɑːn " + TARGET + " sˈɜːɹvɚ?"
    assert plan["shared_cap"] == len(raw) and plan["lexical_counts"] == dict(
        python=1, github=0, server=1
    )
    plan = worker.chunk_plan("python.", "pˈaɪθɑːn.", len)
    assert (
        plan["same_input"]
        and plan["edits"] == []
        and plan["lexical_counts"]["python"] == 1
    )
    with pytest.raises(ValueError, match="marker_binding"):
        worker.chunk_plan("python API?", raw, len)


def test_frontend_guards_semantics_I_question_references_and_source_drift():
    """Reject wrong values, I-to-i, lost questions and mismatched rendered input before any model load."""
    front = frontend_fixture()
    rows = trial.packet(front)
    assert len(rows) == 10
    assert sum(len(r["phone_plans"]) for r in rows) == 12
    for kind in ("number", "I", "question", "reference", "source", "count"):
        bad = copy.deepcopy(front)
        if kind == "number":
            bad["rows"][7]["chunks"] = ["mười ba sản phẩm."]
        elif kind == "I":
            bad["rows"][0]["phone_plans"][0]["us"] = "ˈi "
        elif kind == "question":
            bad["rows"][2]["phone_plans"][0]["us"] = "changed."
        elif kind == "reference":
            bad["rows"][1]["reference_phones"]["ship"] = "wrong"
        elif kind == "source":
            bad["rows"][0]["rendered_text"] = "changed"
        else:
            bad["rows"][2]["phone_plans"][0]["lexical_counts"]["server"] = 0
        with pytest.raises(ValueError):
            trial.packet(bad)


def test_packet_bound_adapter_preserves_multichunk_order_joining_and_reference():
    """Use the original native objects, speaker/code objects and decoding controls for all approved chunks."""
    front = frontend_fixture()
    row = next(r for r in front["rows"] if r["id"] == "mixed-time")
    speaker = np.array([0.1], dtype=np.float32)
    codes = np.array([[1]], dtype=np.int64)
    waves = [np.array([0.1, 0.2], dtype=np.float32), np.array([0.3], dtype=np.float32)]
    calls = []

    def resolve(voice, reference, denoise, use_codes):
        """Require the existing Truc Ly reference path without cloning or reference ablation."""
        assert voice == "Trúc Ly" and reference is None and denoise is use_codes is True
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
    adapter = worker.ValidationAdapter(wrapper, front["rows"], deps)
    result = adapter.infer(row["rendered_text"], voice="Trúc Ly")
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
        adapter.infer(row["rendered_text"], voice="Ngọc Huyền")
    with pytest.raises(ValueError, match="unapproved_text"):
        adapter.infer("unlisted", voice="Trúc Ly")
    assert len(calls) == 2


def test_native_rejects_actual_plan_voice_cap_and_chunk_hash_drift(tmp_path):
    """Verify genuine native trace bindings independently of a successful response flag."""
    row = trial.packet(frontend_fixture())[0]
    raw = b"fixture"
    voice = dict(speaker_sha256="s", reference_codes_sha256="r")
    (tmp_path / (row["id"] + "-chunk-0.f32")).write_bytes(raw)
    trace = dict(
        validation_case=row["id"],
        validation_plans=row["phone_plans"],
        voice_binding=voice,
        term_mode="us",
        chunks=row["chunks"],
        gaps=row["gaps"],
        phonemes=[p["us"] for p in row["phone_plans"]],
        native_chunk_sha256=[trial.Q.lifecycle.sha(raw)],
    )
    native = dict(
        prosody_trace=trace,
        generation_complete=True,
        chunks=[dict(eos=True, frames=10)],
    )
    trial.verify_native(row, native, tmp_path, voice)
    for kind in ("voice", "cap", "hash", "order"):
        bad = copy.deepcopy(native)
        if kind == "voice":
            bad["prosody_trace"]["voice_binding"]["speaker_sha256"] = "other"
        elif kind == "cap":
            bad["chunks"][0]["frames"] = 101
        elif kind == "hash":
            bad["prosody_trace"]["native_chunk_sha256"][0] = "wrong"
        else:
            bad["prosody_trace"]["phonemes"] = ["wrong"]
        with pytest.raises(ValueError):
            trial.verify_native(row, bad, tmp_path, voice)


def test_namespace_keeps_model_free_probe_and_read_only_SHA_bound_packet(tmp_path):
    """Expose the approved packet only to the offline native worker and refuse an unbound entry point."""
    out = tmp_path / "out"
    out.mkdir(mode=0o700)
    front = tmp_path / "front.json"
    front.write_text("{}")
    args = trial.command(out, probe=True)
    mounts = {args[i + 2] for i, v in enumerate(args) if v == "--ro-bind"}
    assert (
        "/model" not in mounts
        and "/hf/hub" not in mounts
        and "/approved-validation.json" not in mounts
    )
    args = trial.command(out, frontend=front, expected_sha="a" * 64)
    assert (
        "/approved-validation.json" in args
        and args[-2:] == ["--run", "a" * 64]
        and "--unshare-all" in args
    )
    with pytest.raises(ValueError, match="mount_required"):
        trial.command(out)


def test_grouped_media_keeps_missing_slots_and_exact_native_bytes():
    """Publish the declared4/3/3language groups without scripts, autoplay or fabricated missing clips."""
    rows = trial.packet(frontend_fixture())
    audio = {r["id"]: r["id"].encode() for r in rows}
    for group, count in [(None, 10), ("EN", 4), ("MIXED", 3), ("VI", 3)]:
        parser = MediaParser()
        parser.feed(trial.render_review(rows, audio, group))
        assert (
            len(parser.media) == count
            and not parser.forbidden
            and all(
                "autoplay" not in r and r["preload"] == "none" for r in parser.media
            )
        )
        assert all(
            base64.b64decode(r["src"].split(",", 1)[1]) in audio.values()
            for r in parser.media
        )
    assert (
        trial.render_review(rows, {}).count("Chưa có clip hoàn chỉnh: UNATTEMPTED")
        == 10
    )
    with pytest.raises(ValueError):
        trial.render_review(rows[:-1], audio)


@pytest.mark.asyncio
async def test_consumed_root_prevents_replay(tmp_path):
    """Reject a retained study marker before reading private artifacts or creating a model worker."""
    (tmp_path / "execution-freeze.json").write_text("{}")
    with pytest.raises(ValueError, match="already_attempted"):
        await trial.run(tmp_path)


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [None, ValueError, asyncio.CancelledError])
async def test_request_chunk_budget_failure_stop_and_join(
    tmp_path, monkeypatch, failure
):
    """Exercise the real controller's ten-request/twelve-chunk path and fatal first response without any model."""
    project = tmp_path / "project"
    evidence = project / "docs/evidence"
    evidence.mkdir(parents=True)
    (evidence / "d74-truc-validation-authorization.json").write_text(
        '{"authorized":true}'
    )
    hashes = {}
    for name in trial.SOURCES:
        p = project / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text('"""Fixture."""\n')
        hashes[name] = trial.Q.assets.digest(p)
    front = frontend_fixture()
    (tmp_path / "probe/native").mkdir(parents=True)
    (tmp_path / "probe/native/frontend.json").write_text(json.dumps(front))
    (tmp_path / "software-verification.json").write_text(
        json.dumps(dict(status="PASS", source_sha256=hashes))
    )
    monkeypatch.setattr(trial.Q.assets, "PROJECT", project)
    monkeypatch.setattr(trial.Q.assets, "ROOT", tmp_path)
    monkeypatch.setattr(
        trial,
        "verify_previous",
        lambda: {"speaker_sha256": "s", "reference_codes_sha256": "r"},
    )
    monkeypatch.setattr(trial.Q.lifecycle, "prepared_integrity", lambda r: None)
    monkeypatch.setattr(trial.Q.lifecycle, "verify_originals", lambda: {"fixture": 1})
    monkeypatch.setattr(trial.Q.lifecycle, "local_state", lambda: {"native_pids": []})
    monkeypatch.setattr(trial, "verify_native", lambda *args: None)
    calls = []
    closed = []

    class Worker:
        """Return public first-attempt responses and explicit joined-cleanup observations."""

        def __init__(self, *args):
            """Bind a fake initially clean worker without a process."""
            self.failure = None

        async def start(self):
            """Represent readiness without loading any model."""
            return self

        async def call(self, message):
            """Record one request and optionally fail or cancel before further dispatch."""
            calls.append(message)
            if failure:
                self.failure = "fixture"
                raise failure("fixture")
            row = next(r for r in front["rows"] if r["id"] == message["id"])
            return dict(chunks=[{}] * len(row["phone_plans"]))

        async def close(self, force):
            """Record original owned-worker retirement under every result path."""
            closed.append(True)

    monkeypatch.setattr(trial, "ValidationWorker", Worker)
    result = await trial.run(tmp_path)
    assert len(calls) == result["tts_attempts"] == (1 if failure else 10)
    assert result["completed_inner_chunks"] == (0 if failure else 12) and result[
        "unattempted"
    ] == (9 if failure else 0)
    assert result["status"] == (
        "STOPPED_NO_RETRY" if failure else "TRUC_CONTEXTS_COMPLETE_ACOUSTIC_UNVERIFIED"
    )
    assert (
        closed == [True]
        and result["baseline_restored"]
        and result["retries"] == 0
        and all(r["voice"] == "Trúc Ly" for r in calls)
    )
