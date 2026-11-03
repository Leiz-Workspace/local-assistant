"""Publish a self-contained local listening sheet from retained ADR-154 native audio without inference."""

import argparse
import base64
import html
import json
import logging
import os
from pathlib import Path

from benchmarks.scripts import vi_voice_preparation as assets
from benchmarks.scripts.vi_voice_campaign import read_native

LOGGER = logging.getLogger(__name__)


def render_review(items):
    """Render exactly24 complete native clips with escaped labels and no microphone, scripts or remote resources."""
    if len(items) != 24 or len({item["id"] for item in items}) != 24:
        raise ValueError("review_coverage")
    cards = []
    for item in items:
        audio = base64.b64encode(item["wav"]).decode("ascii")
        cards.append(f"""<article><h2>{html.escape(item["id"])}</h2>
<p>{html.escape(item["text"])}</p><p>Giọng: {html.escape(item["voice"])}; {item["sample_rate"]} Hz.
Mã SHA256 bản gốc: <code>{html.escape(item["sha256"])}</code></p>
<audio controls preload="none" src="data:audio/wav;base64,{audio}"></audio>
<p>Ghi nhận: phát âm / dấu / đọc số, ngày giờ; ngắt nhịp; rè, méo, đứt tiếng;
nhận cảm giọng nữ, miền Bắc; độ tự nhiên và mức chắc chắn.</p></article>""")
    return (
        """<!doctype html>
<!-- Purpose: Local review of unchanged benchmark audio; no recording, uploads or inference. -->
<html lang="vi"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; media-src data:; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
<title>D74 — Nghe so sánh 24 clip</title>
<style>body{max-width:900px;margin:32px auto;padding:0 20px;font:17px/1.6 system-ui;color:#18232b;background:#fafafa}
article{background:white;border:1px solid #cdd5da;border-radius:10px;padding:20px;margin:20px 0}h2{font-size:19px}
audio{width:100%}code{overflow-wrap:anywhere;font-size:12px}</style>
<h1>D74 — Nghe so sánh 24 clip</h1>
<p>Trang này chứa đủ âm thanh gốc, mở trực tiếp và bấm phát từng mục; không cần máy chủ.
Không thu microphone, không gửi dữ liệu ra ngoài. Piper là giọng đối chứng cũ.</p>
<p>Chưa có đánh giá nghe hoặc lựa chọn giọng mới. Thời gian tạo âm thanh không chứng minh thời gian chờ toàn bộ câu trả lời tối đa 4 giây.
Bạn có thể gửi nhận xét theo mã clip trong chat; không cần sửa JSON.</p>
"""
        + "\n".join(cards)
        + "\n</html>\n"
    )


def publish_review(root=assets.ROOT):
    """Verify original first-attempt audio and publish an exclusive embedded listening page and hash index."""
    root = Path(root)
    result = json.loads((root / "campaign-result.json").read_text())
    packet = json.loads(assets.PACKET.read_text())
    texts = {case["id"]: case["text"] for case in packet["tts_cases"]}
    items, index = [], []
    variants = {
        "piper-vi": ("piper-vi", "piper-vi"),
        "truc-ly": ("turbo", "Trúc Ly"),
        "ngoc-huyen": ("turbo", "Ngọc Huyền"),
    }
    expected = {label + "-" + identity for label in variants for identity in texts}
    if {row["id"] for row in result["standalone"]} != expected:
        raise ValueError("review_variant_coverage")
    for row in result["standalone"]:
        if row["status"] != "NATIVE_COMPLETE_AWAITING_LISTENING":
            raise ValueError("review_incomplete_audio")
        label = next(label for label in variants if row["id"].startswith(label + "-"))
        directory = root / "results" / ("standalone-" + label) / "native"
        read_native(directory, row["id"], row["result"])
        wav = (directory / (row["id"] + ".wav")).read_bytes()
        items.append(
            dict(
                id=row["id"],
                text=texts[row["case"]],
                voice=row["voice"],
                sample_rate=row["result"]["sample_rate"],
                sha256=row["result"]["wav_sha256"],
                wav=wav,
            )
        )
        index.append(
            dict(
                id=row["id"],
                case=row["case"],
                voice=row["voice"],
                native_wav_sha256=row["result"]["wav_sha256"],
                native_path=str((directory / (row["id"] + ".wav")).relative_to(root)),
            )
        )
    page = render_review(items).encode()
    directory = root / "review"
    directory.mkdir(mode=0o700)
    with (directory / "index.html").open("xb") as stream:
        stream.write(page)
    assets.publish(
        directory / "index.json",
        dict(
            description="24 unchanged native audio outputs embedded for local owner review; no labels or voice preference invented.",
            page_sha256=assets.digest(directory / "index.html"),
            audio=index,
            owner_ratings=None,
        ),
    )
    assets.budget(root)
    LOGGER.info(
        "local_listening_sheet_published clips=%d bytes=%d", len(items), len(page)
    )
    return directory / "index.html"


def main():
    """Build only the local review artifact from an already retained campaign, without model or provider calls."""
    argparse.ArgumentParser(description=__doc__).parse_args()
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    os.umask(0o077)
    publish_review()


if __name__ == "__main__":
    main()
