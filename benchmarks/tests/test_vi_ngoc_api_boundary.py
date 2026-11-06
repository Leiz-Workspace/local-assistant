"""Test the one-case API boundary edit, retained budget/native objects, packet isolation and first-failure lifecycle."""

import asyncio
import base64
import copy
import json
from types import SimpleNamespace

import numpy as np
import pytest

from benchmarks.scripts import vi_ngoc_api_boundary_trial as trial
from benchmarks.scripts import vi_ngoc_api_boundary_worker as worker
from benchmarks.tests.test_vi_speech_review import MediaParser
from benchmarks.tests.test_vi_truc_ly_validation import frontend_fixture


def fixture_packets():
    """Supply public original plans and independent no-weights observation metadata without private assets."""
    rows = trial.retained.packet_rows(frontend_fixture())
    original = dict(voice=worker.VOICE, rows=rows, description="Public fixture")
    row = next(row for row in rows if row["id"] == worker.SELECTED)
    observed = dict(
        selected_id=worker.SELECTED,
        model_calls=0,
        unknown_tokens=0,
        native_dictionary=worker.TARGET + ".",
        original_row=copy.deepcopy(row),
        candidate_plan=worker.compact_plan(row["phone_plans"][0], lambda text: 100),
    )
    return original, observed


def test_exact_boundary_change_keeps_all_non_API_phones_and_retained_cap():
    """Remove exactly two spaces without a guessed vowel/stress rewrite or a relaxed retained allowance."""
    old, probe = fixture_packets()
    original = probe["original_row"]["phone_plans"][0]
    plan = worker.compact_plan(original, lambda text: 100)
    assert plan["us"] == original["us"].replace(worker.SOURCE, worker.TARGET, 1)
    assert plan["us"].replace(worker.TARGET, worker.SOURCE, 1) == original["us"]
    assert (
        len(original["us"]) - len(plan["us"]) == 2
        and plan["shared_cap"] == original["shared_cap"] == 100
    )
    assert plan["edits"] == original["edits"] and plan["api_replacements"] == 1
    with pytest.raises(ValueError, match="cap_mismatch"):
        worker.compact_plan(original, lambda text: 99)
    for text in [
        original["us"] + worker.SOURCE,
        original["us"].replace(worker.SOURCE, "missing"),
        plan["us"],
    ]:
        with pytest.raises(ValueError, match="exact_span"):
            worker.compact_plan(dict(original, us=text), lambda text: 100)


def test_compile_changes_only_one_row_and_rejects_misbound_probe_or_plan():
    """Keep nine metadata rows untouched and bind the selected edit to measured original case/dictionary/cap."""
    original, probe = fixture_packets()
    before = copy.deepcopy(original)
    packet = trial.compile_packet(original, probe)
    assert original == before and packet["selected_id"] == worker.SELECTED
    for old, new in zip(original["rows"], packet["rows"], strict=True):
        if old["id"] != worker.SELECTED:
            assert old == new
        else:
            assert dict(new, phone_plans=old["phone_plans"]) == old
            assert new["phone_plans"] == [probe["candidate_plan"]]
    for kind in ["unknown", "dictionary", "source", "plan"]:
        bad = copy.deepcopy(probe)
        if kind == "unknown":
            bad["unknown_tokens"] = 1
        elif kind == "dictionary":
            bad["native_dictionary"] = "other"
        elif kind == "source":
            bad["original_row"]["rendered_text"] = "other"
        else:
            bad["candidate_plan"]["us"] += " extra"
        with pytest.raises(ValueError):
            trial.compile_packet(original, bad)


def test_read_packet_refuses_rewritten_source_or_probe_after_preparation(
    tmp_path, monkeypatch
):
    """Rebuild the expected packet rather than trusting a mutable prepared document before model startup."""
    original, probe = fixture_packets()
    old = tmp_path / "old"
    old.mkdir()
    (old / "approved-packet.json").write_text(json.dumps(original))
    out = tmp_path / "new"
    (out / "probe/native").mkdir(parents=True)
    (out / "probe/native/frontend.json").write_text(json.dumps(probe))
    packet = trial.compile_packet(original, probe)
    (out / "approved-packet.json").write_text(json.dumps(packet))
    monkeypatch.setattr(trial.retained, "ROOT", old)
    assert trial.read_packet(out) == packet
    packet["rows"][0]["source_text"] = "different"
    (out / "approved-packet.json").write_text(json.dumps(packet))
    with pytest.raises(ValueError, match="packet_drift"):
        trial.read_packet(out)


def test_adapter_uses_original_Ngoc_reference_sampling_native_wave_and_one_chunk():
    """Preserve actual speaker/code objects and native waveform while changing only the declared acronym grouping."""
    original, probe = fixture_packets()
    packet = trial.compile_packet(original, probe)
    row = next(row for row in packet["rows"] if row["id"] == worker.SELECTED)
    before = probe["original_row"]
    speaker = np.array([0.1], dtype=np.float32)
    codes = np.array([[1]], dtype=np.int64)
    wave = np.array([0.1, 0.2], dtype=np.float32)
    calls = []

    def resolve(voice, reference, denoise, use_codes):
        """Keep the existing Ngoc Huyen preset with reference codes enabled."""
        assert (
            voice == worker.VOICE and reference is None and denoise is use_codes is True
        )
        return speaker, codes

    def phonemize(text, **kwargs):
        """Supply exact original normalized phones before the two-space candidate edit."""
        assert text == before["chunks"][0]
        return before["phone_plans"][0]["raw"]

    def infer(**kwargs):
        """Capture original generation arguments and return one genuine synthetic waveform object."""
        calls.append(kwargs)
        return wave

    def join(chunks, rate, silence_ps):
        """Prove the unmodified single native waveform reaches the original join boundary."""
        assert (
            len(chunks) == 1
            and chunks[0] is wave
            and rate == 48000
            and silence_ps == []
        )
        return chunks[0]

    deps = dict(
        normalize=lambda text, **kw: text,
        split=lambda text: row["chunks"],
        pack=lambda rows, **kw: rows,
        classify=lambda text: "sentence",
        phonemize=phonemize,
        frame_cap=lambda ph: 100,
        repetition_window=64,
        pauses=lambda gaps: [],
        join=join,
    )
    wrapper = SimpleNamespace(
        engine=SimpleNamespace(infer=infer),
        _resolve_ref=resolve,
        _apply_watermark=lambda value: value,
        sample_rate=48000,
    )
    adapter = worker.BoundaryAdapter(wrapper, packet["rows"], deps)
    assert adapter.infer(row["rendered_text"], voice=worker.VOICE) is wave
    call = calls[0]
    assert (
        call["speaker_emb"] is speaker
        and call["ref_codes"] is codes
        and call["use_ref_codes"] is True
    )
    assert (
        call["phonemes"] == probe["candidate_plan"]["us"]
        and call["max_new_frames"] == 100
    )
    assert (
        call["temperature"],
        call["top_k"],
        call["top_p"],
        call["repetition_penalty"],
        call["repetition_window"],
    ) == (0.8, 25, 0.95, 1.2, 64)
    assert adapter.last_trace["validation_plans"] == row["phone_plans"]
    with pytest.raises(ValueError):
        adapter.infer(row["rendered_text"], voice="Trúc Ly")
    with pytest.raises(ValueError):
        adapter.infer(packet["rows"][0]["rendered_text"], voice=worker.VOICE)
    assert len(calls) == 1


def test_admission_excludes_all_other_metadata_and_second_request():
    """Nine frozen rows remain metadata and never become silently queued candidate requests."""
    original, probe = fixture_packets()
    rows = trial.compile_packet(original, probe)["rows"]
    row = next(row for row in rows if row["id"] == worker.SELECTED)
    message = dict(
        op="synthesize",
        id=worker.SELECTED,
        text=row["rendered_text"],
        voice=worker.VOICE,
    )
    worker.admit_boundary(message, rows, set())
    worker.admit_boundary(dict(op="close"), rows, {worker.SELECTED})
    with pytest.raises(ValueError):
        worker.admit_boundary(message, rows, {worker.SELECTED})
    other = rows[0]
    with pytest.raises(ValueError):
        worker.admit_boundary(
            dict(message, id=other["id"], text=other["rendered_text"]), rows, set()
        )


def test_model_free_namespace_and_bound_native_entrypoint(tmp_path):
    """Expose only pinned frontend assets to a probe and a read-only SHA packet to native execution."""
    output = tmp_path / "out"
    output.mkdir(mode=0o700)
    args = trial.command(output, probe=True)
    mounts = {args[i + 2] for i, value in enumerate(args) if value == "--ro-bind"}
    assert (
        "/model" not in mounts
        and "/hf/hub" not in mounts
        and "/approved-validation.json" not in mounts
    )
    assert args[-1] == "--probe" and args[args.index("/venv/bin/python") + 1].endswith(
        "vi_ngoc_api_boundary_worker.py"
    )
    packet = tmp_path / "packet.json"
    packet.write_text("{}")
    args = trial.command(output, packet, "a" * 64)
    assert (
        "--unshare-all" in args
        and "/approved-validation.json" in args
        and args[-2:] == ["--run", "a" * 64]
    )


def test_pair_media_has_exact_old_new_WAVs_or_explicit_missing_candidate():
    """Prevent regenerated baselines, fabricated repaired audio and hidden browser capabilities."""
    text = trial.render_pair("<script>source</script>", b"old", b"new", "COMPLETE")
    parser = MediaParser()
    parser.feed(text)
    assert (
        len(parser.media) == 2
        and not parser.forbidden
        and "<script>source</script>" not in text
    )
    assert [base64.b64decode(row["src"].split(",", 1)[1]) for row in parser.media] == [
        b"old",
        b"new",
    ]
    assert all("autoplay" not in row for row in parser.media)
    text = trial.render_pair("source", b"old", None, "FAILED")
    parser = MediaParser()
    parser.feed(text)
    assert len(parser.media) == 1 and "Chưa có clip hoàn chỉnh: FAILED" in text


@pytest.mark.asyncio
async def test_consumed_root_prevents_model_replay(tmp_path):
    """Refuse a second run before reading authorization or starting a process."""
    (tmp_path / "execution-freeze.json").write_text("{}")
    with pytest.raises(ValueError, match="already_attempted"):
        await trial.run(tmp_path)


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [None, ValueError, asyncio.CancelledError])
async def test_single_attempt_error_cancel_and_join(tmp_path, monkeypatch, failure):
    """Run the actual one-request controller without weights and keep fatal first outcomes rather than retrying."""
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
    (tmp_path / "probe/native").mkdir(parents=True)
    (tmp_path / "probe/native/frontend.json").write_text("{}")
    (tmp_path / "approved-packet.json").write_text("{}")
    (tmp_path / "software-verification.json").write_text(
        json.dumps(dict(status="PASS", source_sha256=hashes))
    )
    original, probe = fixture_packets()
    packet = trial.compile_packet(original, probe)
    old = copy.deepcopy(probe["original_row"])
    monkeypatch.setattr(trial.Q.assets, "PROJECT", project)
    monkeypatch.setattr(trial.Q.assets, "ROOT", tmp_path)
    monkeypatch.setattr(trial, "authorization", lambda: authority)
    monkeypatch.setattr(
        trial,
        "verify_previous",
        lambda: dict(speaker_sha256="s", reference_codes_sha256="r"),
    )
    monkeypatch.setattr(trial, "read_packet", lambda root: copy.deepcopy(packet))
    monkeypatch.setattr(trial, "baseline", lambda: old)
    monkeypatch.setattr(trial.Q.lifecycle, "prepared_integrity", lambda root: None)
    monkeypatch.setattr(trial.Q.lifecycle, "verify_originals", lambda: {"fixture": 1})
    monkeypatch.setattr(trial.Q.lifecycle, "local_state", lambda: {"native_pids": []})
    monkeypatch.setattr(trial.retained.retained, "verify_native", lambda *args: None)
    calls = []
    closed = []

    class FakeWorker:
        """Record one synthetic outcome and explicit owned cleanup without a process."""

        def __init__(self, *args):
            """Start unused and without any native state."""
            self.failure = None

        async def start(self):
            """Represent fixed readiness without model execution."""
            return self

        async def call(self, message):
            """Return one first response or fail/cancel before any second request can exist."""
            calls.append(message)
            if failure:
                self.failure = "fixture"
                raise failure("fixture")
            return dict(chunks=[{}])

        async def close(self, force):
            """Record owned retirement under success, error or cancellation."""
            closed.append(True)

    monkeypatch.setattr(trial, "BoundaryWorker", FakeWorker)
    result = await trial.run(tmp_path)
    assert (
        len(calls) == result["tts_attempts"] == 1
        and calls[0]["id"] == worker.SELECTED
        and calls[0]["voice"] == worker.VOICE
    )
    assert (
        result["completed_inner_chunks"] == (0 if failure else 1)
        and result["unattempted"] == 0
    )
    assert result["status"] == (
        "STOPPED_NO_RETRY"
        if failure
        else "API_BOUNDARY_CANDIDATE_COMPLETE_ACOUSTIC_UNVERIFIED"
    )
    assert closed == [True] and result["retries"] == 0 and result["baseline_restored"]
