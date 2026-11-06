"""Describe sparse unverified frame observations with immutable host timestamps and no continuous-video or audio inference authority."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from src.application.ports.video import VideoMetadata


@dataclass(frozen=True, slots=True, repr=False)
class FrameDescription:
    """Bind one original CORE image answer to exact normalized frame pixels and decoded host timing."""

    requested_ms: int
    frame_index: int
    pts: int
    relative_time_num: int
    relative_time_den: int
    image_sha256: str
    answer: str
    uncertainties: tuple[str, ...]
    model_id: str


@dataclass(frozen=True, slots=True, repr=False)
class VideoDescription:
    """Return only sampled image observations, not a continuous-motion, speech, authorization or semantic-truth certificate."""

    owner_id: UUID
    source_sha256: str
    question_sha256: str
    metadata: VideoMetadata
    frames: tuple[FrameDescription, ...]
    received_at: datetime
    observed_frames_only: bool = True
    continuous_motion_verified: bool = False
    audio_transcribed: bool = False
    semantic_validation: bool = False
    confidence: None = None
    persisted: bool = False
