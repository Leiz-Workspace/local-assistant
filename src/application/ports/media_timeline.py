"""Describe explicitly supplied unverified transcripts and sparse source-clock-bound timeline summaries without raw media retention."""

from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True, repr=False)
class TranscriptSegment:
    """Bind supplied unverified text to an explicit normalized PCM sample interval, not recognized word alignment."""

    start_sample: int
    end_sample: int
    text: str


@dataclass(frozen=True, slots=True, repr=False)
class ProvidedTranscript:
    """Associate externally provided reference text with one owner/video/normalized audio without claiming ASR or human certification."""

    owner_id: UUID
    source_sha256: str
    pcm_sha256: str
    segments: tuple[TranscriptSegment, ...]
    language: str = "unknown"
    origin: str = "provided_reference"


@dataclass(frozen=True, slots=True, repr=False)
class TimelineEvent:
    """Preserve exact rational video-relative endpoints and literal supplied text or sparse frame observation."""

    kind: str
    index: int
    start_num: int
    start_den: int
    end_num: int
    end_den: int
    text: str
    uncertainties: tuple[str, ...]


@dataclass(frozen=True, slots=True, repr=False)
class MediaTimeline:
    """Return an unverified reproducible supplied-speech/frame timeline without raw PCM, images or inferred continuous events."""

    owner_id: UUID
    source_sha256: str
    pcm_sha256: str
    events: tuple[TimelineEvent, ...]
    summary_text: str
    summary_sha256: str
    transcript_origin: str = "provided_reference"
    audio_transcribed: bool = False
    word_alignment_verified: bool = False
    continuous_motion_verified: bool = False
    semantic_validation: bool = False
    confidence: None = None
    persisted: bool = False
