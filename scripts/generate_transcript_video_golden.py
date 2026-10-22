"""Mux pinned public speech normalized in isolation with explicitly authored unrelated visual stages for D66 timeline testing."""

import json
import logging
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from src.application.services.vision_chat_policy import digest
from src.infrastructure.audio_normalizer import NativeAudioNormalizer

logger = logging.getLogger(__name__)
REFERENCE = "And so my fellow Americans, ask not what your country can do for you, ask what you can do for your country."


def generate(destination):
    """Create an explicitly authored composite while retaining original speech/PCM hashes and an unverified supplied reference."""
    original = Path("tests/fixtures/audio/jfk.flac").read_bytes()
    audio = NativeAudioNormalizer().normalize(original)
    assert (
        audio.sample_count == 176000
        and audio.sample_rate == 16000
        and audio.first_pts == 0
    )
    font = ImageFont.truetype(
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 48
    )
    frames = []
    for index in range(11):
        title, color = (
            ("READY", "#19643c")
            if index < 4
            else ("MOVING", "#245b91")
            if index < 8
            else ("DONE", "#643c91")
        )
        image = Image.new("RGB", (960, 360), color)
        ImageDraw.Draw(image).text((100, 135), title, font=font, fill="white")
        frames.append(image.tobytes())
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryFile() as pcm:
        pcm.write(audio.pcm_s16le)
        pcm.flush()
        pcm.seek(0)
        subprocess.run(
            [
                "/usr/bin/ffmpeg",
                "-nostdin",
                "-v",
                "error",
                "-threads",
                "1",
                "-filter_threads",
                "1",
                "-f",
                "rawvideo",
                "-pixel_format",
                "rgb24",
                "-video_size",
                "960x360",
                "-framerate",
                "1",
                "-i",
                "pipe:0",
                "-f",
                "s16le",
                "-ar",
                "16000",
                "-ac",
                "1",
                "-i",
                f"/proc/self/fd/{pcm.fileno()}",
                "-map",
                "0:v:0",
                "-map",
                "1:a:0",
                "-c:v",
                "ffv1",
                "-level",
                "3",
                "-pix_fmt",
                "bgr0",
                "-threads",
                "1",
                "-c:a",
                "pcm_s16le",
                "-fflags",
                "+bitexact",
                "-flags:v",
                "+bitexact",
                "-flags:a",
                "+bitexact",
                "-map_metadata",
                "-1",
                "-t",
                "11",
                "-y",
                str(destination),
            ],
            input=b"".join(frames),
            pass_fds=(pcm.fileno(),),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True,
            timeout=15,
            env={"PATH": "/usr/bin:/bin"},
        )
    composite = NativeAudioNormalizer().normalize(destination.read_bytes())
    assert (
        composite.pcm_sha256 == audio.pcm_sha256
        and composite.sample_count == audio.sample_count
    )
    manifest = dict(
        description="D66 authored composite: pinned official public speech plus unrelated synthetic visual stages. Supplied same-agent reference, not ASR output/independent human certification/original historic video.",
        fixture=str(destination),
        source_sha256=digest(destination.read_bytes()),
        original_speech_fixture="tests/fixtures/audio/jfk.flac",
        original_speech_sha256=digest(original),
        pcm_sha256=composite.pcm_sha256,
        sample_count=composite.sample_count,
        sample_rate=16000,
        targets_ms=[0, 4000, 8000],
        expected_pts=[0, 4000, 8000],
        expected_stages=["READY", "MOVING", "DONE"],
        provided_transcript=dict(
            origin="provided_reference",
            language="en",
            segments=[dict(start_sample=0, end_sample=176000, text=REFERENCE)],
        ),
        source_ASR_model=None,
        source_ASR_evaluated=False,
        word_alignment_verified=False,
    )
    destination.with_suffix(".json").write_text(json.dumps(manifest, indent=2) + "\n")
    logger.info(
        "authored_speech_video_composite_generated samples=%d frames=11 ASR_attempts=0",
        audio.sample_count,
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    generate("tests/fixtures/video/d66-composite.mkv")
