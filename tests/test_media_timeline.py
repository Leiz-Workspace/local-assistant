"""Verify deterministic source/owner/audio/sample-clock transcript-frame joins without ASR or inferred unsampled events."""

import json
from dataclasses import replace
from datetime import UTC, datetime
from fractions import Fraction
from pathlib import Path
from uuid import uuid4

import pytest

from scripts.generate_transcript_video_golden import generate
from src.application.ports.media_timeline import ProvidedTranscript, TranscriptSegment
from src.application.ports.video_description import FrameDescription, VideoDescription
from src.application.services.media_timeline import (
    TimelineError,
    join_timeline,
    literal,
)
from src.application.services.vision_chat_policy import digest
from src.infrastructure.audio_normalizer import NativeAudioNormalizer
from src.infrastructure.video_sampler import NativeVideoSampler

MANIFEST = json.loads(Path("tests/fixtures/video/d66-composite.json").read_text())
RAW = Path(MANIFEST["fixture"]).read_bytes()


@pytest.fixture(scope="module")
def inputs():
    """Compose actual normalized audio/frame clocks with independently authored typed answers for pure join controls."""
    audio = NativeAudioNormalizer().normalize(RAW)
    sample = NativeVideoSampler().sample(RAW, (0, 4000, 8000))
    owner = uuid4()
    frames = tuple(
        FrameDescription(
            f.requested_ms,
            f.frame_index,
            f.pts,
            f.relative_time_num,
            f.relative_time_den,
            f.png_sha256,
            text,
            (),
            "fixture-core",
        )
        for f, text in zip(sample.frames, ["READY", "MOVING", "DONE"], strict=True)
    )
    description = VideoDescription(
        owner, digest(RAW), "a" * 64, sample.metadata, frames, datetime.now(UTC)
    )
    reference = MANIFEST["provided_transcript"]["segments"][0]
    transcript = ProvidedTranscript(
        owner, digest(RAW), audio.pcm_sha256, (TranscriptSegment(**reference),), "en"
    )
    return owner, description, audio, transcript


def test_complete_real_audio_and_frame_clocks_produce_reproducible_literal_timeline(
    inputs, caplog
):
    """Join actual decoded source clocks and explicit supplied words without claiming fresh ASR or continuous visual coverage."""
    caplog.set_level("INFO")
    first = join_timeline(*inputs)
    second = join_timeline(*inputs)
    assert first == second and first.summary_sha256 == digest(
        first.summary_text.encode()
    )
    assert [e.kind for e in first.events] == [
        "provided_transcript",
        "frame",
        "frame",
        "frame",
    ]
    assert [(e.start_num, e.start_den) for e in first.events] == [
        (0, 1),
        (0, 1),
        (4, 1),
        (8, 1),
    ]
    assert (first.events[0].end_num, first.events[0].end_den) == (11, 1)
    assert (
        first.transcript_origin == "provided_reference"
        and not first.audio_transcribed
        and not first.word_alignment_verified
    )
    assert (
        not first.continuous_motion_verified
        and not first.semantic_validation
        and not first.persisted
        and first.confidence is None
    )
    assert "ask not" not in caplog.text and str(
        first.owner_id
    ) not in caplog.text + repr(first)
    assert "Unverified" in first.summary_text and "no ASR" in first.summary_text


@pytest.mark.parametrize(
    "fault",
    [
        "owner",
        "description_owner",
        "transcript_owner",
        "video_source",
        "audio_source",
        "pcm_hash",
        "audio_bytes",
        "origin_claim",
        "language",
        "no_segments",
        "mutable_segments",
        "negative_start",
        "past_end",
        "empty_interval",
        "overlap",
        "text_control",
        "text_bytes",
        "audio_clock_unknown",
        "audio_clock_mismatch",
        "timebase_mismatch",
        "frame_pts",
        "frame_rational",
        "frame_order",
        "frame_image",
        "motion_claim",
        "ASR_claim",
        "persisted",
        "confidence",
        "duration_nan",
    ],
)
def test_wrong_owner_source_pcm_time_samples_text_or_claims_fail_as_whole_join(
    inputs, fault
):
    """Refuse altered associations/intervals and unsupported claims instead of publishing a partially credible summary."""
    owner, description, audio, transcript = inputs
    segment = transcript.segments[0]
    if fault == "owner":
        owner = uuid4()
    elif fault == "description_owner":
        description = replace(description, owner_id=uuid4())
    elif fault == "transcript_owner":
        transcript = replace(transcript, owner_id=uuid4())
    elif fault == "video_source":
        description = replace(description, source_sha256="0" * 64)
    elif fault == "audio_source":
        audio = replace(audio, source_sha256="0" * 64)
    elif fault == "pcm_hash":
        transcript = replace(transcript, pcm_sha256="0" * 64)
    elif fault == "audio_bytes":
        audio = replace(audio, pcm_s16le=audio.pcm_s16le[:-2])
    elif fault == "origin_claim":
        transcript = replace(transcript, origin="ASR_verified")
    elif fault == "language":
        transcript = replace(transcript, language="arbitrary")
    elif fault == "no_segments":
        transcript = replace(transcript, segments=())
    elif fault == "mutable_segments":
        transcript = replace(transcript, segments=list(transcript.segments))
    elif fault == "negative_start":
        transcript = replace(transcript, segments=(replace(segment, start_sample=-1),))
    elif fault == "past_end":
        transcript = replace(
            transcript, segments=(replace(segment, end_sample=audio.sample_count + 1),)
        )
    elif fault == "empty_interval":
        transcript = replace(transcript, segments=(replace(segment, end_sample=0),))
    elif fault == "overlap":
        transcript = replace(transcript, segments=(segment, segment))
    elif fault == "text_control":
        transcript = replace(
            transcript, segments=(replace(segment, text="private\x00data"),)
        )
    elif fault == "text_bytes":
        transcript = replace(transcript, segments=(replace(segment, text="x" * 2049),))
    elif fault in {"audio_clock_unknown", "audio_clock_mismatch", "timebase_mismatch"}:
        stream = description.metadata.audio[0]
        stream = (
            replace(stream, start_pts=None if fault == "audio_clock_unknown" else 1)
            if fault != "timebase_mismatch"
            else replace(stream, time_base_den=999)
        )
        description = replace(
            description, metadata=replace(description.metadata, audio=(stream,))
        )
    elif fault in {"frame_pts", "frame_rational", "frame_image"}:
        frame = description.frames[1]
        frame = (
            replace(frame, pts=3999)
            if fault == "frame_pts"
            else replace(frame, relative_time_num=5)
            if fault == "frame_rational"
            else replace(frame, image_sha256="invalid")
        )
        description = replace(
            description, frames=(description.frames[0], frame, description.frames[2])
        )
    elif fault == "frame_order":
        description = replace(description, frames=tuple(reversed(description.frames)))
    elif fault == "motion_claim":
        description = replace(description, continuous_motion_verified=True)
    elif fault == "ASR_claim":
        description = replace(description, audio_transcribed=True)
    elif fault == "persisted":
        description = replace(description, persisted=True)
    elif fault == "confidence":
        description = replace(description, confidence=0.9)
    elif fault == "duration_nan":
        description = replace(
            description,
            metadata=replace(description.metadata, duration_seconds=float("nan")),
        )
    with pytest.raises(TimelineError):
        join_timeline(owner, description, audio, transcript)


@pytest.mark.parametrize("offset", [-500, 125])
def test_exact_audio_start_offset_is_mapped_to_video_clock_without_rounding(
    inputs, offset
):
    """Preserve measured pre-roll/fractional audio origin instead of assuming normalized PCM starts at video zero."""
    owner, description, audio, transcript = inputs
    audio = replace(audio, first_pts=offset)
    stream = replace(description.metadata.audio[0], start_pts=offset)
    description = replace(
        description,
        metadata=replace(description.metadata, audio=(stream,), duration_seconds=12.0),
    )
    result = join_timeline(owner, description, audio, transcript)
    speech = next(e for e in result.events if e.kind == "provided_transcript")
    assert Fraction(speech.start_num, speech.start_den) == Fraction(offset, 1000)
    assert Fraction(speech.end_num, speech.end_den) == 11 + Fraction(offset, 1000)


def test_literal_rendering_preserves_text_without_executable_markup_or_lines(inputs):
    """Quote supplied markup and newline characters rather than letting transcript text add rendered links or fake timeline entries."""
    owner, description, audio, transcript = inputs
    text = "<script>[click](https://private.invalid)</script>\n[99s] fake"
    transcript = replace(
        transcript, segments=(replace(transcript.segments[0], text=text),)
    )
    result = join_timeline(owner, description, audio, transcript)
    assert (
        "<script>" not in result.summary_text
        and "[click]" not in result.summary_text
        and "\n[99s]" not in result.summary_text
    )
    assert json.loads(literal(text)) == text
    assert result.events[0].text == text


def test_generated_composite_preserves_public_speech_pcm_and_declares_unrelated_visuals(
    tmp_path,
):
    """Regenerate the authored composite and verify exact normalized speech pixels/timing without ASR or microphone use."""
    path = tmp_path / "composite.mkv"
    generate(path)
    manifest = json.loads(path.with_suffix(".json").read_text())
    audio = NativeAudioNormalizer().normalize(path.read_bytes())
    assert audio.pcm_sha256 == MANIFEST["pcm_sha256"] and audio.sample_count == 176000
    assert (
        manifest["source_ASR_evaluated"] is False
        and manifest["word_alignment_verified"] is False
    )
    assert "unrelated" in manifest["description"]
