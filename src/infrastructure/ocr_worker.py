"""Verify and rasterize one source page, then produce bounded native or English OCR data in isolation."""

import base64
import csv
import io
import json
import logging
import os
import resource
import subprocess
import sys

from src.infrastructure.native_input import rewind_native_input

logger = logging.getLogger(__name__)
# Native children inherit the worker's 512 MiB RLIMIT_AS. Multi-threaded FFmpeg (one
# thread per demuxer/decoder/filter/encoder/muxer) otherwise gives each thread its own
# glibc malloc arena: a 64 MiB reservation, transiently 128 MiB while it is aligned.
# Those reservations fill the address-space cap, and a thread-stack mmap that lands
# during one fails, so pthread_create returns EAGAIN and FFmpeg exits 245 at random.
# A single arena keeps the footprint deterministic without raising the cap.
CHILD_ENV = {
    "PATH": "/usr/bin:/bin",
    "LANG": "C.UTF-8",
    "OMP_THREAD_LIMIT": "1",
    "MALLOC_ARENA_MAX": "1",
}


def child_output(command, *, source=None, data=None, timeout=8, limit=4 * 1024 * 1024):
    """Reuse bounded anonymous stdout for a reaped renderer/OCR child inside the same PID namespace."""
    from src.application.services.file_storage_policy import StoragePolicyError

    with os.fdopen(os.dup(1), "r+b") as output:
        output.seek(0)
        output.truncate()
        try:
            if source is not None:
                rewind_native_input(source)
            result = subprocess.run(
                command,
                stdin=source,
                input=data,
                stdout=output,
                stderr=subprocess.DEVNULL,
                timeout=timeout,
                check=False,
                env=dict(CHILD_ENV),
            )
        except subprocess.TimeoutExpired:
            raise StoragePolicyError("ocr_processing_timeout", 413) from None
        except OSError:
            raise StoragePolicyError("ocr_processing_unavailable", 503) from None
        finally:
            if source is not None:
                rewind_native_input(source)
        if result.returncode:
            raise StoragePolicyError("ocr_processing_unavailable", 503)
        output.seek(0)
        payload = output.read(limit + 1)
        output.seek(0)
        output.truncate()
        if len(payload) > limit:
            raise StoragePolicyError("ocr_limits_exceeded", 413)
        return payload


def recognize(png, page):
    """Convert Tesseract TSV into ordered lines and bounded normalized-pixel word boxes."""
    from src.application.services.file_storage_policy import StoragePolicyError
    from src.application.services.ocr_contract import MAX_TEXT_BYTES

    engine = (
        child_output(["/usr/bin/tesseract", "--version"], limit=4096)
        .decode("utf-8")
        .splitlines()[0]
    )
    data = child_output(
        ["/usr/bin/tesseract", "stdin", "stdout", "-l", "eng", "--psm", "6", "tsv"],
        data=png,
        timeout=10,
    )
    words, lines = [], {}
    weighted = weight = text_bytes = 0
    for row in csv.DictReader(
        io.StringIO(data.decode("utf-8")), delimiter="\t", quoting=csv.QUOTE_NONE
    ):
        if row["level"] != "5" or not row["text"].strip():
            continue
        text = row["text"].strip()
        score = float(row["conf"])
        if score < 0:
            continue
        word = dict(
            text=text,
            score=score,
            left=int(row["left"]),
            top=int(row["top"]),
            width=int(row["width"]),
            height=int(row["height"]),
            block=int(row["block_num"]),
            paragraph=int(row["par_num"]),
            line=int(row["line_num"]),
        )
        words.append(word)
        key = (word["block"], word["paragraph"], word["line"])
        lines.setdefault(key, []).append(text)
        weighted += len(text) * score
        weight += len(text)
        text_bytes += len(text.encode("utf-8"))
        if len(words) > 5000 or text_bytes > MAX_TEXT_BYTES // 2:
            raise StoragePolicyError("ocr_limits_exceeded", 413)
    text = "\n".join(" ".join(parts) for parts in lines.values())
    if len(text.encode("utf-8")) + text_bytes > MAX_TEXT_BYTES:
        raise StoragePolicyError("ocr_limits_exceeded", 413)
    confidence = round(weighted / weight, 3) if weight else None
    page.update(
        method="tesseract",
        engine=engine + ":eng",
        text=text,
        words=words,
        confidence_score=confidence,
        confidence_basis="character_weighted_engine_score_not_probability",
        review_required=not text or confidence is None or confidence < 85,
        uncertainties=[
            "ocr_score_not_calibrated",
            "english_only",
            "reading_order_and_table_grid_not_inferred",
        ],
    )
    if not text:
        page["uncertainties"].append("no_text_detected_not_proof_of_blank")
    return page


def process(source, suffix, number, mode):
    """Prefer native text or normalize one image/PDF page before OCR or explicit VLM preparation."""
    from PIL import Image, ImageOps
    from pypdf import PdfReader

    from src.application.services.file_storage_policy import (
        DEFAULT_POLICY,
        StoragePolicyError,
    )
    from src.application.services.ocr_contract import (
        MAX_IMAGE_BYTES,
        MAX_TEXT_BYTES,
        empty_page,
    )
    from src.infrastructure.file_content_verifier import detect_content

    detect_content(source, suffix, DEFAULT_POLICY)
    source.seek(0)
    count = 1
    if suffix == "pdf":
        reader = PdfReader(source, strict=True)
        count = len(reader.pages)
    if not 1 <= number <= count:
        raise StoragePolicyError("ocr_page_not_found", 422)
    page = empty_page(number, count)
    if suffix == "pdf" and mode == "auto":
        text = reader.pages[number - 1].extract_text(extraction_mode="plain") or ""
        if len(text.encode("utf-8")) > MAX_TEXT_BYTES:
            raise StoragePolicyError("ocr_limits_exceeded", 413)
        if text.strip():
            page["text"] = text
            return page
    source.seek(0)
    if suffix == "pdf":
        rendered = child_output(
            [
                "/usr/bin/pdftoppm",
                "-f",
                str(number),
                "-l",
                str(number),
                "-singlefile",
                "-r",
                "150",
                "-scale-to",
                "2000",
                "-png",
                "-",
            ],
            source=source,
        )
        image_source = io.BytesIO(rendered)
    else:
        image_source = source
    with Image.open(image_source) as image:
        normalized = ImageOps.exif_transpose(image).convert("RGB")
        normalized.thumbnail((2000, 2000))
        normalized.info.clear()
        width, height = normalized.size
        output = io.BytesIO()
        normalized.save(output, "PNG")
        png = output.getvalue()
    if len(png) > MAX_IMAGE_BYTES or width * height > 4_000_000:
        raise StoragePolicyError("ocr_limits_exceeded", 413)
    page.update(width=width, height=height, coordinate_space="rendered_pixels")
    if mode == "vlm":
        page.update(
            method="vlm_pending",
            engine="local-core-pending",
            confidence_basis="no_calibrated_vlm_confidence",
            review_required=True,
            uncertainties=["model_transcription_requires_review"],
            image_base64=base64.b64encode(png).decode("ascii"),
        )
        return page
    return recognize(png, page)


def main():
    """Set kernel limits before parser imports and replace temporary output with safe final JSON."""
    resource.setrlimit(resource.RLIMIT_AS, (512 * 1024**2, 512 * 1024**2))
    resource.setrlimit(resource.RLIMIT_CPU, (8, 9))
    resource.setrlimit(resource.RLIMIT_FSIZE, (8 * 1024**2, 8 * 1024**2))
    resource.setrlimit(resource.RLIMIT_NOFILE, (32, 32))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    os.umask(0o077)
    from src.application.services.file_storage_policy import StoragePolicyError
    from src.application.services.ocr_contract import validate_page

    try:
        suffix, number, mode = sys.argv[1:]
        if suffix not in ("pdf", "png", "jpg", "jpeg", "webp") or mode not in (
            "auto",
            "ocr",
            "vlm",
        ):
            raise StoragePolicyError("invalid_ocr_request", 422)
        with os.fdopen(os.dup(0), "rb") as source:
            result = validate_page(process(source, suffix, int(number), mode))
    except MemoryError:
        result = {"error": "ocr_limits_exceeded"}
    except StoragePolicyError as error:
        codes = {
            "ocr_page_not_found",
            "ocr_processing_timeout",
            "ocr_processing_unavailable",
            "ocr_limits_exceeded",
            "invalid_ocr_request",
        }
        result = {
            "error": error.code
            if error.code in codes
            else "ocr_limits_exceeded"
            if error.code.endswith("exceeded")
            else "invalid_ocr_content"
        }
    except Exception:
        result = {"error": "invalid_ocr_content"}
    with os.fdopen(os.dup(1), "r+b") as output:
        output.seek(0)
        output.truncate()
        output.write(
            json.dumps(result, ensure_ascii=False, separators=(",", ":")).encode(
                "utf-8"
            )
        )
    logger.info("ocr_worker_finished accepted=%s", "method" in result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
