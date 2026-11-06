"""Validate complete explicit audio bytes and bounded isolated PCM/source-clock responses without host codec decoding."""

import base64
import logging
from fractions import Fraction

from src.application.ports.audio import NormalizedAudio
from src.application.services.video_contract import integer
from src.application.services.vision_chat_policy import digest

logger = logging.getLogger(__name__)
MAX_SOURCE = 32 * 1024**2
MAX_OUTPUT = 2 * 1024**2
MAX_SAMPLES = 480000
ERRORS = frozenset(
    {
        "audio_invalid_input",
        "audio_invalid_content",
        "audio_limits_exceeded",
        "audio_clock_unavailable",
        "audio_processing_timeout",
        "audio_processing_unavailable",
        "audio_invalid_result",
    }
)


class AudioError(Exception):
    """Expose finite native audio failures without private signal, transcript, path or decoder diagnostics."""

    def __init__(self, code):
        """Retain bounded audit error metadata and discard unknown backend-controlled content."""
        self.code = (
            code
            if type(code) is str and code in ERRORS
            else "audio_processing_unavailable"
        )
        super().__init__(self.code)
        logger.warning("audio_rejected code=%s", self.code)


def audio_input(raw):
    """Admit only complete bounded immutable explicit bytes, never a location or automatic recording request."""
    if type(raw) is not bytes or not 1 <= len(raw) <= MAX_SOURCE:
        raise AudioError("audio_invalid_input")
    logger.info("audio_source_admitted bytes=%d", len(raw))
    return digest(raw)


def resolve_audio(value, source_sha):
    """Verify whole PCM/hash/count and rational decoded-clock metadata before returning an immutable untrusted audio capability."""
    try:
        keys = {
            "source_sha256",
            "pcm_sha256",
            "pcm_base64",
            "sample_count",
            "source_codec",
            "source_sample_rate",
            "source_channels",
            "source_sample_count",
            "time_base_num",
            "time_base_den",
            "first_pts",
            "sample_rate",
            "channels",
            "processor",
        }
        if (
            type(value) is not dict
            or set(value) != keys
            or value["source_sha256"] != source_sha
            or value["source_codec"] not in {"flac", "pcm_s16le"}
            or value["processor"] != "native-pcm-v1"
        ):
            raise ValueError()
        if (
            type(value["sample_rate"]) is not int
            or value["sample_rate"] != 16000
            or type(value["channels"]) is not int
            or value["channels"] != 1
        ):
            raise ValueError()
        count = integer(value["sample_count"], 1, MAX_SAMPLES)
        rate = integer(value["source_sample_rate"], 8000, 48000)
        channels = integer(value["source_channels"], 1, 2)
        source_count = integer(value["source_sample_count"], 1, 30 * rate)
        num = integer(value["time_base_num"], 1, 10**9)
        den = integer(value["time_base_den"], 1, 10**9)
        pts = integer(value["first_pts"], -(2**53), 2**53)
        if abs(Fraction(count, 16000) - Fraction(source_count, rate)) > Fraction(
            1, 16000
        ):
            raise ValueError()
        if (
            type(value["pcm_base64"]) is not str
            or not 1 <= len(value["pcm_base64"]) <= (2 * MAX_SAMPLES + 2) // 3 * 4
        ):
            raise ValueError()
        pcm = base64.b64decode(value["pcm_base64"], validate=True)
        if len(pcm) != count * 2 or digest(pcm) != value["pcm_sha256"]:
            raise ValueError()
        if (
            type(source_sha) is not str
            or len(source_sha) != 64
            or any(c not in "0123456789abcdef" for c in source_sha)
        ):
            raise ValueError()
        logger.info("normalized_audio_verified samples=%d source_rate=%d", count, rate)
        return NormalizedAudio(
            source_sha,
            value["pcm_sha256"],
            pcm,
            count,
            value["source_codec"],
            rate,
            channels,
            source_count,
            num,
            den,
            pts,
        )
    except Exception:
        raise AudioError("audio_invalid_result") from None
