"""Provide exact original PCM conversion and joined resource helpers without campaign operators."""

import asyncio
import io
import logging
import os
import stat
import wave
from pathlib import Path
import numpy as np
from src.application.services.web_fetch_tasks import finish_owned, spawn_owned

from src.application.services.voice_pipeline import digest as sha

LOGGER = logging.getLogger(__name__)
logger = LOGGER


def pcm_wave(raw, rate):
    """Quantize a separate PCM16 WAV without gain changes, trimming or modifying native float bytes."""
    samples = np.frombuffer(raw, dtype="<f4")
    if (
        rate not in {16000, 22050, 48000}
        or not 1 <= len(samples) <= rate * 20
        or (not np.isfinite(samples).all())
        or (np.abs(samples).max() > 1)
    ):
        raise ValueError("playback_conversion_bound")
    converted = (
        np.rint(np.where(samples < 0, samples * 32768, samples * 32767))
        .astype("<i2")
        .tobytes()
    )
    output = io.BytesIO()
    with wave.open(output, "wb") as writer:
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(rate)
        writer.writeframes(converted)
    return output.getvalue()


def read_native(directory, identity, result):
    """Independently verify exact private native float/WAV output and genuine generation completion."""
    from src.infrastructure.voice.waveform import native_bytes

    contents = []
    for suffix in ["f32", "wav"]:
        path = directory / (identity + "." + suffix)
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(descriptor, "rb") as stream:
            info = os.fstat(stream.fileno())
            if (
                not stat.S_ISREG(info.st_mode)
                or info.st_mode & 63
                or info.st_size > 16 * 1024**2
            ):
                raise ValueError("native_output_capability")
            contents.append(stream.read(16 * 1024**2 + 1))
    raw, wav = contents
    values = np.frombuffer(raw, dtype="<f4")
    expected_raw, expected_wav = native_bytes(values, result["sample_rate"])
    if (
        raw != expected_raw
        or wav != expected_wav
        or sha(raw) != result["native_sha256"]
        or (sha(wav) != result["wav_sha256"])
        or (len(values) != result["samples"])
        or (result["channels"] != 1)
        or (result["dtype"] != "float32")
    ):
        raise ValueError("native_output_integrity")
    if result["generation_complete"] is not True:
        raise ValueError("native_generation_did_not_end")
    return raw


def process_tree(pid):
    """Sample descendants through procfs without touching unrelated host processes."""
    found, pending = (set(), [pid])
    while pending:
        current = pending.pop()
        if current in found:
            continue
        found.add(current)
        try:
            for task in Path(f"/proc/{current}/task").iterdir():
                pending.extend(
                    (int(x) for x in (task / "children").read_text().split())
                )
        except (FileNotFoundError, ProcessLookupError):
            pass
    return found


def rss_bytes(pid):
    """Return sampled resident bytes for one process, treating an already retired child as zero."""
    try:
        return next(
            (
                int(line.split()[1]) * 1024
                for line in Path(f"/proc/{pid}/status").read_text().splitlines()
                if line.startswith("VmRSS:")
            )
        )
    except (FileNotFoundError, StopIteration, ProcessLookupError):
        return 0


def mem_available():
    """Read the current available host RAM without implying reservation or substituting free VRAM."""
    return next(
        (
            int(line.split()[1]) * 1024
            for line in Path("/proc/meminfo").read_text().splitlines()
            if line.startswith("MemAvailable:")
        )
    )


async def joined_io(function, *args, **kwargs):
    """Keep the real bounded native subprocess/thread owned until it exits, even after caller cancellation."""
    task = spawn_owned(asyncio.to_thread(function, *args, **kwargs))
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        try:
            await finish_owned(task)
        except BaseException:
            logger.info("voice_native_cancelled_worker_joined")
        raise
