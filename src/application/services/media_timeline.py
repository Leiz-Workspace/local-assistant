"""Join bounded supplied transcript samples and sparse frame descriptions using exact source clocks without ASR, interpolation or model calls."""

import base64
import json
import logging
import math
import re
from dataclasses import asdict
from fractions import Fraction
from uuid import UUID

from src.application.ports.audio import NormalizedAudio
from src.application.ports.media_timeline import (
    MediaTimeline,
    ProvidedTranscript,
    TimelineEvent,
    TranscriptSegment,
)
from src.application.ports.video import VideoMetadata
from src.application.ports.video_description import FrameDescription, VideoDescription
from src.application.services.audio_contract import resolve_audio
from src.application.services.video_contract import integer
from src.application.services.vision_chat_policy import bounded_text, digest

logger = logging.getLogger(__name__)


class TimelineError(Exception):
    """Expose a finite join error without source IDs, waveform, transcript or model-controlled details."""

    def __init__(self):
        """Record only rejected composition metadata rather than private supplied text."""
        super().__init__("media_timeline_invalid")
        self.code = "media_timeline_invalid"
        logger.warning("media_timeline_rejected")


def literal(value):
    """Encode literal JSON data while escaping markup punctuation for safe plain-text timeline presentation."""
    text = json.dumps(value, ensure_ascii=False)
    for char in "<>&`*_[]()!":
        text = text.replace(char, f"\\u{ord(char):04x}")
    return text


def checked_audio(audio, source_sha):
    """Revalidate complete normalized PCM bytes and source clocks before using any supplied transcript interval."""
    if (
        type(audio) is not NormalizedAudio
        or audio.persisted is not False
        or audio.content_trust != "untrusted"
    ):
        raise ValueError()
    count = integer(audio.sample_count, 1, 480000)
    if type(audio.pcm_s16le) is not bytes or len(audio.pcm_s16le) != count * 2:
        raise ValueError()
    value = asdict(audio)
    value.pop("persisted")
    value.pop("content_trust")
    value["pcm_base64"] = base64.b64encode(value.pop("pcm_s16le")).decode()
    return resolve_audio(value, source_sha)


def event(kind, index, start, end, text, uncertainties=()):
    """Freeze already validated exact rational time endpoints without formatting them as approximate decimal seconds."""
    return TimelineEvent(
        kind,
        index,
        start.numerator,
        start.denominator,
        end.numerator,
        end.denominator,
        text,
        uncertainties,
    )


def render(source_sha, pcm_sha, events):
    """Render deterministic labelled literal observations without executable markup, generated times or hidden media history."""
    rows = [
        "Unverified provided-transcript and sampled-frame timeline.",
        "Speech text is supplied; no ASR, word alignment or continuous-motion verification.",
        f"Source SHA256: {source_sha}",
        f"Normalized PCM SHA256: {pcm_sha}",
    ]
    for item in events:
        time = f"{item.start_num}/{item.start_den}s"
        if item.kind == "provided_transcript":
            time += f"..{item.end_num}/{item.end_den}s"
        rows.append(
            f"[{time}] {item.kind} {item.index}: {literal(item.text)}; uncertainties={literal(list(item.uncertainties))}"
        )
    result = "\n".join(rows) + "\n"
    if len(result.encode()) > 32768:
        raise ValueError()
    return result


def event_order(row):
    """Order exact event times with supplied transcript windows before frame observations at a shared instant."""
    return (
        Fraction(row.start_num, row.start_den),
        0 if row.kind == "provided_transcript" else 1,
        row.index,
    )


def join_timeline(owner, description, audio, transcript):
    """Validate exact owner/source/audio/sample/time associations and return only explicit supplied/sampled observations."""
    try:
        if (
            type(owner) is not UUID
            or type(description) is not VideoDescription
            or type(transcript) is not ProvidedTranscript
        ):
            raise ValueError()
        if (
            owner != description.owner_id
            or owner != transcript.owner_id
            or description.source_sha256 != transcript.source_sha256
        ):
            raise ValueError()
        if (
            description.observed_frames_only is not True
            or description.continuous_motion_verified is not False
            or description.audio_transcribed is not False
            or description.semantic_validation is not False
            or description.persisted is not False
            or description.confidence is not None
        ):
            raise ValueError()
        if transcript.origin != "provided_reference" or transcript.language not in {
            "en",
            "vi",
            "unknown",
        }:
            raise ValueError()
        audio = checked_audio(audio, description.source_sha256)
        if transcript.pcm_sha256 != audio.pcm_sha256:
            raise ValueError()
        meta = description.metadata
        if (
            type(meta) is not VideoMetadata
            or type(meta.audio) is not tuple
            or len(meta.audio) != 1
        ):
            raise ValueError()
        stream = meta.audio[0]
        if (
            stream.codec != audio.source_codec
            or stream.sample_rate != audio.source_sample_rate
            or stream.channels != audio.source_channels
            or stream.time_base_num != audio.time_base_num
            or stream.time_base_den != audio.time_base_den
        ):
            raise ValueError()
        if stream.start_pts is None or stream.start_pts != audio.first_pts:
            raise ValueError()
        origin = integer(meta.origin_pts, -(2**53), 2**53) * Fraction(
            integer(meta.time_base_num, 1, 10**9), integer(meta.time_base_den, 1, 10**9)
        )
        offset = (
            audio.first_pts * Fraction(audio.time_base_num, audio.time_base_den)
            - origin
        )
        if (
            type(meta.duration_seconds) not in (int, float)
            or not math.isfinite(meta.duration_seconds)
            or not 0 < meta.duration_seconds <= 30
        ):
            raise ValueError()
        duration = Fraction(str(meta.duration_seconds))
        if offset + Fraction(audio.sample_count, 16000) > duration:
            raise ValueError()
        if abs(offset) > 30:
            raise ValueError()
        if (
            type(transcript.segments) is not tuple
            or not 1 <= len(transcript.segments) <= 32
        ):
            raise ValueError()
        events = []
        previous_end = 0
        total_bytes = 0
        for index, segment in enumerate(transcript.segments):
            if type(segment) is not TranscriptSegment:
                raise ValueError()
            start = integer(segment.start_sample, 0, audio.sample_count - 1)
            end = integer(segment.end_sample, start + 1, audio.sample_count)
            if start < previous_end or bounded_text(segment.text, 2048) != segment.text:
                raise ValueError()
            total_bytes += len(segment.text.encode())
            previous_end = end
            if total_bytes > 8192:
                raise ValueError()
            events.append(
                event(
                    "provided_transcript",
                    index,
                    offset + Fraction(start, 16000),
                    offset + Fraction(end, 16000),
                    segment.text,
                )
            )
        if (
            type(description.frames) is not tuple
            or not 1 <= len(description.frames) <= 3
        ):
            raise ValueError()
        previous_target = -1
        previous_index = -1
        previous_time = None
        for frame in description.frames:
            if type(frame) is not FrameDescription:
                raise ValueError()
            index = integer(frame.frame_index, 0, integer(meta.frame_count, 1, 900) - 1)
            target = integer(frame.requested_ms, 0, 30000)
            pts = integer(frame.pts, meta.origin_pts, 2**53)
            time = (pts - meta.origin_pts) * Fraction(
                meta.time_base_num, meta.time_base_den
            )
            if (
                integer(frame.relative_time_num, 0, 2**63) != time.numerator
                or integer(frame.relative_time_den, 1, 10**9) != time.denominator
            ):
                raise ValueError()
            if (
                target <= previous_target
                or index < previous_index
                or previous_time is not None
                and time < previous_time
                or time < Fraction(target, 1000)
                or time > duration
            ):
                raise ValueError()
            if (
                re.fullmatch("[0-9a-f]{64}", frame.image_sha256) is None
                or bounded_text(frame.answer, 8192) != frame.answer
                or type(frame.uncertainties) is not tuple
                or len(frame.uncertainties) > 16
                or any(bounded_text(s, 512) != s for s in frame.uncertainties)
            ):
                raise ValueError()
            events.append(
                event("frame", index, time, time, frame.answer, frame.uncertainties)
            )
            previous_target, previous_index, previous_time = target, index, time
        events.sort(key=event_order)
        summary = render(description.source_sha256, audio.pcm_sha256, events)
        result = MediaTimeline(
            owner,
            description.source_sha256,
            audio.pcm_sha256,
            tuple(events),
            summary,
            digest(summary.encode()),
        )
        logger.info(
            "media_timeline_joined frames=%d transcript_segments=%d",
            len(description.frames),
            len(transcript.segments),
        )
        return result
    except Exception:
        raise TimelineError() from None
