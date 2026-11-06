"""Decode fixed local video containers and normalize selected PTS-bound frames inside the credential-free native namespace."""

import base64
import hashlib
import io
import json
import logging
import math
import os
import resource
import sys
from fractions import Fraction

logger = logging.getLogger(__name__)


def native(command, limit):
    """Join one bounded child using accepted anonymous output ownership and suppress all decoder stderr."""
    from src.application.services.video_contract import VideoError
    from src.infrastructure.ocr_worker import child_output

    try:
        return child_output(command, timeout=8, limit=limit)
    except Exception as error:
        code = (
            "video_processing_timeout"
            if getattr(error, "code", "") == "ocr_processing_timeout"
            else "video_invalid_content"
        )
        raise VideoError(code) from None


def probe(entries, *, frames=False):
    """Read finite fixed metadata fields without tags, filenames, network protocols or arbitrary demuxers."""
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
        "matroska,webm,mov,mp4,m4a,3gp,3g2,mj2",
    ]
    if frames:
        command += ["-select_streams", "v:0", "-show_frames", "-read_intervals", "%+31"]
    else:
        command += ["-show_streams", "-show_format"]
    command += ["-show_entries", entries, "-of", "json", "/payload"]
    return strict_json(native(command, 256 * 1024), 256 * 1024)


def process(targets):
    """Choose first decoded PTS at or after each relative target and emit source-bound metadata-free RGB frame pixels."""
    from PIL import Image

    from src.application.services.video_contract import (
        AUDIO_CODECS,
        MAX_FRAME,
        VIDEO_CODECS,
        VideoError,
        resolve_video,
        schedule,
    )

    schedule(targets)
    metadata = probe(
        "stream=index,codec_type,codec_name,width,height,time_base,start_pts,sample_rate,channels:stream_disposition=attached_pic:format=duration,format_name"
    )
    streams = metadata["streams"]
    video = [s for s in streams if s["codec_type"] == "video"]
    audio = [s for s in streams if s["codec_type"] == "audio"]
    if len(video) != 1 or len(audio) > 1 or len(streams) != len(video) + len(audio):
        raise VideoError("video_invalid_content")
    stream = video[0]
    duration = float(metadata["format"]["duration"])
    width, height = stream["width"], stream["height"]
    if (
        stream["codec_name"] not in VIDEO_CODECS
        or stream["disposition"]["attached_pic"]
        or not math.isfinite(duration)
        or not 0 < duration <= 30
        or not 1 <= width <= 1920
        or not 1 <= height <= 1920
        or width * height > 2073600
    ):
        raise VideoError("video_limits_exceeded")
    audio_rows = []
    for row in audio:
        if (
            row["codec_name"] not in AUDIO_CODECS
            or not 8000 <= int(row["sample_rate"]) <= 96000
            or not 1 <= row["channels"] <= 2
        ):
            raise VideoError("video_invalid_content")
        audio_base = Fraction(row["time_base"])
        audio_rows.append(
            dict(
                index=row["index"],
                codec=row["codec_name"],
                sample_rate=int(row["sample_rate"]),
                channels=row["channels"],
                time_base_num=audio_base.numerator,
                time_base_den=audio_base.denominator,
                start_pts=row.get("start_pts"),
            )
        )
    timebase = Fraction(stream["time_base"])
    if not 0 < timebase.numerator <= 10**9 or not 0 < timebase.denominator <= 10**9:
        raise VideoError("video_invalid_content")
    frames = probe("frame=best_effort_timestamp", frames=True)["frames"]
    if not 1 <= len(frames) <= 900:
        raise VideoError("video_limits_exceeded")
    points = [int(f["best_effort_timestamp"]) for f in frames]
    if any(b <= a for a, b in zip(points, points[1:])):
        raise VideoError("video_invalid_content")
    origin = points[0]
    if any((p - origin) * timebase > Fraction(str(duration)) for p in points):
        raise VideoError("video_invalid_content")
    source_sha = hashlib.sha256()
    with open("/payload", "rb") as source:
        while chunk := source.read(256 * 1024):
            source_sha.update(chunk)
    result = dict(
        source_sha256=source_sha.hexdigest(),
        processor="ffmpeg-frames-v1",
        metadata=dict(
            width=width,
            height=height,
            codec=stream["codec_name"],
            time_base_num=timebase.numerator,
            time_base_den=timebase.denominator,
            origin_pts=origin,
            duration_seconds=duration,
            frame_count=len(points),
            audio=audio_rows,
        ),
        frames=[],
    )
    for target in targets:
        selected = next(
            (
                index
                for index, pts in enumerate(points)
                if (pts - origin) * timebase >= Fraction(target, 1000)
            ),
            None,
        )
        if selected is None:
            raise VideoError("video_time_unavailable")
        rendered = native(
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
                "matroska,webm,mov,mp4,m4a,3gp,3g2,mj2",
                "-noautorotate",
                "-i",
                "/payload",
                "-map",
                "0:v:0",
                "-an",
                "-sn",
                "-dn",
                "-vf",
                f"select=eq(n\\,{selected})",
                "-frames:v",
                "1",
                "-fps_mode",
                "passthrough",
                "-threads",
                "1",
                "-f",
                "image2pipe",
                "-vcodec",
                "png",
                "pipe:1",
            ],
            8 * 1024**2,
        )
        with Image.open(io.BytesIO(rendered)) as image:
            normalized = image.convert("RGB")
            normalized.thumbnail((1280, 1280))
            normalized.info.clear()
            output = io.BytesIO()
            normalized.save(output, "PNG")
            png = output.getvalue()
        if len(png) > MAX_FRAME:
            raise VideoError("video_limits_exceeded")
        relative = (points[selected] - origin) * timebase
        result["frames"].append(
            dict(
                requested_ms=target,
                frame_index=selected,
                pts=points[selected],
                relative_time_num=relative.numerator,
                relative_time_den=relative.denominator,
                width=normalized.width,
                height=normalized.height,
                png_base64=base64.b64encode(png).decode("ascii"),
                png_sha256=hashlib.sha256(png).hexdigest(),
            )
        )
    resolve_video(result, source_sha.hexdigest(), targets)
    return result


def main():
    """Set native resource limits before decoder imports and emit only a complete bounded result or finite error."""
    resource.setrlimit(resource.RLIMIT_AS, (512 * 1024**2, 512 * 1024**2))
    resource.setrlimit(resource.RLIMIT_CPU, (8, 9))
    resource.setrlimit(resource.RLIMIT_FSIZE, (8 * 1024**2, 8 * 1024**2))
    resource.setrlimit(resource.RLIMIT_NOFILE, (32, 32))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    os.umask(0o077)
    from src.application.services.video_contract import MAX_SOURCE, VideoError

    try:
        if not 1 <= os.stat("/payload").st_size <= MAX_SOURCE:
            raise VideoError("video_limits_exceeded")
        targets = json.loads(sys.argv[1])
        result = process(tuple(targets))
    except VideoError as error:
        result = {"error": error.code}
    except MemoryError:
        result = {"error": "video_limits_exceeded"}
    except Exception:
        result = {"error": "video_invalid_content"}
    logger.info("video_worker_finished accepted=%s", "frames" in result)
    with os.fdopen(os.dup(1), "r+b") as output:
        output.seek(0)
        output.truncate()
        output.write(json.dumps(result, separators=(",", ":")).encode())
        output.flush()


if __name__ == "__main__":
    main()
