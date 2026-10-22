"""Create explicitly separate rational ASR inputs and compressed listening copies from verified native TTS audio in a credential-free namespace."""

import hashlib
import json
import logging
import math
import os
import re
import resource
import stat
import subprocess
import sys
from pathlib import Path

import numpy as np

from scripts.tts_waveform import asr_input, write_exclusive

logger = logging.getLogger(__name__)


def validate_request(request):
    """Accept only bounded fixed leaf names, original sample identities and declared native rates without arbitrary encoder options."""
    if (
        type(request) is not dict
        or set(request) != {"cases"}
        or type(request["cases"]) is not list
        or not 1 <= len(request["cases"]) <= 30
    ):
        raise ValueError("tts_diagnostic_request")
    identities = set()
    for case in request["cases"]:
        if type(case) is not dict or set(case) != {
            "id",
            "filename",
            "waveform_sha256",
            "sample_count",
            "sample_rate",
        }:
            raise ValueError("tts_diagnostic_case")
        if (
            type(case["id"]) is not str
            or re.fullmatch(r"[a-z0-9_-]{1,80}", case["id"]) is None
            or case["id"] in identities
            or case["filename"] != case["id"] + ".f32"
        ):
            raise ValueError("tts_diagnostic_identity")
        if (
            type(case["sample_rate"]) is not int
            or case["sample_rate"] not in {22050, 24000}
            or type(case["sample_count"]) is not int
            or not 1 <= case["sample_count"] <= case["sample_rate"] * 20
            or type(case["waveform_sha256"]) is not str
            or re.fullmatch(r"[a-f0-9]{64}", case["waveform_sha256"]) is None
        ):
            raise ValueError("tts_diagnostic_waveform")
        identities.add(case["id"])
    logger.info("tts_diagnostic_request_verified cases=%d", len(identities))


def load_native(case, root=Path("/samples")):
    """Read exact finite native source bits without following links, accepting special files or repairing original amplitude."""
    descriptor = os.open(
        Path(root) / case["filename"], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
    )
    with os.fdopen(descriptor, "rb") as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise ValueError("tts_diagnostic_source_type")
        raw = stream.read(24000 * 20 * 4 + 1)
    if (
        len(raw) != case["sample_count"] * 4
        or hashlib.sha256(raw).hexdigest() != case["waveform_sha256"]
    ):
        raise ValueError("tts_diagnostic_source_integrity")
    values = np.frombuffer(raw, dtype="<f4")
    if not np.isfinite(values).all() or np.max(np.abs(values)) > 16:
        raise ValueError("tts_diagnostic_source_signal")
    return values


def preview_pcm(values):
    """Produce a separately declared RMS-levelled listening input with peak headroom, preserving every source sample and its timeline."""
    rms = float(np.sqrt(np.mean(values.astype(np.float64) ** 2)))
    peak = float(np.max(np.abs(values)))
    if not math.isfinite(rms) or not math.isfinite(peak):
        raise ValueError("tts_preview_nonfinite")
    gain = min(0.10 / rms, 0.95 / peak) if rms > 0 and peak > 0 else 1.0
    preview = np.asarray(values * gain, dtype="<f4")
    logger.info("tts_separate_listening_gain_prepared samples=%d", len(values))
    return preview.tobytes(), dict(
        preview_gain=gain,
        target_RMS=0.10,
        maximum_peak=0.95,
        source_RMS=rms,
        source_peak=peak,
        native_original_modified=False,
    )


def encode_preview(raw, rate):
    """Encode the complete separate listening signal with a pinned bounded local FFmpeg command and no original-file write or lossy quality claim."""
    command = [
        "/usr/bin/ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-nostdin",
        "-threads",
        "1",
        "-f",
        "f32le",
        "-ar",
        str(rate),
        "-ac",
        "1",
        "-i",
        "pipe:0",
        "-map_metadata",
        "-1",
        "-c:a",
        "libopus",
        "-b:a",
        "24k",
        "-application",
        "voip",
        "-threads",
        "1",
        "-f",
        "ogg",
        "pipe:1",
    ]
    result = subprocess.run(
        command,
        input=raw,
        capture_output=True,
        timeout=30,
        check=False,
        env={"PATH": "/usr/bin", "LANG": "C.UTF-8"},
    )
    if (
        result.returncode != 0
        or not 1 <= len(result.stdout) <= 256 * 1024
        or not result.stdout.startswith(b"OggS")
        or len(result.stderr) > 65536
    ):
        raise ValueError("tts_preview_encoder")
    logger.info("tts_complete_listening_copy_encoded bytes=%d", len(result.stdout))
    return result.stdout


def transform(case, output=Path("/output"), samples=Path("/samples")):
    """Retain separate ASR and preview hashes/gain/count without treating either transformation as an original waveform or naturalness rating."""
    from scipy.signal import resample_poly

    values = load_native(case, samples)
    common, metadata = asr_input(values, case["sample_rate"], resample_poly)
    preview, gain = preview_pcm(values)
    encoded = encode_preview(preview, case["sample_rate"])
    name = case["id"]
    write_exclusive(Path(output) / (name + ".f32"), common.tobytes())
    write_exclusive(Path(output) / (name + ".ogg"), encoded)
    return dict(
        id=name,
        asr=metadata,
        preview=dict(
            gain,
            filename=name + ".ogg",
            bytes=len(encoded),
            sha256=hashlib.sha256(encoded).hexdigest(),
            mime_type="audio/ogg",
            codec="FFmpeg libopus 24k voip mono",
            full_native_timeline=True,
            lossy_inspection_copy=True,
            actual_listening_completed=False,
        ),
        naturalness_score=None,
    )


def main():
    """Transform only selected readonly native waveforms after TTS retirement; no model loading, host data, references or invented listening result."""
    logging.basicConfig(level=logging.INFO)
    raw = sys.stdin.buffer.read(65537)
    if len(raw) > 65536:
        raise ValueError("tts_diagnostic_request_bound")
    request = json.loads(raw)
    validate_request(request)
    os.sched_setaffinity(0, {0, 1})
    for case in request["cases"]:
        result = transform(case)
        print(
            json.dumps(dict(event="transformed", **result), allow_nan=False), flush=True
        )
    usage = resource.getrusage(resource.RUSAGE_SELF)
    print(
        json.dumps(
            dict(
                event="complete",
                peak_lifetime_process_RSS_KiB=usage.ru_maxrss,
                process_CPU_seconds=usage.ru_utime + usage.ru_stime,
            )
        ),
        flush=True,
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(
            json.dumps(
                dict(
                    event="error",
                    error_class=type(error).__name__,
                    detail=str(error)[:512],
                )
            ),
            flush=True,
        )
        raise SystemExit(1) from None
