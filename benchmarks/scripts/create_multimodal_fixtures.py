
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import subprocess

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "benchmarks/fixtures/multimodal"
OUT.mkdir(parents=True, exist_ok=True)

def font(size):
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
    ]
    for path in candidates:
        if Path(path).is_file():
            return ImageFont.truetype(path, size)
    raise RuntimeError("No suitable font installed")

big = font(70)
medium = font(40)

# V01: OCR
img = Image.new("RGB", (900, 450), "white")
draw = ImageDraw.Draw(img)
draw.text((55, 55), "SHLDD TEST", font=big, fill="black")
draw.text((55, 180), "CODE: RX-7392", font=medium, fill="black")
draw.text((55, 270), "VALUE: 482", font=medium, fill="black")
img.save(OUT / "ocr.png")

# V02: Colors and position
img = Image.new("RGB", (900, 450), "white")
draw = ImageDraw.Draw(img)
draw.ellipse((60, 90, 290, 320), fill="red")
draw.rectangle((580, 90, 810, 320), fill="blue")
img.save(OUT / "shapes.png")

# V03: Two separate images
for filename, color, word in [
    ("image_a.png", "red", "ALPHA"),
    ("image_b.png", "blue", "BRAVO"),
]:
    img = Image.new("RGB", (640, 360), color)
    draw = ImageDraw.Draw(img)
    draw.text((160, 145), word, font=big, fill="white")
    img.save(OUT / filename)

# VID01–03: Three scenes, two seconds each
for i, (color, word) in enumerate(
    [
        ("red", "RED"),
        ("green", "GREEN"),
        ("blue", "BLUE"),
    ],
    start=1,
):
    img = Image.new("RGB", (640, 360), color)
    draw = ImageDraw.Draw(img)
    draw.text((160, 145), word, font=big, fill="white")
    img.save(OUT / f"scene_{i}.png")

# Produce an actual six-second MP4.
# Each scene is exactly 2 seconds at 2 FPS.
segments = []
for i in range(1, 4):
    segment = OUT / f"segment_{i}.mp4"
    subprocess.run([
        "ffmpeg", "-hide_banner", "-loglevel", "error",
        "-y", "-loop", "1", "-framerate", "2",
        "-i", str(OUT / f"scene_{i}.png"),
        "-t", "2",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        str(segment),
    ], check=True)
    segments.append(segment)

concat = OUT / "concat.txt"
concat.write_text(
    "".join(f"file '{p.name}'\n" for p in segments),
    encoding="utf-8",
)

subprocess.run([
    "ffmpeg", "-hide_banner", "-loglevel", "error",
    "-y", "-f", "concat", "-safe", "0",
    "-i", str(concat),
    "-c", "copy",
    str(OUT / "sequence.mp4"),
], check=True, cwd=OUT)

print("Fixtures created:", OUT)
print("Video:", OUT / "sequence.mp4")

