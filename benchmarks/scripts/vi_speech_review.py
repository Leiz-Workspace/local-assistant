"""Render a self-contained local paired listening page from new speech-quality native outputs only."""

import base64
import html
import json
import logging
from pathlib import Path

from benchmarks.scripts import vi_voice_preparation as assets
from benchmarks.scripts.vi_voice_campaign import read_native

LOGGER = logging.getLogger(__name__)
LABELS = {
    "raw": "Bản đối chứng",
    "reading": "Sửa cách đọc",
    "clauses": "Cách đọc + ngắt câu và giữ dấu hỏi",
}


def render_page(rows, audio):
    """Show all48 declared slots, preserving missing/failed outcomes and every provided native audio byte."""
    if (
        len(rows) != 48
        or len({row["id"] for row in rows}) != 48
        or set(audio) - {row["id"] for row in rows}
    ):
        raise ValueError("paired_review_coverage")
    cards = []
    for case in sorted({row["case"] for row in rows}):
        for voice in ("Trúc Ly", "Ngọc Huyền"):
            selected = [
                row for row in rows if row["case"] == case and row["voice"] == voice
            ]
            if {row["profile"] for row in selected} != set(LABELS) or len(
                selected
            ) != 3:
                raise ValueError("paired_review_variant_coverage")
            cells = []
            for profile, label in LABELS.items():
                row = next(row for row in selected if row["profile"] == profile)
                if row["id"] in audio:
                    encoded = base64.b64encode(audio[row["id"]]).decode("ascii")
                    player = f'<audio controls preload="none" src="data:audio/wav;base64,{encoded}"></audio>'
                else:
                    player = (
                        "<p>Chưa có clip hoàn chỉnh: "
                        + html.escape(row["status"])
                        + "</p>"
                    )
                cells.append(
                    "<section><h3>"
                    + label
                    + "</h3><p>Mã: "
                    + html.escape(row["id"])
                    + "</p>"
                    + player
                    + "<details><summary>Văn bản dùng để đọc</summary><p>"
                    + html.escape(row["render"]["speech_text"])
                    + "</p></details></section>"
                )
            cards.append(
                "<article><h2>"
                + html.escape(case + " — " + voice)
                + "</h2><p>"
                + html.escape(selected[0]["render"]["source_text"])
                + '</p><div class="variants">'
                + "".join(cells)
                + "</div></article>"
            )
    return (
        """<!doctype html>
<!-- Purpose: Compare unchanged new native audio for owner listening without recording or network access. -->
<html lang="vi"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; media-src data:; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
<title>D74 — So sánh cách đọc và ngữ điệu</title>
<style>body{max-width:1250px;margin:30px auto;padding:0 20px;background:#f8fafb;color:#18232b;font:16px/1.6 system-ui}
article{background:white;border:1px solid #ccd6dd;border-radius:10px;padding:20px;margin:22px 0}.variants{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:20px}
h2{font-size:21px}h3{font-size:17px}section{min-width:0;overflow-wrap:anywhere}audio{width:100%}details{font-size:14px}@media(max-width:850px){.variants{grid-template-columns:1fr}}</style>
<h1>D74 — Cách đọc và ngữ điệu</h1>
<p>Mỗi câu có ba bản của cùng một giọng. Bấm phát để so sánh phát âm, giờ/ngày, Python/API,
ngắt nhịp và câu hỏi. Đây là clip mới; 24 clip trước giữ nguyên.</p>
<p>Bản sửa Python/API dùng cách ghi âm tiết tiếng Việt để thử, chưa được chốt là phát âm chuẩn.
Một số bản đối chứng và bản sửa có thể giống hệt vì thư viện đã chuyển giờ/ngày thành chữ đúng từ đầu.</p>
<p>Chưa có đánh giá nghe hoặc lựa chọn giọng cho bộ mới. Bạn có thể gửi mã câu/giọng và bản bạn thích,
kèm lỗi còn nghe thấy trong chat. Không cần điền JSON. Trang này không thu microphone hoặc gửi dữ liệu ra ngoài.</p>
"""
        + "".join(cards)
        + "\n</html>\n"
    )


def publish_review(root):
    """Verify every completed native output before embedding it, while retaining all failed/unattempted slots."""
    root = Path(root)
    result = json.loads((root / "campaign-result.json").read_text())
    audio, index = {}, []
    for row in result["rows"]:
        if row["status"] != "NATIVE_COMPLETE_AWAITING_OWNER_REVIEW":
            continue
        directory = root / ("profile-" + row["profile"]) / "native"
        read_native(directory, row["id"], row["native"])
        path = directory / (row["id"] + ".wav")
        audio[row["id"]] = path.read_bytes()
        index.append(
            dict(
                id=row["id"],
                wav_sha256=assets.digest(path),
                path=str(path.relative_to(root)),
            )
        )
    directory = root / "review"
    directory.mkdir(mode=0o700)
    with (directory / "index.html").open("xb") as stream:
        stream.write(render_page(result["rows"], audio).encode())
    assets.publish(
        directory / "index.json",
        dict(
            description="Unchanged new native outputs in a local paired listening sheet; incomplete slots remain visible.",
            page_sha256=assets.digest(directory / "index.html"),
            native_audio=index,
            owner_ratings=None,
        ),
    )
    assets.budget(assets.ROOT)
    LOGGER.info(
        "paired_listening_page_published audio=%d declared_slots=48", len(audio)
    )
    return directory / "index.html"
