"""Describe ephemeral owner-bound voice-stage results without selecting models, recording devices or persistence."""

from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True, repr=False)
class VoiceTranscript:
    """Bind one fully materialized untrusted ASR result to the owner and original normalized PCM."""

    owner_id: UUID
    source_sha256: str
    pcm_sha256: str
    language: str
    text: str
    model_id: str
    complete: bool = True


@dataclass(frozen=True, slots=True, repr=False)
class VoiceSpeech:
    """Bind complete mono16k PCM16 synthesis to an exact response text and trusted expected voice identity."""

    owner_id: UUID
    text_sha256: str
    language: str
    model_id: str
    pcm_s16le: bytes
    sample_count: int
    complete: bool = True


@dataclass(frozen=True, slots=True, repr=False)
class VoiceTurn:
    """Return one complete buffered voice turn with original clocks and host timing, never a quality certification."""

    owner_id: UUID
    source_sha256: str
    pcm_sha256: str
    source_first_pts: int
    source_time_base_num: int
    source_time_base_den: int
    transcript: VoiceTranscript
    answer: str
    speech: VoiceSpeech
    stage_seconds: tuple[tuple[str, float], ...]
    buffered_latency_seconds: float
    persisted: bool = False
