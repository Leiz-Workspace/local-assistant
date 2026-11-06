"""Create bounded detector-only amplitude views while retaining original PCM for the research ASR gate."""

from dataclasses import dataclass
from src.infrastructure.voice.presence import VAD_MODEL

POLICY = "detector-peak-half-boost32-v1"


@dataclass(frozen=True, slots=True, repr=False)
class DetectorView:
    """Bind one full-length detector copy to the original PCM and a fixed non-clipping gain policy."""

    pcm_sha256: str
    waveform_sha256: str
    sample_count: int
    gain: float
    waveform_f32: bytes
    policy: str = POLICY


@dataclass(frozen=True, slots=True, repr=False)
class ViewObservation:
    """Describe a complete model observation of one exact detector-view waveform."""

    waveform_sha256: str
    sample_count: int
    segments: tuple[tuple[int, int], ...]
    model_id: str = VAD_MODEL
    complete: bool = True
