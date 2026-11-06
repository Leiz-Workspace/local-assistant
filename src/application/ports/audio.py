"""Describe ephemeral source-bound normalized PCM and actual decoded audio clocks without recording, ASR or file authorization."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True, repr=False)
class NormalizedAudio:
    """Bind normalized mono PCM to complete original bytes and a continuous decoded source-sample timeline."""

    source_sha256: str
    pcm_sha256: str
    pcm_s16le: bytes
    sample_count: int
    source_codec: str
    source_sample_rate: int
    source_channels: int
    source_sample_count: int
    time_base_num: int
    time_base_den: int
    first_pts: int
    sample_rate: int = 16000
    channels: int = 1
    processor: str = "native-pcm-v1"
    content_trust: str = "untrusted"
    persisted: bool = False
