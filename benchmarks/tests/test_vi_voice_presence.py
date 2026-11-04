"""Verify optional whole-clip admission, original bytes, failure distinctions and joined voice lifecycle."""

import asyncio
from dataclasses import replace
from types import SimpleNamespace
from uuid import uuid4

import pytest

from benchmarks.scripts.vi_voice_presence import SpeechPresence, VAD_MODEL, WholeClipASR
from src.application.ports.audio import NormalizedAudio
from src.application.ports.inference import CompletionResult
from src.application.ports.voice import VoiceSpeech, VoiceTranscript
from src.application.services.voice_pipeline import VoiceError, VoicePipeline, digest


def audio():
    """Build a bounded private fixture with separated signal bytes and a nonzero rational clock."""
    raw = b"\x01\x00" * 16000 + b"\0\0" * 16000
    return NormalizedAudio(
        "a" * 64, digest(raw), raw, 32000, "pcm_s16le", 16000, 1, 32000, 1, 1000, 2500
    )


def decision(owner, value, segments=((100, 500), (16000, 17000))):
    """Bind synthetic detector evidence without claiming genuine speech quality."""
    return SpeechPresence(
        owner,
        value.source_sha256,
        value.pcm_sha256,
        value.sample_count,
        value.first_pts,
        value.time_base_num,
        value.time_base_den,
        VAD_MODEL,
        segments,
    )


def fixture(*, segments=((100, 500),), mutate=None):
    """Create recording stubs that preserve exact input object and complete dependency results."""
    calls = []

    async def detect(owner, value):
        """Return authored complete evidence and record only dependency order."""
        calls.append(("vad", value))
        result = decision(owner, value, segments)
        return mutate(result) if mutate else result

    async def transcribe(owner, value, language):
        """Return a complete transcript without simulating recognition accuracy."""
        calls.append(("asr", value))
        return VoiceTranscript(
            owner,
            value.source_sha256,
            value.pcm_sha256,
            language,
            "private speech",
            "fixture-asr",
        )

    return WholeClipASR(
        detector=SimpleNamespace(detect=detect),
        asr=SimpleNamespace(transcribe=transcribe),
        asr_model="fixture-asr",
    ), calls


@pytest.mark.asyncio
async def test_positive_preserves_all_bytes_gaps_clocks_and_transcript(caplog):
    """Forward the identical object despite partial intervals and avoid leaking audio or transcript text."""
    caplog.set_level("INFO")
    value, owner = audio(), uuid4()
    adapter, calls = fixture(segments=((100, 500), (16000, 17000)))
    result = await adapter.transcribe(owner, value, "vi")
    assert [x[0] for x in calls] == ["vad", "asr"]
    assert calls[1][1] is value and result.pcm_sha256 == value.pcm_sha256
    assert value.first_pts == 2500 and result.text == "private speech"
    assert "private speech" not in caplog.text and "private" not in repr(result)


@pytest.mark.asyncio
async def test_empty_gate_prevents_asr_core_and_tts_in_original_pipeline():
    """Exercise the unchanged application no-speech branch rather than only checking a detector boolean."""
    adapter, calls = fixture(segments=())

    async def forbidden(**kwargs):
        """Fail the test if a refused source can trigger a downstream model."""
        pytest.fail("downstream model was called")

    pipeline = VoicePipeline(
        asr=adapter,
        llm=SimpleNamespace(complete=forbidden),
        tts=SimpleNamespace(synthesize=forbidden),
        asr_model="fixture-asr",
        llm_model="fixture-core",
        tts_model="fixture-tts",
    )
    with pytest.raises(VoiceError, match="no_speech"):
        await pipeline.complete(uuid4(), audio(), "en", explicit_submission=True)
    assert [x[0] for x in calls] == ["vad"]
    await pipeline.shutdown()


@pytest.mark.parametrize(
    "field,value",
    [
        ("owner_id", uuid4()),
        ("source_sha256", "b" * 64),
        ("pcm_sha256", "b" * 64),
        ("sample_count", 32001),
        ("sample_count", True),
        ("first_pts", 2501),
        ("time_base_num", True),
        ("time_base_den", 16000),
        ("model_id", "other"),
        ("complete", False),
        ("complete", 1),
        ("segments", []),
        ("segments", ((0, 0),)),
        ("segments", ((False, 2),)),
        ("segments", ((1, 4), (3, 8))),
        ("segments", ((0, 32001),)),
        ("segments", ((0.0, 2),)),
        ("segments", tuple((i, i + 1) for i in range(129))),
    ],
)
@pytest.mark.asyncio
async def test_invalid_detector_evidence_is_not_no_speech(field, value):
    """Reject malformed provenance before ASR without disguising errors as valid empty evidence."""
    adapter, calls = fixture(mutate=lambda x: replace(x, **{field: value}))
    with pytest.raises(VoiceError, match="invalid_result"):
        await adapter.transcribe(uuid4(), audio(), "vi")
    assert len(calls) == 1


@pytest.mark.parametrize("bad", [None, {}, "", True])
@pytest.mark.asyncio
async def test_wrong_detector_result_type_is_rejected(bad):
    """Accept only the sealed result record rather than permissive dicts or truthy responses."""
    adapter, calls = fixture(mutate=lambda x: bad)
    with pytest.raises(VoiceError, match="invalid_result"):
        await adapter.transcribe(uuid4(), audio(), "vi")
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_detector_failure_is_not_transcribed_or_relabelled():
    """Preserve a finite dependency failure and prevent silent fallback to raw ASR."""
    adapter, calls = fixture()

    async def fail(owner, value):
        """Raise an authored backend fault without exposing its text to the caller."""
        raise RuntimeError("private backend detail")

    adapter.detector.detect = fail
    with pytest.raises(VoiceError, match="^dependency_failed$"):
        await adapter.transcribe(uuid4(), audio(), "vi")
    assert not calls


@pytest.mark.parametrize("stage", ["detector", "asr"])
@pytest.mark.asyncio
async def test_cancel_and_shutdown_join_active_dependencies(stage):
    """Hold admission through cancellation cleanup and reject another call while work is active."""
    adapter, _ = fixture()
    entered, retired = asyncio.Event(), asyncio.Event()

    async def block(*args):
        """Expose owned dependency start and guaranteed finally cleanup to the lifecycle test."""
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            retired.set()

    if stage == "detector":
        adapter.detector.detect = block
    else:
        adapter.asr.transcribe = block
    task = asyncio.create_task(adapter.transcribe(uuid4(), audio(), "vi"))
    await asyncio.wait_for(entered.wait(), 1)
    with pytest.raises(VoiceError, match="busy"):
        await adapter.transcribe(uuid4(), audio(), "vi")
    await adapter.shutdown()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert retired.is_set() and adapter.active is None
    with pytest.raises(VoiceError, match="closed"):
        await adapter.transcribe(uuid4(), audio(), "vi")


@pytest.mark.asyncio
async def test_suppressed_cancel_cannot_forward_audio():
    """Prevent a detector that swallows cancellation from subsequently invoking ASR."""
    adapter, calls = fixture()
    entered = asyncio.Event()

    async def suppress(owner, value):
        """Return apparently valid evidence after deliberately suppressing task cancellation."""
        entered.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            return decision(owner, value)

    adapter.detector.detect = suppress
    task = asyncio.create_task(adapter.transcribe(uuid4(), audio(), "vi"))
    await asyncio.wait_for(entered.wait(), 1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert not calls and adapter.active is None


@pytest.mark.asyncio
async def test_pipeline_timeout_joins_detector_and_never_reaches_asr():
    """Retain the original voice deadline across presence detection and downstream processing."""
    adapter, calls = fixture()
    retired = asyncio.Event()

    async def block(owner, value):
        """Wait for the pipeline deadline and expose dependency retirement."""
        try:
            await asyncio.Event().wait()
        finally:
            retired.set()

    adapter.detector.detect = block
    pipeline = VoicePipeline(
        asr=adapter,
        llm=None,
        tts=None,
        asr_model="fixture-asr",
        llm_model="fixture-core",
        tts_model="fixture-tts",
        timeout=0.02,
    )
    with pytest.raises(VoiceError, match="timeout"):
        await pipeline.complete(uuid4(), audio(), "vi", explicit_submission=True)
    assert retired.is_set() and not calls and adapter.active is None


@pytest.mark.parametrize(
    "field,value",
    [
        ("owner_id", uuid4()),
        ("model_id", "other"),
        ("pcm_sha256", "b" * 64),
        ("complete", False),
    ],
)
@pytest.mark.asyncio
async def test_positive_asr_result_keeps_original_binding(field, value):
    """Prevent a correctly gated source from publishing a mismatched ASR result."""
    adapter, _ = fixture()
    original = adapter.asr.transcribe

    async def wrong(*args):
        """Mutate one result field after normal fixture recognition."""
        return replace(await original(*args), **{field: value})

    adapter.asr.transcribe = wrong
    with pytest.raises(VoiceError, match="invalid_result"):
        await adapter.transcribe(uuid4(), audio(), "vi")


@pytest.mark.asyncio
async def test_positive_pipeline_preserves_original_turn_and_audio():
    """Keep original application CORE/TTS authority and clock checks in the optional composition."""
    adapter, calls = fixture()
    owner, value = uuid4(), audio()

    async def complete(**kwargs):
        """Supply one authored CORE response with unchanged profile and budgets."""
        assert kwargs["profile"] == "core" and kwargs["max_tokens"] == 512
        return CompletionResult("answer", "fixture-core", "fast", "stop")

    async def synthesize(who, answer, language):
        """Produce complete authored output without invoking a speech model."""
        return VoiceSpeech(
            who,
            digest(answer.encode()),
            language,
            "fixture-tts",
            b"\0\0" * 16000,
            16000,
        )

    pipeline = VoicePipeline(
        asr=adapter,
        llm=SimpleNamespace(complete=complete),
        tts=SimpleNamespace(synthesize=synthesize),
        asr_model="fixture-asr",
        llm_model="fixture-core",
        tts_model="fixture-tts",
    )
    turn = await pipeline.complete(owner, value, "vi", explicit_submission=True)
    assert turn.answer == "answer" and turn.source_first_pts == value.first_pts
    assert calls[-1][1] is value


@pytest.mark.asyncio
async def test_invalid_audio_and_missing_owner_never_enter_detector():
    """Check original normalized capabilities before model access rather than trusting a prior pipeline check."""
    adapter, calls = fixture()
    for owner, value, language in [
        ("owner", audio(), "vi"),
        (uuid4(), audio(), "fr"),
        (uuid4(), replace(audio(), pcm_sha256="b" * 64), "vi"),
    ]:
        with pytest.raises(VoiceError, match="invalid_input"):
            await adapter.transcribe(owner, value, language)
    assert not calls
