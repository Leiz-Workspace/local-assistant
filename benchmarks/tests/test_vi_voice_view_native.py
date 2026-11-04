"""Test conditional native-gate admission, finite model budgets and exact VAD child cancellation without real models."""

import asyncio
import json
import time

import pytest

from benchmarks.scripts import vi_voice_view_native as target
from benchmarks.tests.test_vi_voice_presence import audio
from benchmarks.tests.test_vi_voice_presence_check import events


def test_eight_slots_fix_two_asr_lanes_and_original_sources():
    """Keep source order and four negatives explicit before any model decision can affect coverage."""
    packet = dict(
        workflow_sources=[
            dict(id="s" + str(i), expected_no_answer=i >= 4) for i in range(6)
        ]
    )
    rows = target.matrix(packet)
    assert (
        len(rows) == 8 and [x["source"] for x in rows] == ["s0", "s1", "s4", "s5"] * 2
    )
    assert sum(x["expected_no_answer"] for x in rows) == 4
    assert {x["asr"] for x in rows} == {"whisper-small-ct2", "qwen3-asr-0.6b"}


def test_call_ledger_consumes_before_dispatch_and_never_refunds(tmp_path):
    """Forbid a fifth native call or duplicate identity even when a prior attempt failed externally."""
    ledger = target.Ledger(tmp_path)
    for kind in ("asr", "core", "tts"):
        for i in range(4):
            ledger.admit(kind, kind + str(i))
        with pytest.raises(ValueError, match="budget"):
            ledger.admit(kind, kind + "extra")
    assert ledger.counts == dict(asr=4, core=4, tts=4)


@pytest.mark.parametrize(
    "bad", ["status", "correct", "total", "observations", "baseline", "failure"]
)
@pytest.mark.asyncio
async def test_unqualified_detector_cannot_load_any_voice_models(
    monkeypatch, tmp_path, bad
):
    """Require the actual147of147and288observation gate rather than promoting99of100or software-only PASS."""
    root = tmp_path / "study"
    root.mkdir()
    quality = dict(status="LOCAL_DETECTOR_GATES_PASS", boost_correct=147, total=147)
    retired = dict(observations=288, baseline_preserved=True, failure=None)
    if bad == "status":
        quality["status"] = "LOCAL_DETECTOR_GATES_FAIL"
    elif bad == "correct":
        quality["boost_correct"] = 146
    elif bad == "total":
        quality["total"] = 146
    elif bad == "observations":
        retired["observations"] = 287
    elif bad == "baseline":
        retired["baseline_preserved"] = False
    elif bad == "failure":
        retired["failure"] = "RuntimeError"
    (root / "quality.json").write_text(json.dumps(quality))
    (root / "retirement.json").write_text(json.dumps(retired))
    monkeypatch.setattr(target.study, "ROOT", root)
    with pytest.raises(ValueError, match="qualification_not_passed"):
        await target.run(tmp_path / "not_created")
    assert not (tmp_path / "not_created").exists()


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["success", "cancel", "deadline"])
async def test_owned_native_vad_retires_before_asr_admission(
    monkeypatch, tmp_path, mode
):
    """Verify exact child ownership, bounded deadlines and joined cancellation with no model or host process action."""
    slot = tmp_path / "slot"
    slot.mkdir()
    samples = tmp_path / "samples"
    samples.mkdir()
    view = target.study.peak.detector_view(audio())
    expected = dict(
        id="one",
        filename="one.f32",
        sample_count=view.sample_count,
        waveform_sha256=view.waveform_sha256,
    )
    (samples / "one.f32").write_bytes(view.waveform_f32)
    entered, released = asyncio.Event(), asyncio.Event()
    kills = []

    class Child:
        """Expose only the asynchronous subprocess contract needed by the detector backend."""

        pid = 123456
        returncode = None

        async def communicate(self, payload):
            """Preserve native-shaped output after completion or explicit synthetic process retirement."""
            entered.set()
            if mode != "success":
                await released.wait()
            else:
                await asyncio.sleep(0)
            self.returncode = -9 if kills else 0
            output = events([expected], reverse=False)
            return "".join(json.dumps(x) + "\n" for x in output).encode(), b""

    child = Child()

    async def create(*args, **kwargs):
        """Assert isolated child ownership while avoiding any actual executable launch."""
        assert kwargs["start_new_session"] is True
        return child

    def kill(pid, sig):
        """Release only the fake owned process and record the exact target identity."""
        kills.append(pid)
        child.returncode = -9
        released.set()

    monkeypatch.setattr(target.asyncio, "create_subprocess_exec", create)
    monkeypatch.setattr(target.os, "killpg", kill)
    monkeypatch.setattr(
        target.old, "require_headroom", lambda: dict(MemAvailable_bytes=16 * 1024**3)
    )
    monkeypatch.setattr(
        target.old, "sandbox", lambda: [str(target.old.VAD_ROOT / "samples")]
    )
    monkeypatch.setattr(target.original, "WORKERS", set())
    monkeypatch.setattr(target.original, "process_tree", lambda pid: {pid})
    monkeypatch.setattr(target.original, "rss_bytes", lambda pid: 0)
    backend = target.NativeViewBackend(
        slot,
        samples,
        expected,
        time.monotonic() + (-1 if mode == "deadline" else 5),
        99,
    )
    task = asyncio.create_task(backend.observe(view))
    await asyncio.wait_for(entered.wait(), 1)
    if mode == "cancel":
        task.cancel()
    if mode == "success":
        result = await task
        assert result.waveform_sha256 == view.waveform_sha256
        with pytest.raises(ValueError, match="capability"):
            await backend.observe(view)
    else:
        with pytest.raises(asyncio.CancelledError if mode == "cancel" else ValueError):
            await task
    receipt = json.loads((slot / "vad/retirement.json").read_text())
    assert receipt["reaped"] and receipt["exit_code"] == (
        0 if mode == "success" else -9
    )
    assert kills == ([] if mode == "success" else [123456])


@pytest.mark.asyncio
async def test_changed_detector_file_cannot_start_a_worker(tmp_path):
    """Validate the exact prepared native input on disk before any headroom or loading attempt."""
    slot = tmp_path / "slot"
    slot.mkdir()
    samples = tmp_path / "samples"
    samples.mkdir()
    view = target.study.peak.detector_view(audio())
    (samples / "one.f32").write_bytes(b"changed")
    backend = target.NativeViewBackend(
        slot,
        samples,
        dict(
            filename="one.f32",
            waveform_sha256=view.waveform_sha256,
            sample_count=view.sample_count,
        ),
        time.monotonic() + 1,
        99,
    )
    with pytest.raises(ValueError, match="input_changed"):
        await backend.observe(view)
    assert not (slot / "vad").exists()
