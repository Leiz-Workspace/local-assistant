"""Create a public authored three-stage audio-bearing video fixture using existing Pillow, fonts and FFmpeg only."""

import io
import logging
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)


def generate(destination):
    """Encode three fixed RGB title frames and a synthetic tone without recording a camera, microphone or user document."""
    font = ImageFont.truetype(
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 48
    )
    frames = []
    for title, color in [
        ("READY", "#19643c"),
        ("MOVING", "#245b91"),
        ("DONE", "#643c91"),
    ]:
        picture = Image.new("RGB", (960, 360), color)
        ImageDraw.Draw(picture).text((100, 135), title, font=font, fill="white")
        output = io.BytesIO()
        picture.save(output, "PNG")
        frames.append(output.getvalue())
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
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
            "image2pipe",
            "-framerate",
            "1",
            "-vcodec",
            "png",
            "-i",
            "pipe:0",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:sample_rate=16000:duration=3",
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
            "3",
            "-y",
            str(destination),
        ],
        input=b"".join(frames),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=15,
        check=True,
        env={"PATH": "/usr/bin:/bin"},
        close_fds=True,
    )
    logger.info("authored_video_golden_generated frames=3 audio_is_synthetic_tone=true")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    generate("tests/fixtures/video/stages.mkv")
