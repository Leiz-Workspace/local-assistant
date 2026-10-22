"""Describe immutable decoded video metadata and timestamp-bound private frames without playback, persistence or action authority."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AudioMetadata:
    """Report the existence and format of a bounded audio stream without claiming speech transcription."""

    index: int
    codec: str
    sample_rate: int
    channels: int
    time_base_num: int
    time_base_den: int
    start_pts: int | None


@dataclass(frozen=True, slots=True)
class VideoMetadata:
    """Preserve decoded timing origin/time base and container-reported duration, which may include a nonzero start offset."""

    width: int
    height: int
    codec: str
    time_base_num: int
    time_base_den: int
    origin_pts: int
    duration_seconds: float
    frame_count: int
    audio: tuple[AudioMetadata, ...]


@dataclass(frozen=True, slots=True, repr=False)
class VideoFrame:
    """Bind exact normalized pixels to a decoded PTS and keep requested time separate from observed relative time."""

    requested_ms: int
    frame_index: int
    pts: int
    relative_time_num: int
    relative_time_den: int
    width: int
    height: int
    png: bytes
    png_sha256: str


@dataclass(frozen=True, slots=True, repr=False)
class VideoSample:
    """Carry untrusted source-bound frames and metadata without file authorization, inference or durable retention."""

    source_sha256: str
    metadata: VideoMetadata
    frames: tuple[VideoFrame, ...]
    processor: str = "ffmpeg-frames-v1"
    content_trust: str = "untrusted"
    persisted: bool = False
