"""Generate deterministic public authored D63 visual goldens with installed fonts and no external image input."""

import logging
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)
FONT = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
BOLD = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")


def generate(destination):
    """Write one chart, Vietnamese table and document dashboard with fixed literal layout and no private inputs."""
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    font = ImageFont.truetype(str(FONT), 27)
    title = ImageFont.truetype(str(BOLD), 32)
    image = Image.new("RGB", (960, 640), "white")
    draw = ImageDraw.Draw(image)
    draw.text((45, 25), "Monthly completed requests", font=title, fill="black")
    draw.line((100, 520, 870, 520), fill="black", width=3)
    draw.line((100, 120, 100, 520), fill="black", width=3)
    for label, value, x in [
        ("January", 10, 210),
        ("February", 30, 440),
        ("March", 20, 670),
    ]:
        top = 520 - value * 11
        draw.rectangle((x, top, x + 110, 519), fill="#2864a0")
        draw.text((x + 30, top - 40), str(value), font=title, fill="black")
        draw.text((x - 10, 545), label, font=font, fill="black")
    image.save(destination / "chart.png")
    image = Image.new("RGB", (1000, 440), "white")
    draw = ImageDraw.Draw(image)
    draw.text((35, 25), "Danh sách văn phòng phẩm", font=title, fill="black")
    rows = [
        ("Tên hàng", "Số lượng", "Đơn giá (VND)"),
        ("Bút", "3", "12000"),
        ("Vở", "5", "18000"),
    ]
    xs = [35, 340, 600, 965]
    for index, row in enumerate(rows):
        y = 110 + index * 95
        draw.line((35, y, 965, y), fill="black", width=2)
        for col, text in enumerate(row):
            draw.text((xs[col] + 15, y + 25), text, font=font, fill="black")
    draw.line((35, 395, 965, 395), fill="black", width=2)
    for x in xs:
        draw.line((x, 110, x, 395), fill="black", width=2)
    image.save(destination / "table.png")
    image = Image.new("RGB", (1000, 620), "#f1f4f8")
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, 1000, 92), fill="#18324b")
    draw.text((35, 25), "Atlas document dashboard", font=title, fill="white")
    draw.rectangle((45, 135, 955, 550), fill="white", outline="#a0a0a0", width=2)
    for y, text in [
        (170, "Project: Atlas"),
        (260, "Release: 2.4"),
        (350, "Files: 12"),
        (440, "Status: Ready"),
    ]:
        draw.text((85, y), text, font=title, fill="black")
    image.save(destination / "document.png")
    logger.info("authored_vision_goldens_generated images=3")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    generate(Path("tests/fixtures/vision/d63"))
