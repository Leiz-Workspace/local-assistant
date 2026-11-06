"""Decode continuous bounded FLAC/PCM source clocks and normalize mono16k PCM inside the readonly credential-free native namespace."""

import base64
import hashlib
import json
import logging
import os
import resource
from fractions import Fraction

logger = logging.getLogger(__name__)
FORMATS = "flac,wav,matroska,webm"


def native(command, limit):
    """Run and join one fixed bounded child using accepted anonymous stdout ownership and sanitized failure codes."""
    from src.application.services.audio_contract import AudioError
    from src.infrastructure.ocr_worker import child_output

    try:
        return child_output(command, timeout=8, limit=limit)
    except Exception as error:
        raise AudioError(
            "audio_processing_timeout"
            if getattr(error, "code", "") == "ocr_processing_timeout"
            else "audio_invalid_content"
        ) from None


def probe(entries, *, frames=False):
    """Read only fixed bounded stream/frame fields without exposing tags, filenames or remote protocols."""
    from src.application.services.vision_chat_policy import strict_json

    command = [
        "/usr/bin/ffprobe",
        "-v",
        "error",
        "-threads",
        "1",
        "-protocol_whitelist",
        "file",
        "-format_whitelist",
        FORMATS,
    ]
    command += (
        ["-select_streams", "a:0", "-show_frames", "-read_intervals", "%+31"]
        if frames
        else ["-show_streams"]
    )
    command += ["-show_entries", entries, "-of", "json", "/payload"]
    return strict_json(native(command, 256 * 1024), 256 * 1024)


def process():
    """Require a continuous decoded audio sample clock before fixed PCM normalization and exact source/sample hashing."""
    from src.application.services.audio_contract import (
        MAX_SAMPLES,
        AudioError,
        resolve_audio,
    )

    data = probe("stream=index,codec_type,codec_name,time_base,sample_rate,channels")
    streams = data["streams"]
    audio = [row for row in streams if row["codec_type"] == "audio"]
    video = [row for row in streams if row["codec_type"] == "video"]
    if len(audio) != 1 or len(video) > 1 or len(audio) + len(video) != len(streams):
        raise AudioError("audio_invalid_content")
    row = audio[0]
    rate = int(row["sample_rate"])
    channels = row["channels"]
    timebase = Fraction(row["time_base"])
    if (
        row["codec_name"] not in {"flac", "pcm_s16le"}
        or not 8000 <= rate <= 48000
        or not 1 <= channels <= 2
        or not 0 < timebase.numerator <= 10**9
        or not 0 < timebase.denominator <= 10**9
    ):
        raise AudioError("audio_invalid_content")
    frames = probe("frame=best_effort_timestamp,nb_samples", frames=True)["frames"]
    if not 1 <= len(frames) <= 2000:
        raise AudioError("audio_limits_exceeded")
    total, origin = 0, None
    for frame in frames:
        if (
            type(frame.get("best_effort_timestamp")) is not int
            or type(frame.get("nb_samples")) is not int
        ):
            raise AudioError("audio_clock_unavailable")
        pts, n = frame["best_effort_timestamp"], frame["nb_samples"]
        if origin is None:
            origin = pts
        if not 1 <= n <= 65536 or (pts - origin) * timebase != Fraction(total, rate):
            raise AudioError("audio_clock_unavailable")
        total += n
        if total > 30 * rate:
            raise AudioError("audio_limits_exceeded")
    pcm = native(
        [
            "/usr/bin/ffmpeg",
            "-nostdin",
            "-v",
            "error",
            "-threads",
            "1",
            "-filter_threads",
            "1",
            "-protocol_whitelist",
            "file",
            "-format_whitelist",
            FORMATS,
            "-i",
            "/payload",
            "-map",
            "0:a:0",
            "-vn",
            "-sn",
            "-dn",
            "-map_metadata",
            "-1",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-threads",
            "1",
            "-c:a",
            "pcm_s16le",
            "-f",
            "s16le",
            "pipe:1",
        ],
        2 * MAX_SAMPLES,
    )
    if not pcm or len(pcm) % 2:
        raise AudioError("audio_invalid_content")
    source_sha = hashlib.sha256()
    with open("/payload", "rb") as source:
        while chunk := source.read(256 * 1024):
            source_sha.update(chunk)
    result = dict(
        source_sha256=source_sha.hexdigest(),
        pcm_sha256=hashlib.sha256(pcm).hexdigest(),
        pcm_base64=base64.b64encode(pcm).decode(),
        sample_count=len(pcm) // 2,
        source_codec=row["codec_name"],
        source_sample_rate=rate,
        source_channels=channels,
        source_sample_count=total,
        time_base_num=timebase.numerator,
        time_base_den=timebase.denominator,
        first_pts=origin,
        sample_rate=16000,
        channels=1,
        processor="native-pcm-v1",
    )
    resolve_audio(result, source_sha.hexdigest())
    return result


def main():
    """Apply native kernel limits before decoding and emit one complete bounded response or finite error."""
    resource.setrlimit(resource.RLIMIT_AS, (512 * 1024**2, 512 * 1024**2))
    resource.setrlimit(resource.RLIMIT_CPU, (8, 9))
    resource.setrlimit(resource.RLIMIT_FSIZE, (8 * 1024**2, 8 * 1024**2))
    resource.setrlimit(resource.RLIMIT_NOFILE, (32, 32))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    os.umask(0o077)
    from src.application.services.audio_contract import MAX_SOURCE, AudioError

    try:
        if not 1 <= os.stat("/payload").st_size <= MAX_SOURCE:
            raise AudioError("audio_limits_exceeded")
        result = process()
    except AudioError as error:
        result = {"error": error.code}
    except MemoryError:
        result = {"error": "audio_limits_exceeded"}
    except Exception:
        result = {"error": "audio_invalid_content"}
    logger.info("audio_worker_finished accepted=%s", "pcm_base64" in result)
    with os.fdopen(os.dup(1), "r+b") as output:
        output.seek(0)
        output.truncate()
        output.write(json.dumps(result, separators=(",", ":")).encode())
        output.flush()


if __name__ == "__main__":
    main()
