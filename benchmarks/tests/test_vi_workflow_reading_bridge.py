"""Exercise the real buffered voice pipeline with reading provenance, original gateway metadata and joined cancellation."""

import asyncio
import copy
import hashlib
import json
from dataclasses import replace
from types import SimpleNamespace
from uuid import uuid4

import httpx
import numpy as np
import pytest

from apps.api.services.llama_gateway import LlamaGateway
from benchmarks.scripts import vi_voice_campaign as original
from benchmarks.scripts import vi_workflow_reading_bridge as bridge
from benchmarks.scripts.vi_workflow_reading_policy import (
    MODEL,
    POLICY,
    VOICE,
    plan_chunk,
    prepare_answer,
    sha,
)
from src.application.ports.audio import NormalizedAudio
from src.application.ports.inference import CompletionResult
from src.application.ports.voice import VoiceSpeech, VoiceTranscript
from src.application.services.voice_pipeline import VoiceError

ANSWER = "private-answer lúc 09:15 ngày 14/11/2026; Python dùng API?"
BINDING = dict(speaker_sha256="a" * 64, reference_codes_sha256="b" * 64)


def audio():
    """Provide public source-bound authored PCM with the original nonzero source clock."""
    raw = b"\0\0" * 16000
    return NormalizedAudio(
        "a" * 64,
        hashlib.sha256(raw).hexdigest(),
        raw,
        16000,
        "pcm_s16le",
        16000,
        1,
        16000,
        1,
        1000,
        2500,
    )


def fixture(change=None, timeout=2):
    """Compose the unchanged pipeline with source-bound authored stages and observable reading/audit boundaries."""
    seen, traces = [], []

    async def transcribe(owner, value, language):
        """Return one complete source/model-bound ASR observation without a model call."""
        return VoiceTranscript(
            owner,
            value.source_sha256,
            value.pcm_sha256,
            language,
            "private-speech",
            "qwen3-asr-0.6b",
        )

    async def complete(**kwargs):
        """Keep the original CORE/Fast512 request shape and answer text."""
        assert (
            kwargs["profile"] == "core"
            and kwargs["preset"] == "fast"
            and kwargs["max_tokens"] == 512
        )
        assert kwargs["temperature"] == 0 and "tools" not in kwargs
        return CompletionResult(ANSWER, "qwen3.5-9b-core", "fast", "stop")

    async def synthesize(owner, spoken, language):
        """Return complete authored PCM bound to the actual rendered input, never the original answer by accident."""
        seen.append((owner, spoken, language))
        result = VoiceSpeech(
            owner, sha(spoken), language, MODEL, b"\0\0" * 16000, 16000
        )
        return change(result) if change else result

    async def audit(trace):
        """Record only the explicit original/spoken transform provenance."""
        traces.append(trace)

    backend = SimpleNamespace(
        model_id=MODEL, reading_profile=POLICY, synthesize=synthesize
    )
    service = bridge.compose_workflow(
        SimpleNamespace(transcribe=transcribe),
        SimpleNamespace(complete=complete),
        backend,
        audit,
        asr_model="qwen3-asr-0.6b",
        timeout=timeout,
    )
    return service, backend, seen, traces


@pytest.mark.asyncio
async def test_complete_turn_keeps_original_answer_and_binds_verified_rendered_audio(
    caplog,
):
    """Show the original answer while separately hashing the spoken text and preserving original source clocks."""
    caplog.set_level("INFO")
    service, _, seen, traces = fixture()
    owner = uuid4()
    result = await service.complete(owner, audio(), "vi", explicit_submission=True)
    assert result.answer == ANSWER and result.speech.text_sha256 == sha(ANSWER)
    assert seen == [(owner, prepare_answer(ANSWER)[0], "vi")]
    assert traces[0].spoken_sha256 == sha(seen[0][1]) != traces[0].original_sha256
    assert result.source_first_pts == 2500 and result.source_time_base_den == 1000
    assert [stage for stage, _ in result.stage_seconds] == ["asr", "llm", "tts"]
    assert "private-answer" not in caplog.text and "private-speech" not in caplog.text
    assert "private" not in repr(result) and not service.tts.busy


@pytest.mark.parametrize(
    "change",
    [
        lambda value: replace(value, owner_id=uuid4()),
        lambda value: replace(value, text_sha256=sha(ANSWER)),
        lambda value: replace(value, model_id="wrong-model"),
        lambda value: replace(value, language="en"),
        lambda value: replace(value, complete=1),
        lambda value: replace(value, sample_count=True),
        lambda value: replace(value, pcm_s16le=b"bad"),
        lambda value: object(),
    ],
)
@pytest.mark.asyncio
async def test_wrong_backend_capability_cannot_be_rebound_or_audited(change):
    """Do not turn a mismatched owner/hash/model/language or partial waveform into an apparently valid turn."""
    service, _, _, traces = fixture(change)
    with pytest.raises(VoiceError):
        await service.complete(uuid4(), audio(), "vi", explicit_submission=True)
    assert not traces and service.active is None and not service.tts.busy


@pytest.mark.asyncio
async def test_empty_ASR_reaches_neither_CORE_reading_nor_TTS():
    """Preserve the existing no-speech refusal rather than converting silence into a spoken answer."""
    service, _, seen, traces = fixture()

    async def empty(owner, value, language):
        """Return a complete empty source-bound transcript without a speech claim."""
        return VoiceTranscript(
            owner, value.source_sha256, value.pcm_sha256, language, "", "qwen3-asr-0.6b"
        )

    service.asr.transcribe = empty
    with pytest.raises(VoiceError, match="no_speech"):
        await service.complete(uuid4(), audio(), "vi", explicit_submission=True)
    assert not seen and not traces


@pytest.mark.asyncio
async def test_audit_sink_failure_never_publishes_success_or_raw_error(caplog):
    """Require successful provenance recording before rebinding a complete waveform to the original answer."""
    caplog.set_level("INFO")
    service, _, seen, _ = fixture()

    async def broken(trace):
        """Model a failed owner-controlled trace writer without leaking its private diagnostic."""
        raise RuntimeError("private-sink-failure")

    service.tts.audit = broken
    with pytest.raises(VoiceError, match="dependency_failed"):
        await service.complete(uuid4(), audio(), "vi", explicit_submission=True)
    assert len(seen) == 1 and not service.tts.busy and service.active is None
    assert "private-sink-failure" not in caplog.text


@pytest.mark.parametrize("stage", ["backend", "audit"])
@pytest.mark.asyncio
async def test_repeated_cancel_keeps_admission_busy_until_reading_dependency_cleanup_joins(
    stage,
):
    """Preserve Stop/Cancel ownership across both speech preparation and trace publication boundaries."""
    service, backend, _, _ = fixture()
    entered, release, joined = asyncio.Event(), asyncio.Event(), asyncio.Event()

    async def blocked(*args):
        """Delay dependency cleanup to expose premature busy release or a late publish."""
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            await release.wait()
            joined.set()

    if stage == "backend":
        backend.synthesize = blocked
    else:
        service.tts.audit = blocked
    operation = asyncio.create_task(
        service.complete(uuid4(), audio(), "vi", explicit_submission=True)
    )
    await entered.wait()
    operation.cancel()
    await asyncio.sleep(0)
    operation.cancel()
    with pytest.raises(VoiceError, match="busy"):
        await service.complete(uuid4(), audio(), "vi", explicit_submission=True)
    assert service.tts.busy and not joined.is_set()
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await operation
    assert joined.is_set() and service.active is None and not service.tts.busy


@pytest.mark.parametrize("stage", ["backend", "audit"])
@pytest.mark.asyncio
async def test_suppressed_timeout_cannot_publish_a_late_reading_result(stage):
    """Keep the original host deadline authoritative even if a speech/audit dependency swallows cancellation."""
    service, backend, _, traces = fixture(timeout=0.01)

    async def late(*args):
        """Return after cancellation to test the bridge's explicit live checks."""
        try:
            await asyncio.sleep(10)
        except asyncio.CancelledError:
            if stage == "backend":
                owner, spoken, language = args
                return VoiceSpeech(
                    owner, sha(spoken), language, MODEL, b"\0\0" * 100, 100
                )

    if stage == "backend":
        backend.synthesize = late
    else:
        service.tts.audit = late
    with pytest.raises(VoiceError, match="timeout"):
        await service.complete(uuid4(), audio(), "vi", explicit_submission=True)
    assert not traces and not service.tts.busy and service.active is None


@pytest.mark.asyncio
async def test_shutdown_joins_reading_cleanup_and_permanently_closes_pipeline():
    """Keep shutdown from reopening recording/model admission before the active speech dependency is retired."""
    service, backend, _, _ = fixture()
    entered, release = asyncio.Event(), asyncio.Event()

    async def blocked(*args):
        """Expose an active owned synthesis dependency until shutdown cleanup is released."""
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            await release.wait()

    backend.synthesize = blocked
    operation = asyncio.create_task(
        service.complete(uuid4(), audio(), "vi", explicit_submission=True)
    )
    await entered.wait()
    stopping = asyncio.create_task(service.shutdown())
    await asyncio.sleep(0)
    with pytest.raises(VoiceError, match="closed"):
        await service.complete(uuid4(), audio(), "vi", explicit_submission=True)
    release.set()
    await stopping
    with pytest.raises(asyncio.CancelledError):
        await operation
    assert service.active is None and not service.tts.busy


@pytest.mark.asyncio
async def test_actual_gateway_metadata_contract_runs_through_reading_pipeline(
    tmp_path, monkeypatch
):
    """Exercise the real original Fast gateway and caller's preset fallback using only authored HTTP fixtures."""
    requests = []

    def handler(request):
        """Serve declared gateway endpoints without a network connection or CORE generation."""
        data = json.loads(request.content) if request.content else {}
        if request.url.path == "/v1/models":
            return httpx.Response(200, json=dict(data=[dict(id="qwen3.5-9b-core")]))
        if request.url.path == "/apply-template":
            return httpx.Response(200, json=dict(prompt="fixture prompt"))
        if request.url.path == "/tokenize":
            return httpx.Response(200, json=dict(tokens=[1, 2]))
        assert request.url.path == "/v1/chat/completions"
        requests.append(data)
        return httpx.Response(
            200,
            json=dict(
                choices=[dict(message=dict(content=ANSWER), finish_reason="stop")],
                usage=dict(prompt_tokens=2, completion_tokens=4),
            ),
        )

    gateway = LlamaGateway(
        "http://127.0.0.1:18080",
        "qwen3.5-9b-core",
        transport=httpx.MockTransport(handler),
    )
    monkeypatch.setattr(original, "LlamaGateway", lambda **kwargs: gateway)
    slot = tmp_path / "turn"
    slot.mkdir()
    service, _, seen, traces = fixture()
    service.llm = original.ResearchCORE(slot, original.Ledger(tmp_path))
    result = await service.complete(uuid4(), audio(), "vi", explicit_submission=True)
    assert result.answer == ANSWER and seen and traces and len(requests) == 1
    saved = json.loads((slot / "core-response.json").read_text())["response"][
        "local_assistant"
    ]
    assert (
        saved["preset"] == "fast"
        and "preset_selected" not in saved
        and saved["context_size"] == 32768
    )
    assert requests[0]["max_tokens"] == 512


def native_fixture(tmp_path):
    """Build independently authored native trace and chunk bytes for provenance refusal controls."""
    message = dict(op="synthesize", id="reply-01", text="hello", voice=VOICE)
    plan = plan_chunk("hello.", "həloʊ.", lambda text: 100)
    raw = b"authored-chunk"
    (tmp_path / "reply-01-chunk-0.f32").write_bytes(raw)
    trace = dict(
        reading_policy=POLICY,
        spoken_input_sha256=sha(message["text"]),
        voice_binding=BINDING,
        reading_plans=[plan],
        chunks=[plan["normalized"]],
        gaps=[],
        phonemes=[plan["phones"]],
        native_chunk_sha256=[hashlib.sha256(raw).hexdigest()],
        reading_tokens=[dict(token_ids=[1, 2], decoded_exact=True, unknown_tokens=0)],
    )
    return message, dict(
        prosody_trace=trace,
        chunks=[dict(eos=True, frames=10)],
        generation_complete=True,
    )


@pytest.mark.parametrize(
    "kind", ["profile", "source", "voice", "phones", "cap", "EOS", "tokens", "hash"]
)
def test_native_trace_mismatch_cannot_be_converted_into_playback(tmp_path, kind):
    """Verify actual native provenance independently of a successful result flag or matching original-answer hash."""
    message, result = native_fixture(tmp_path)
    bridge.verify_native(result, message, tmp_path, BINDING)
    bad = copy.deepcopy(result)
    if kind == "profile":
        bad["prosody_trace"]["reading_policy"] = "raw"
    elif kind == "source":
        bad["prosody_trace"]["spoken_input_sha256"] = "other"
    elif kind == "voice":
        bad["prosody_trace"]["voice_binding"] = {}
    elif kind == "phones":
        bad["prosody_trace"]["reading_plans"][0]["phones"] = "other"
    elif kind == "cap":
        bad["chunks"][0]["frames"] = 101
    elif kind == "EOS":
        bad["chunks"][0]["eos"] = False
    elif kind == "tokens":
        bad["prosody_trace"]["reading_tokens"][0]["unknown_tokens"] = 1
    else:
        bad["prosody_trace"]["native_chunk_sha256"] = ["other"]
    with pytest.raises(ValueError):
        bridge.verify_native(bad, message, tmp_path, BINDING)


@pytest.mark.asyncio
async def test_wrong_cold_worker_profile_is_joined_and_invalid_language_never_loads(
    tmp_path,
):
    """Prevent raw TTS from silently substituting for accepted reading and keep invalid requests before startup."""
    events = []

    class WrongWorker:
        """Represent a wrongly configured owned child without creating a process."""

        ready = dict(
            candidate="turbo", profile="raw", voice=VOICE, reading_policy=POLICY
        )

        async def close(self, force=False):
            """Record joined disposal of the mismatched cold child."""
            events.append("joined")

    async def factory(*args):
        """Represent only the explicitly injected resource owner starting a child."""
        events.append("start")
        return WrongWorker()

    backend = bridge.ReadingResearchTTS(None, tmp_path, None, 1, None, factory, BINDING)
    with pytest.raises(ValueError, match="backend_request"):
        await backend.synthesize(uuid4(), "hello", "en")
    assert not events
    with pytest.raises(ValueError, match="ready_contract"):
        await backend.synthesize(uuid4(), "hello", "vi")
    assert events == ["start", "joined"]


def test_unmeasured_binding_or_another_ASR_lane_cannot_be_instantiated(tmp_path):
    """Refuse a missing voice capability or new model lane before any model factory can run."""
    with pytest.raises(ValueError, match="reference_binding"):
        bridge.ReadingResearchTTS(None, tmp_path, None, 1, None, lambda *args: None, {})
    service, backend, _, _ = fixture()
    with pytest.raises(ValueError, match="asr_lane"):
        bridge.compose_workflow(
            service.asr,
            service.llm,
            backend,
            service.tts.audit,
            asr_model="another-ASR",
        )


@pytest.mark.parametrize("resident", [False, True])
@pytest.mark.asyncio
async def test_actual_original_native_reader_and_playback_conversion_for_cold_and_resident(
    resident, tmp_path
):
    """Run genuine waveform writing/verification/conversion on authored PCM without TTS inference or playback claims."""
    from benchmarks.scripts.vi_voice_worker import native_bytes

    slot = tmp_path / "turn-00"
    slot.mkdir()
    directory = tmp_path / "worker"
    native = directory / "native"
    native.mkdir(parents=True)
    ledger = original.Ledger(tmp_path)
    closed, started = [], []
    wave = (0.1 * np.sin(2 * np.pi * 440 * np.arange(4800) / 48000)).astype(np.float32)
    raw, wav = native_bytes(wave, 48000)

    class AuthoredWorker:
        """Expose authored complete native artifacts through the original research worker interface."""

        ready = dict(
            candidate="turbo",
            profile="workflow-reading",
            voice=VOICE,
            reading_policy=POLICY,
        )

        def __init__(self):
            """Bind a public temporary fixture directory without creating a process."""
            self.directory = directory

        async def call(self, message):
            """Write the complete original-format native files and declared reading provenance."""
            plan = plan_chunk("hello.", "həloʊ.", lambda phones: 100)
            for name, content in [
                (message["id"] + ".f32", raw),
                (message["id"] + ".wav", wav),
                (message["id"] + "-chunk-0.f32", raw),
                (message["id"] + "-chunk-0.wav", wav),
            ]:
                path = native / name
                path.write_bytes(content)
                path.chmod(0o600)
            trace = dict(
                reading_policy=POLICY,
                spoken_input_sha256=sha(message["text"]),
                voice_binding=BINDING,
                reading_plans=[plan],
                chunks=[plan["normalized"]],
                gaps=[],
                phonemes=[plan["phones"]],
                native_chunk_sha256=[hashlib.sha256(raw).hexdigest()],
                reading_tokens=[
                    dict(token_ids=[1, 2], decoded_exact=True, unknown_tokens=0)
                ],
            )
            return dict(
                sample_rate=48000,
                channels=1,
                dtype="float32",
                samples=4800,
                native_sha256=hashlib.sha256(raw).hexdigest(),
                wav_sha256=hashlib.sha256(wav).hexdigest(),
                generation_complete=True,
                chunks=[dict(eos=True, frames=10)],
                prosody_trace=trace,
            )

        async def close(self, force=False):
            """Record original owned versus resident retirement without touching any process."""
            closed.append(force)

    actual = AuthoredWorker()

    async def factory(*args):
        """Provide the explicitly injected cold fixture once, never a model runtime."""
        started.append(True)
        return actual

    backend = bridge.ReadingResearchTTS(
        actual if resident else None, slot, ledger, 1, None, factory, BINDING
    )
    result = await backend.synthesize(uuid4(), "hello", "vi")
    assert (
        result.text_sha256 == sha("hello")
        and result.model_id == MODEL
        and result.complete is True
    )
    assert len(result.pcm_s16le) == 2 * result.sample_count and result.sample_count > 0
    assert ledger.counts == dict(tts=1, asr=0, core=0)
    assert started == ([] if resident else [True]) and closed == (
        [] if resident else [False]
    )
    metadata = json.loads((slot / "playback-conversion.json").read_text())
    assert metadata["native_sha256"] == hashlib.sha256(raw).hexdigest()
    assert metadata["native_sample_rate"] == 48000
