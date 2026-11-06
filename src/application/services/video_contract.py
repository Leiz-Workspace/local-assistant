"""Validate complete bounded video input and isolated frame responses without decoding source pixels on the host."""

import base64
import logging
import math
from fractions import Fraction

from src.application.ports.video import (
    AudioMetadata,
    VideoFrame,
    VideoMetadata,
    VideoSample,
)
from src.application.ports.vision_chat import NormalizedImage
from src.application.services.ocr_contract import OCR_VERSION
from src.application.services.vision_chat_policy import digest, validate_image

logger = logging.getLogger(__name__)
MAX_SOURCE = 32 * 1024**2
MAX_OUTPUT = 5 * 1024**2
MAX_FRAME = 1024**2
ERRORS = frozenset(
    {
        "video_invalid_input",
        "video_invalid_content",
        "video_limits_exceeded",
        "video_time_unavailable",
        "video_processing_timeout",
        "video_processing_unavailable",
        "video_invalid_result",
    }
)
VIDEO_CODECS = {"h264", "vp9", "ffv1"}
AUDIO_CODECS = {"aac", "opus", "pcm_s16le"}


class VideoError(Exception):
    """Expose only finite video failure codes without media bytes, paths or decoder exception details."""

    def __init__(self, code):
        """Record bounded audit metadata while discarding unknown child-controlled text."""
        self.code = (
            code
            if type(code) is str and code in ERRORS
            else "video_processing_unavailable"
        )
        super().__init__(self.code)
        logger.warning("video_rejected code=%s", self.code)


def schedule(targets):
    """Require one to three unique increasing millisecond targets without accepting booleans or arbitrary iterables."""
    if (
        type(targets) is not tuple
        or not 1 <= len(targets) <= 3
        or any(type(v) is not int or not 0 <= v <= 30000 for v in targets)
        or list(targets) != sorted(set(targets))
    ):
        raise VideoError("video_invalid_input")
    return targets


def video_input(raw, targets):
    """Admit bounded explicit immutable bytes and a complete fixed schedule without opening a user location."""
    schedule(targets)
    if type(raw) is not bytes or not 1 <= len(raw) <= MAX_SOURCE:
        raise VideoError("video_invalid_input")
    logger.info("video_input_admitted bytes=%d frames=%d", len(raw), len(targets))
    return digest(raw)


def integer(value, lower, upper):
    """Reject coerced or out-of-range timing, geometry and stream counters."""
    if type(value) is not int or not lower <= value <= upper:
        raise ValueError("integer")
    return value


def resolve_video(value, source_sha, targets):
    """Verify exact response shape, source binding, decoded rational timestamps and canonical normalized PNGs before publication."""
    try:
        schedule(targets)
        if (
            type(value) is not dict
            or set(value) != {"source_sha256", "metadata", "frames", "processor"}
            or value["source_sha256"] != source_sha
            or value["processor"] != "ffmpeg-frames-v1"
        ):
            raise ValueError("shape")
        meta = value["metadata"]
        keys = {
            "width",
            "height",
            "codec",
            "time_base_num",
            "time_base_den",
            "origin_pts",
            "duration_seconds",
            "frame_count",
            "audio",
        }
        if (
            type(meta) is not dict
            or set(meta) != keys
            or meta["codec"] not in VIDEO_CODECS
        ):
            raise ValueError("metadata")
        width, height = (
            integer(meta["width"], 1, 1920),
            integer(meta["height"], 1, 1920),
        )
        if width * height > 2073600 or max(width, height) > 1920:
            raise ValueError("pixels")
        num, den = (
            integer(meta["time_base_num"], 1, 1000000000),
            integer(meta["time_base_den"], 1, 1000000000),
        )
        origin = integer(meta["origin_pts"], -(2**53), 2**53)
        count = integer(meta["frame_count"], 1, 900)
        duration = meta["duration_seconds"]
        if (
            type(duration) not in (int, float)
            or not math.isfinite(duration)
            or not 0 < duration <= 30
        ):
            raise ValueError("duration")
        if type(meta["audio"]) is not list or len(meta["audio"]) > 1:
            raise ValueError("audio")
        audio = []
        for row in meta["audio"]:
            if (
                type(row) is not dict
                or set(row)
                != {
                    "index",
                    "codec",
                    "sample_rate",
                    "channels",
                    "time_base_num",
                    "time_base_den",
                    "start_pts",
                }
                or row["codec"] not in AUDIO_CODECS
            ):
                raise ValueError("audio")
            audio.append(
                AudioMetadata(
                    integer(row["index"], 0, 8),
                    row["codec"],
                    integer(row["sample_rate"], 8000, 96000),
                    integer(row["channels"], 1, 2),
                    integer(row["time_base_num"], 1, 10**9),
                    integer(row["time_base_den"], 1, 10**9),
                    None
                    if row["start_pts"] is None
                    else integer(row["start_pts"], -(2**53), 2**53),
                )
            )
        rows = value["frames"]
        if type(rows) is not list or len(rows) != len(targets):
            raise ValueError("frames")
        frames, previous_index, previous_pts = [], -1, None
        for target, row in zip(targets, rows, strict=True):
            if type(row) is not dict or set(row) != {
                "requested_ms",
                "frame_index",
                "pts",
                "relative_time_num",
                "relative_time_den",
                "width",
                "height",
                "png_base64",
                "png_sha256",
            }:
                raise ValueError("frame")
            if type(row["requested_ms"]) is not int or row["requested_ms"] != target:
                raise ValueError("target")
            index = integer(row["frame_index"], 0, count - 1)
            pts = integer(row["pts"], origin, 2**53)
            if (
                index < previous_index
                or previous_pts is not None
                and pts < previous_pts
            ):
                raise ValueError("order")
            if (index == 0) != (pts == origin):
                raise ValueError("origin")
            if (
                previous_pts is not None
                and index > previous_index
                and pts <= previous_pts
            ):
                raise ValueError("strict_pts")
            if (
                frames
                and index == previous_index
                and (
                    pts != previous_pts
                    or row["png_sha256"] != frames[-1].png_sha256
                    or row["width"] != frames[-1].width
                    or row["height"] != frames[-1].height
                )
            ):
                raise ValueError("same_frame")
            relative = Fraction((pts - origin) * num, den)
            if relative < Fraction(target, 1000) or relative > Fraction(str(duration)):
                raise ValueError("time")
            if (
                integer(row["relative_time_num"], 0, 2**63) != relative.numerator
                or integer(row["relative_time_den"], 1, 10**9) != relative.denominator
            ):
                raise ValueError("rational")
            if (
                type(row["png_base64"]) is not str
                or not 1 <= len(row["png_base64"]) <= (MAX_FRAME + 2) // 3 * 4
            ):
                raise ValueError("png")
            png = base64.b64decode(row["png_base64"], validate=True)
            if len(png) > MAX_FRAME or max(row["width"], row["height"]) > 1280:
                raise ValueError("png_bound")
            image = NormalizedImage(
                source_sha,
                png,
                row["png_sha256"],
                row["width"],
                row["height"],
                OCR_VERSION,
            )
            validate_image(image, source_sha)
            frames.append(
                VideoFrame(
                    target,
                    index,
                    pts,
                    relative.numerator,
                    relative.denominator,
                    image.width,
                    image.height,
                    png,
                    image.png_sha256,
                )
            )
            previous_index, previous_pts = index, pts
        metadata = VideoMetadata(
            width,
            height,
            meta["codec"],
            num,
            den,
            origin,
            float(duration),
            count,
            tuple(audio),
        )
        logger.info(
            "video_result_verified frames=%d audio_streams=%d", len(frames), len(audio)
        )
        return VideoSample(source_sha, metadata, tuple(frames))
    except Exception:
        raise VideoError("video_invalid_result") from None
