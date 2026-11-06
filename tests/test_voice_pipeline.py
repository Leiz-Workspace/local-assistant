"""Exercise owner-bound buffered voice composition, exact clocks, admission and joined cancellation without selecting real models."""

import asyncio
from dataclasses import replace
from fractions import Fraction
from types import SimpleNamespace
from uuid import uuid4

import pytest

from apps.api.runtime.presets import calculate_budget
from src.application.ports.audio import NormalizedAudio
from src.application.ports.inference import CompletionResult
from src.application.ports.voice import VoiceSpeech, VoiceTranscript
from src.application.services.voice_pipeline import (
    VoiceError,
    VoicePipeline,
    digest,
    source_spans,
)


def audio():
    """Create a source-bound authored PCM capability with a nonzero original clock."""
    raw = b"\x00\x00" * 32000
    return NormalizedAudio(
        "a" * 64, digest(raw), raw, 32000, "pcm_s16le", 16000, 1, 32000, 1, 1000, 2500
    )


def fixture(timeout=2):
    """Inject finite independent stages that retain exact model/owner/hash identities and record their order."""
    calls = []

    async def transcribe(owner, value, language):
        """Return an authored transcript rather than asserting any real ASR quality."""
        calls.append("asr")
        return VoiceTranscript(
            owner,
            value.source_sha256,
            value.pcm_sha256,
            language,
            "hello private-speech",
            "asr-fixture",
        )

    async def complete(**kwargs):
        """Observe text-only CORE authority and return one complete fixture response."""
        calls.append("llm")
        assert kwargs["profile"] == "core" and "tools" not in kwargs
        calculate_budget(
            preset=kwargs["preset"],
            input_tokens=100,
            requested_max_tokens=kwargs["max_tokens"],
        )
        return CompletionResult("private-answer", "llm-fixture", "fast", "stop")

    async def synthesize(owner, answer, language):
        """Return one bounded source-text-bound authored output without a neural voice."""
        calls.append("tts")
        return VoiceSpeech(
            owner,
            digest(answer.encode()),
            language,
            "tts-fixture",
            b"\x00\x00" * 16000,
            16000,
        )

    service = VoicePipeline(
        asr=SimpleNamespace(transcribe=transcribe),
        llm=SimpleNamespace(complete=complete),
        tts=SimpleNamespace(synthesize=synthesize),
        asr_model="asr-fixture",
        llm_model="llm-fixture",
        tts_model="tts-fixture",
        timeout=timeout,
    )
    return service, calls


@pytest.mark.asyncio
async def test_complete_buffers_all_stages_with_owner_clock_and_redacted_audit(caplog):
    """Expose no partial turn, audio or transcript in logs and retain the unchanged source clock."""
    caplog.set_level("INFO")
    service, calls = fixture()
    owner = uuid4()
    result = await service.complete(owner, audio(), "en", explicit_submission=True)
    assert calls == ["asr", "llm", "tts"]
    assert result.owner_id == owner and result.source_first_pts == 2500
    assert result.source_time_base_den == 1000 and not result.persisted
    assert result.buffered_latency_seconds >= sum(
        value for _, value in result.stage_seconds
    )
    assert "private-speech" not in caplog.text and "private-answer" not in caplog.text
    assert "private" not in repr(result)


@pytest.mark.parametrize(
    "field,value",
    [
        ("pcm_sha256", "b" * 64),
        ("sample_count", True),
        ("persisted", True),
        ("sample_rate", 48000),
        ("first_pts", False),
        ("time_base_den", 0),
        ("source_sha256", "x" * 64),
    ],
)
@pytest.mark.asyncio
async def test_invalid_source_is_rejected_before_any_dependency(field, value):
    """Reject forged media capabilities rather than relying on the caller's prior normalization."""
    service, calls = fixture()
    with pytest.raises(VoiceError, match="invalid_input"):
        await service.complete(
            uuid4(), replace(audio(), **{field: value}), "en", explicit_submission=True
        )
    assert not calls


@pytest.mark.asyncio
async def test_missing_explicit_submission_and_invalid_owner_cannot_start_work():
    """Require a separate trusted submission action after recording consent."""
    service, calls = fixture()
    for owner, submitted in [(uuid4(), False), (uuid4(), 1), ("not-an-owner", True)]:
        with pytest.raises(VoiceError, match="invalid_input"):
            await service.complete(owner, audio(), "en", explicit_submission=submitted)
    assert not calls


@pytest.mark.parametrize(
    "field,value",
    [
        ("owner_id", uuid4()),
        ("source_sha256", "b" * 64),
        ("pcm_sha256", "c" * 64),
        ("model_id", "wrong-model"),
        ("complete", 1),
        ("language", "vi"),
        ("text", "bad\x00text"),
    ],
)
@pytest.mark.asyncio
async def test_wrong_owner_or_source_transcript_cannot_reach_llm(field, value):
    """Bind the stage result to the admitted request before disclosing text to the next dependency."""
    service, calls = fixture()
    original = service.asr.transcribe

    async def changed(*args):
        """Alter a single transcript capability field to model a corrupt or substituted result."""
        return replace(await original(*args), **{field: value})

    service.asr.transcribe = changed
    with pytest.raises(VoiceError, match="invalid_result"):
        await service.complete(uuid4(), audio(), "en", explicit_submission=True)
    assert calls == ["asr"] and service.active is None


@pytest.mark.asyncio
async def test_no_speech_short_circuits_without_an_llm_or_tts_request():
    """Treat an empty actual ASR transcript as no speech rather than inventing a reply."""
    service, calls = fixture()

    async def empty(owner, value, language):
        """Return a valid empty ASR observation for the admitted audio."""
        return VoiceTranscript(
            owner, value.source_sha256, value.pcm_sha256, language, "", "asr-fixture"
        )

    service.asr.transcribe = empty
    with pytest.raises(VoiceError, match="no_speech"):
        await service.complete(uuid4(), audio(), "en", explicit_submission=True)
    assert not calls


@pytest.mark.parametrize("stage", ["asr", "llm", "tts"])
@pytest.mark.asyncio
async def test_caller_cancellation_joins_cleanup_before_releasing_busy_admission(stage):
    """Retain ownership through repeated caller cancellation and dependency cleanup at every stage."""
    service, _ = fixture()
    entered, releasing, finished = asyncio.Event(), asyncio.Event(), asyncio.Event()

    async def blocked(*args, **kwargs):
        """Delay cancellation cleanup to expose premature admission release or unjoined shutdown."""
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            await releasing.wait()
            finished.set()

    setattr(
        getattr(service, stage),
        {"asr": "transcribe", "llm": "complete", "tts": "synthesize"}[stage],
        blocked,
    )
    operation = asyncio.create_task(
        service.complete(uuid4(), audio(), "en", explicit_submission=True)
    )
    await entered.wait()
    operation.cancel()
    await asyncio.sleep(0)
    operation.cancel()
    with pytest.raises(VoiceError, match="busy"):
        await service.complete(uuid4(), audio(), "en", explicit_submission=True)
    assert not finished.is_set()
    releasing.set()
    with pytest.raises(asyncio.CancelledError):
        await operation
    assert finished.is_set() and service.active is None


@pytest.mark.asyncio
async def test_timeout_and_suppressed_cancellation_never_publish_success():
    """Reject late ASR output even when a backend catches its deadline cancellation."""
    service, calls = fixture(timeout=0.01)
    original = service.asr.transcribe

    async def late(*args):
        """Deliberately suppress timeout cancellation to exercise the post-stage host check."""
        try:
            await asyncio.sleep(1)
        except asyncio.CancelledError:
            pass
        return await original(*args)

    service.asr.transcribe = late
    with pytest.raises(VoiceError, match="timeout"):
        await service.complete(uuid4(), audio(), "en", explicit_submission=True)
    assert calls == ["asr"] and service.active is None


@pytest.mark.parametrize(
    "field,value",
    [
        ("source_sample_count", 16000),
        ("source_sample_rate", True),
        ("source_codec", "arbitrary-codec"),
        ("time_base_num", False),
    ],
)
@pytest.mark.asyncio
async def test_original_source_clock_and_codec_are_fully_revalidated(field, value):
    """Apply the existing native normalized-audio contract before disclosing data to ASR."""
    service, calls = fixture()
    with pytest.raises(VoiceError, match="invalid_input"):
        await service.complete(
            uuid4(), replace(audio(), **{field: value}), "en", explicit_submission=True
        )
    assert not calls


@pytest.mark.parametrize(
    "stage,field,value",
    [
        ("llm", "model_id", "other-model"),
        ("llm", "finish_reason", "length"),
        ("llm", "content", "x" * 2049),
        ("tts", "owner_id", uuid4()),
        ("tts", "text_sha256", "c" * 64),
        ("tts", "language", "vi"),
        ("tts", "model_id", "other-voice"),
        ("tts", "complete", False),
        ("tts", "sample_count", True),
        ("tts", "pcm_s16le", b"bad"),
    ],
)
@pytest.mark.asyncio
async def test_corrupt_text_or_speech_results_never_publish_a_turn(stage, field, value):
    """Reject output substitution, truncation and corrupt audio rather than promoting partial pipeline success."""
    service, calls = fixture()
    adapter = getattr(service, stage)
    method = "complete" if stage == "llm" else "synthesize"
    original = getattr(adapter, method)

    async def changed(*args, **kwargs):
        """Change one downstream binding while retaining every other valid fixture property."""
        return replace(await original(*args, **kwargs), **{field: value})

    setattr(adapter, method, changed)
    with pytest.raises(VoiceError, match="invalid_result"):
        await service.complete(uuid4(), audio(), "en", explicit_submission=True)
    assert service.active is None
    assert calls == (["asr", "llm"] if stage == "llm" else ["asr", "llm", "tts"])


@pytest.mark.asyncio
async def test_shutdown_permanently_closes_admission_and_joins_current_task():
    """Finish owned work before shutdown returns and reject all later user submissions."""
    service, _ = fixture()
    entered, finished = asyncio.Event(), asyncio.Event()

    async def blocked(*args):
        """Record actual cleanup completion when the service shuts down."""
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            finished.set()

    service.asr.transcribe = blocked
    operation = asyncio.create_task(
        service.complete(uuid4(), audio(), "en", explicit_submission=True)
    )
    await entered.wait()
    await service.shutdown()
    with pytest.raises(asyncio.CancelledError):
        await operation
    assert finished.is_set()
    with pytest.raises(VoiceError, match="closed"):
        await service.complete(uuid4(), audio(), "en", explicit_submission=True)


def test_vad_mapping_preserves_nonzero_origin_and_removed_gaps():
    """Keep exact rational source intervals instead of pretending gated samples form a continuous original clock."""
    result = source_spans(audio(), ((0, 8000), (24000, 32000)))
    assert result == (
        (0, 8000, Fraction(5, 2), Fraction(3)),
        (24000, 32000, Fraction(4), Fraction(9, 2)),
    )
    for spans in [
        ((0, 8000), (7999, 9000)),
        ((0, True),),
        ((-1, 10),),
        ((0, 32001),),
        [[0, 1]],
    ]:
        with pytest.raises(VoiceError, match="invalid_input"):
            source_spans(audio(), spans)
