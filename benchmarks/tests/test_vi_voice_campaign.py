"""Test isolated research inference boundaries, lifecycle guards and unchanged pipeline composition."""

import asyncio
import json
import sys
import time
from types import SimpleNamespace

import numpy as np
import pytest

from benchmarks.scripts import vi_voice_campaign as campaign
from benchmarks.scripts import vi_voice_worker as worker


@pytest.mark.parametrize(
    "value",
    [
        None,
        {},
        {"op": "shell"},
        {"op": "close", "extra": 1},
        {"op": "synthesize", "id": "../x", "text": "hello", "voice": "Trúc Ly"},
        {"op": "synthesize", "id": "ok", "text": "\x00", "voice": "Trúc Ly"},
        {"op": "synthesize", "id": "ok", "text": "x" * 4097, "voice": "Trúc Ly"},
        {"op": "synthesize", "id": "ok", "text": "hello", "voice": "default"},
    ],
)
def test_invalid_worker_requests(value):
    """Reject arbitrary operation injection, filesystem escape and unsupported voice/text inputs."""
    with pytest.raises(ValueError):
        worker.validate_message(value)


def test_public_asr_message_excludes_references():
    """Allow only waveform binding fields and reject expected transcripts or negative labels."""
    message = dict(
        op="transcribe",
        id="test",
        filename="source.f32",
        sample_count=1,
        waveform_sha256="a" * 64,
    )
    worker.validate_message(message)
    for extra in ["expected_no_answer", "reference", "language"]:
        with pytest.raises(ValueError):
            worker.validate_message(message | {extra: "private label"})
    with pytest.raises(ValueError):
        worker.validate_message(message | {"filename": "../source.f32"})
    with pytest.raises(ValueError):
        worker.validate_message(message | {"sample_count": True})


def test_native_48k_preserves_float_bits_and_piper_rate():
    """Retain raw native bits including signed zero without clipping or resampling."""
    values = np.array([0, -0.0, 0.5, -0.75, 1.1], dtype="float32")
    for rate in [48000, 22050]:
        raw, wav = worker.native_bytes(values, rate)
        assert raw == values.tobytes()
        assert wav[44:] == raw
        assert wav[20:22] == b"\x03\x00"
        assert len(wav) == len(raw) + 44
    with pytest.raises(ValueError):
        campaign.pcm_wave(values.tobytes(), 48000)


@pytest.mark.parametrize(
    "values,rate",
    [
        (np.zeros((2, 3), dtype="float32"), 48000),
        (np.zeros(3, dtype="float64"), 48000),
        (np.array([np.nan], dtype="float32"), 48000),
        (np.zeros(0, dtype="float32"), 48000),
        (np.zeros(1, dtype="float32"), 16000),
    ],
)
def test_invalid_native_output(values, rate):
    """Reject ambiguous channels, non-finite samples and unsupported native return formats."""
    with pytest.raises(ValueError):
        worker.native_bytes(values, rate)


def test_parent_output_integrity_and_symlinks(tmp_path):
    """Independently detect corrupted native bytes, missing EOS and escaped output leaves."""
    raw, wav = worker.native_bytes(np.array([0.0, 0.25], dtype="float32"), 48000)
    for suffix, value in [("f32", raw), ("wav", wav)]:
        p = tmp_path / ("case." + suffix)
        p.write_bytes(value)
        p.chmod(0o600)
    result = dict(
        sample_rate=48000,
        samples=2,
        channels=1,
        dtype="float32",
        native_sha256=campaign.sha(raw),
        wav_sha256=campaign.sha(wav),
        generation_complete=True,
    )
    assert campaign.read_native(tmp_path, "case", result) == raw
    with pytest.raises(ValueError, match="did_not_end"):
        campaign.read_native(tmp_path, "case", result | dict(generation_complete=False))
    (tmp_path / "case.wav").write_bytes(wav[:-1] + b"X")
    with pytest.raises(ValueError, match="integrity"):
        campaign.read_native(tmp_path, "case", result)
    (tmp_path / "case.f32").unlink()
    (tmp_path / "case.f32").symlink_to(tmp_path / "case.wav")
    with pytest.raises(OSError):
        campaign.read_native(tmp_path, "case", result)


def test_frame_observer_is_transparent():
    """Return exact original objects/arguments and distinguish frame exhaustion from EOS."""
    codes, audio = object(), object()
    events = []

    class Engine:
        """Provide deterministic native frame and codec results for observer tests."""

        def _acoustic_frame(self, *args, **kwargs):
            """Retain input identity and return one native frame."""
            events.append((args, kwargs))
            return codes, kwargs["eos"]

        def _decode_codes(self, *args, **kwargs):
            """Return the exact original waveform marker."""
            return audio

    engine = Engine()
    observer = worker.FrameObserver(engine)
    marker = object()
    returned = engine._acoustic_frame(marker, eos=False)
    assert returned[0] is codes and events[0][0][0] is marker
    assert engine._decode_codes(marker) is audio
    assert observer.groups == [dict(frames=1, eos=False)]
    observer.reset()
    engine._acoustic_frame(marker, eos=True)
    engine._decode_codes(marker)
    assert observer.groups == [dict(frames=1, eos=True)]


def test_workflow_denominators_are_fixed():
    """Keep all48 slots and their negatives even when no native model can execute."""
    packet = json.loads(campaign.assets.PACKET.read_text())
    rows = campaign.matrix(packet)
    assert len(rows) == 48 and len({r["id"] for r in rows}) == 48
    assert sum(r["expected_no_answer"] for r in rows) == 16
    assert all(r["status"] == "UNATTEMPTED" for r in rows)
    assert {r["state"] for r in rows} == {"fresh", "resident"}
    assert {r["tts"] for r in rows} == {"turbo", "piper-vi"}


def test_ledger_consumes_attempts_before_failure_and_rejects_retry(tmp_path):
    """Prevent repeated request IDs and any native call beyond the approved ceilings."""
    ledger = campaign.Ledger(tmp_path)
    for index in range(74):
        ledger.admit("tts", f"id-{index}")
    with pytest.raises(ValueError):
        ledger.admit("tts", "extra")
    with pytest.raises(ValueError):
        ledger.admit("asr", "id-0")
    assert ledger.counts == dict(tts=74, asr=0, core=0)
    assert len(ledger.path.read_text().splitlines()) == 74


def test_namespace_preserves_caps_and_has_no_host_credentials(tmp_path):
    """Require CPU affinity, offline namespaces, exact caps and only the intended readonly source mount."""
    output = tmp_path / "output"
    output.mkdir(mode=0o700)
    for candidate in ["turbo", "piper-vi", "qwen3-asr-0.6b", "whisper-small-ct2"]:
        command = campaign.namespace(candidate, output, tmp_path)
        assert command[:3] == ["/usr/bin/taskset", "--cpu-list", "0,1"]
        assert "--unshare-all" in command and "--clearenv" in command
        assert "--as=8589934592" in command and "--cpu=1200:1201" in command
        assert "/dev/nvidia0" not in command and "/home" not in command
        assert "--share-net" not in command
        assert "HF_HUB_OFFLINE" in command and "CUDA_VISIBLE_DEVICES" in command
        assert command[-1] == candidate
        if candidate == "qwen3-asr-0.6b":
            assert (
                str(campaign.ASR_ROOT / "runtime-source/qwen-backend-source") in command
            )
    (output / "existing").touch()
    with pytest.raises(ValueError):
        campaign.namespace("turbo", output, tmp_path)


def test_worker_guard_enforces_sampled_rss_and_global_wall(tmp_path, monkeypatch):
    """Stop before the next event on per-worker RSS breach or an expired campaign deadline."""
    directory = tmp_path / "worker"
    directory.mkdir()
    (directory / "stderr.log").touch()
    w = campaign.Worker("turbo", directory, time.monotonic() + 10, root=tmp_path)
    w.process = SimpleNamespace(pid=123, returncode=None)
    w.started = time.monotonic()
    monkeypatch.setattr(campaign, "process_tree", lambda pid: {pid})
    monkeypatch.setattr(campaign, "rss_bytes", lambda pid: 2 * campaign.GIB + 1)
    with pytest.raises(ValueError, match="tts_sampled_rss"):
        w.check()
    w.deadline = time.monotonic() - 1
    with pytest.raises(TimeoutError):
        w.check()


@pytest.mark.asyncio
async def test_real_owned_process_is_joined_on_protocol_failure(tmp_path, monkeypatch):
    """Join a real malformed local fixture process and retain its first protocol failure without model execution."""
    code = 'import time; print("not-json",flush=True); time.sleep(30)'
    monkeypatch.setattr(
        campaign, "namespace", lambda *args: [sys.executable, "-c", code]
    )
    monkeypatch.setattr(campaign, "mem_available", lambda: 20 * campaign.GIB)
    monkeypatch.setattr(campaign.os, "sched_getaffinity", lambda pid: {0, 1})
    w = campaign.Worker(
        "turbo", tmp_path / "worker", time.monotonic() + 10, root=tmp_path
    )
    with pytest.raises(json.JSONDecodeError):
        await w.start()
    assert w.process.returncode is not None
    assert w not in campaign.WORKERS
    assert (w.directory / "retirement.json").exists()
    assert (
        json.loads((w.directory / "process-identity.json").read_text())["pid"]
        == w.process.pid
    )


@pytest.mark.asyncio
async def test_cancellation_joins_real_worker(tmp_path, monkeypatch):
    """Cancel an idle load fixture and verify it leaves no active owned process or queued admission."""
    monkeypatch.setattr(
        campaign,
        "namespace",
        lambda *args: [sys.executable, "-c", "import time; time.sleep(30)"],
    )
    monkeypatch.setattr(campaign, "mem_available", lambda: 20 * campaign.GIB)
    monkeypatch.setattr(campaign.os, "sched_getaffinity", lambda pid: {0, 1})
    w = campaign.Worker(
        "turbo", tmp_path / "worker", time.monotonic() + 10, root=tmp_path
    )
    task = asyncio.create_task(w.start())
    for _ in range(50):
        if w.process is not None:
            break
        await asyncio.sleep(0.01)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert w.process.returncode is not None and w not in campaign.WORKERS


@pytest.mark.asyncio
async def test_headroom_failure_never_spawns(tmp_path, monkeypatch):
    """Reject inadequate RAM before creating a model process or a native output directory."""
    monkeypatch.setattr(campaign, "mem_available", lambda: 14 * campaign.GIB - 1)
    w = campaign.Worker(
        "turbo", tmp_path / "worker", time.monotonic() + 10, root=tmp_path
    )
    with pytest.raises(ValueError, match="preflight"):
        await w.start()
    assert w.process is None and not w.directory.exists()


@pytest.mark.asyncio
async def test_watchdog_guards_idle_resident_workers(tmp_path, monkeypatch):
    """Cancel the campaign while a resident worker is idle if its sampled guard fails."""

    class IdleWorker:
        """Expose a failing resource guard without a native process."""

        def check(self):
            """Fail the aggregate memory precondition on the first observation."""
            raise ValueError("aggregate_sampled_rss_ceiling")

    class Actor:
        """Record cancellation of the owning campaign admission task."""

        def __init__(self):
            """Initialize the observable cancellation flag."""
            self.cancelled = False

        def cancel(self):
            """Mark admission cancelled without cancelling this test task."""
            self.cancelled = True

    actor = Actor()
    monkeypatch.setattr(campaign, "WORKERS", {IdleWorker()})
    monkeypatch.setattr(campaign, "FAILURES", [])
    await campaign.monitor_campaign(tmp_path, time.monotonic() + 10, actor)
    assert actor.cancelled and "aggregate_sampled_rss_ceiling" in campaign.FAILURES[0]


@pytest.mark.asyncio
async def test_research_asr_empty_output_preserves_original_no_speech_gate(tmp_path):
    """Keep negative references outside inference and refuse before any CORE or TTS request."""
    from uuid import uuid4
    from src.application.services.voice_pipeline import VoicePipeline, VoiceError
    from src.infrastructure.audio_normalizer import NativeAudioNormalizer

    audio = NativeAudioNormalizer().normalize(
        campaign.pcm_wave(np.zeros(1600, dtype="<f4").tobytes(), 16000)
    )

    class ASRWorker:
        """Return an original empty ASR prediction without accessing retained inputs."""

        async def call(self, message):
            """Require the public waveform-only protocol and return a complete empty transcript."""
            worker.validate_message(message)
            assert not {"expected_no_answer", "reference"} & message.keys()
            return dict(asr=dict(text="", output_cap_reached=False))

    class Forbidden:
        """Reject any downstream model call for correctly empty ASR output."""

        async def complete(self, **kwargs):
            """Fail if no-speech incorrectly invokes CORE."""
            pytest.fail("CORE must not run")

        async def synthesize(self, *args):
            """Fail if no-speech incorrectly invokes TTS."""
            pytest.fail("TTS must not run")

    slot = tmp_path / "turn-00"
    slot.mkdir()
    ledger = campaign.Ledger(tmp_path)
    source = dict(
        audio=audio,
        request=dict(
            filename="source.f32", sample_count=1600, waveform_sha256="a" * 64
        ),
    )
    adapter = campaign.ResearchASR(
        "qwen3-asr-0.6b", ASRWorker(), slot, source, ledger, time.monotonic() + 10, None
    )
    service = VoicePipeline(
        asr=adapter,
        llm=Forbidden(),
        tts=Forbidden(),
        asr_model="qwen3-asr-0.6b",
        llm_model="qwen3.5-9b-core",
        tts_model="piper-vi",
    )
    with pytest.raises(VoiceError, match="no_speech"):
        await service.complete(uuid4(), audio, "vi", explicit_submission=True)
    await service.shutdown()
    assert ledger.counts == dict(asr=1, core=0, tts=0)


@pytest.mark.asyncio
async def test_core_contract_retains_failed_first_response(tmp_path, monkeypatch):
    """Retain an unfinished original gateway response without retrying it or claiming complete speech."""
    calls = []

    class Gateway:
        """Supply one incomplete gateway response at the approved owned endpoint."""

        def __init__(self, **kwargs):
            """Verify the configured original CORE identity and loopback-only endpoint."""
            assert kwargs == dict(
                base_url="http://127.0.0.1:18080", model_id="qwen3.5-9b-core"
            )

        async def complete(self, **kwargs):
            """Record the single original Fast512 call and return a capped response."""
            calls.append(kwargs)
            return dict(
                choices=[
                    dict(finish_reason="length", message=dict(content="unfinished"))
                ],
                local_assistant=dict(status="PASS", preset_selected="fast"),
            )

    monkeypatch.setattr(campaign, "LlamaGateway", Gateway)
    slot = tmp_path / "turn-00"
    slot.mkdir()
    ledger = campaign.Ledger(tmp_path)
    adapter = campaign.ResearchCORE(slot, ledger)
    with pytest.raises(ValueError, match="incomplete"):
        await adapter.complete(
            profile="core", messages=[], preset="fast", temperature=0, max_tokens=512
        )
    assert len(calls) == 1 and calls[0]["max_tokens"] == 512
    assert (slot / "core-response.json").exists()
    assert ledger.counts["core"] == 1
    with pytest.raises(ValueError, match="contract"):
        await adapter.complete(
            profile="core", messages=[], preset="fast", temperature=0, max_tokens=128
        )
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_campaign_stops_at_first_qualification_load_failure(
    tmp_path, monkeypatch
):
    """Preserve every denominator and stop before scoring or workflows when the first model cannot load."""
    fake_tts = tmp_path / "original-tts/runtime-source"
    fake_tts.mkdir(parents=True)
    for name in ["passwd", "group"]:
        (fake_tts / name).write_text("fixture identity")
    root = tmp_path / "campaign"
    root.mkdir()
    (root / "results").mkdir()
    (root / "prepared-inventory.json").write_text("{}")
    (root / "requirements.lock").write_text("fixture")
    files = [
        *campaign.PROJECT.glob("benchmarks/scripts/vi_voice_*.py"),
        *campaign.PROJECT.glob("benchmarks/tests/test_vi_voice_*.py"),
    ]
    (root / "software-verification.json").write_text(
        json.dumps(
            dict(
                status="PASS",
                operator_sha256={
                    str(p.relative_to(campaign.PROJECT)): campaign.assets.digest(p)
                    for p in files
                },
            )
        )
    )
    monkeypatch.setattr(campaign, "prepared_integrity", lambda root: None)
    monkeypatch.setattr(campaign, "verify_originals", lambda: {})
    monkeypatch.setattr(campaign, "verify_models", lambda: None)
    monkeypatch.setattr(campaign, "verify_runtime_snapshot", lambda: None)
    monkeypatch.setattr(campaign, "verify_file", lambda *args: None)
    monkeypatch.setattr(campaign, "prepare_samples", lambda *args: {})
    monkeypatch.setattr(
        campaign, "local_state", lambda: dict(native_pids=[], containers=[])
    )
    monkeypatch.setattr(campaign, "TTS_ROOT", fake_tts.parent)
    monkeypatch.setattr(campaign, "FAILURES", [])
    attempts = []

    class FailedWorker:
        """Fail a single qualification load before any synthesis dispatch."""

        def __init__(self, candidate, *args, **kwargs):
            """Bind a known failed qualification fixture."""
            self.failure = "fixture_load_failure"
            self.candidate = candidate

        async def start(self):
            """Record and fail the only permitted load attempt."""
            attempts.append(self.candidate)
            raise ValueError("fixture_load_failure")

        async def close(self, **kwargs):
            """Represent joined cleanup of the failed fixture."""
            return None

    monkeypatch.setattr(campaign, "Worker", FailedWorker)
    result = await campaign.run(root)
    assert attempts == ["turbo"]
    assert result["status"] == "STOPPED_NO_RETRY"
    assert result["calls"] == dict(tts=0, asr=0, core=0)
    assert result["unattempted_standalone"] == 24
    assert result["unattempted_workflow"] == 48
    assert not result.get("cleanup_error")


@pytest.mark.asyncio
async def test_core_uses_actual_fast_gateway_metadata(tmp_path, monkeypatch):
    """Exercise the real gateway enrichment, preventing a stub-only metadata shape from masking integration errors."""
    import httpx
    from apps.api.services.llama_gateway import LlamaGateway

    generations = []

    def handler(request):
        """Provide native HTTP fixtures while letting the real gateway construct Fast metadata."""
        data = json.loads(request.content) if request.content else {}
        if request.url.path == "/v1/models":
            return httpx.Response(200, json=dict(data=[dict(id="qwen3.5-9b-core")]))
        if request.url.path == "/apply-template":
            return httpx.Response(200, json=dict(prompt="fixture prompt"))
        if request.url.path == "/tokenize":
            return httpx.Response(200, json=dict(tokens=[1, 2]))
        assert request.url.path == "/v1/chat/completions"
        generations.append(data)
        return httpx.Response(
            200,
            json=dict(
                choices=[dict(message=dict(content="Đã rõ."), finish_reason="stop")],
                usage=dict(prompt_tokens=2, completion_tokens=4),
            ),
        )

    gateway = LlamaGateway(
        "http://127.0.0.1:18080",
        "qwen3.5-9b-core",
        transport=httpx.MockTransport(handler),
    )
    monkeypatch.setattr(campaign, "LlamaGateway", lambda **kwargs: gateway)
    slot = tmp_path / "turn-00"
    slot.mkdir()
    ledger = campaign.Ledger(tmp_path)
    result = await campaign.ResearchCORE(slot, ledger).complete(
        profile="core",
        messages=[dict(role="user", content="Xin chào.")],
        preset="fast",
        temperature=0,
        max_tokens=512,
    )
    assert result.content == "Đã rõ." and result.preset_selected == "fast"
    assert len(generations) == 1 and generations[0]["max_tokens"] == 512
    saved = json.loads((slot / "core-response.json").read_text())["response"][
        "local_assistant"
    ]
    assert saved["preset"] == "fast" and "preset_selected" not in saved
    assert saved["context_size"] == 32768


@pytest.mark.asyncio
async def test_core_unknown_metadata_stops_later_admission(tmp_path, monkeypatch):
    """Mark unexpected gateway metadata fatal rather than repeating the same software failure across slots."""

    class Gateway:
        """Return a deliberately inconsistent gateway metadata contract."""

        async def complete(self, **kwargs):
            """Return a complete string with an unapproved preset identity."""
            return dict(
                choices=[dict(message=dict(content="reply"), finish_reason="stop")],
                local_assistant=dict(status="PASS", preset="balanced"),
            )

    monkeypatch.setattr(campaign, "LlamaGateway", lambda **kwargs: Gateway())
    monkeypatch.setattr(campaign, "FAILURES", [])
    slot = tmp_path / "turn-00"
    slot.mkdir()
    with pytest.raises(ValueError, match="metadata_contract"):
        await campaign.ResearchCORE(slot, campaign.Ledger(tmp_path)).complete(
            profile="core", messages=[], preset="fast", temperature=0, max_tokens=512
        )
    assert campaign.FAILURES == ["core_gateway_metadata_contract"]


@pytest.mark.asyncio
async def test_original_owned_shutdown_survives_repeated_cancellation():
    """Keep the original shutdown task pinned until cleanup finishes despite repeated caller cancellation."""
    from src.application.services.web_fetch_tasks import finish_owned, spawn_owned

    joined = asyncio.Event()

    async def cleanup():
        """Represent a bounded asynchronous owned CORE stop and join."""
        await asyncio.sleep(0.05)
        joined.set()

    async def actor():
        """Use the same shielded join boundary as the corrected campaign."""
        await finish_owned(spawn_owned(cleanup()))

    task = asyncio.create_task(actor())
    await asyncio.sleep(0.01)
    task.cancel()
    await asyncio.sleep(0.01)
    task.cancel()
    await task
    assert joined.is_set()


@pytest.mark.asyncio
async def test_recovery_cannot_execute_without_new_approval(tmp_path, monkeypatch):
    """Refuse recovery before integrity scans, model loading, directories or native calls when approval is absent."""
    monkeypatch.setattr(campaign, "PROJECT", tmp_path / "project")
    monkeypatch.setattr(
        campaign,
        "prepared_integrity",
        lambda root: pytest.fail("Must not prepare or load"),
    )
    with pytest.raises(ValueError, match="adr155_owner_approval_required"):
        await campaign.run_workflow_recovery(tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_recovery_approval_binds_exact_plan(tmp_path):
    """Reject changed or unapproved recovery plans without treating the previous campaign approval as reusable."""
    plan, approval = tmp_path / "plan.json", tmp_path / "approval.json"
    plan.write_text('{"description":"test plan"}')
    for value in [
        dict(approved=False, plan_sha256=campaign.assets.digest(plan)),
        dict(approved=True, plan_sha256="0" * 64),
    ]:
        approval.write_text(json.dumps(value))
        with pytest.raises(ValueError, match="approval_binding"):
            campaign.require_recovery_approval(plan, approval)
    approval.write_text(
        json.dumps(dict(approved=True, plan_sha256=campaign.assets.digest(plan)))
    )
    assert (
        campaign.require_recovery_approval(plan, approval)["description"] == "test plan"
    )
    plan.write_text("{}")
    with pytest.raises(ValueError):
        campaign.require_recovery_approval(plan, approval)
