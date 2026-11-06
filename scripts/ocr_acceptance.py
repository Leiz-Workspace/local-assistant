"""Measure synthetic D21 OCR/vision goldens and retain versioned non-private quality evidence."""

import argparse
import asyncio
import hashlib
import json
import logging
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from apps.api.services.vision_ocr import transcribe_image
from src.application.services.ocr_contract import OCR_VERSION
from src.infrastructure.page_ocr import prepare_page
from src.infrastructure.pdf_extractor import extract_pdf

logger = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests/fixtures/ocr"
EXPECTED_TEXT = "LOCAL OCR GOLDEN\nInvoice 2048\nTotal 42 USD"
EXPECTED_ROWS = [["Tên hàng", "Số lượng"], ["Bút", "3"], ["Vở", "5"]]


def distance(expected, actual):
    """Compute exact sequence edits for short trusted character/word quality oracles."""
    previous = list(range(len(actual) + 1))
    for number, left in enumerate(expected, 1):
        current = [number]
        for index, right in enumerate(actual, 1):
            current.append(
                min(
                    current[-1] + 1,
                    previous[index] + 1,
                    previous[index - 1] + (left != right),
                )
            )
        previous = current
    return previous[-1]


def read_page(name, number=1, mode="auto"):
    """Use the production isolated reader on one retained synthetic source descriptor."""
    with (FIXTURES / name).open("rb") as source:
        return prepare_page(source, name.rsplit(".", 1)[1], number, mode)


async def measure_acceptance():
    """Evaluate actual engine output against exact synthetic text/page/table ground truth."""
    cases = []
    for name, number, expected in [
        ("clean.png", 1, EXPECTED_TEXT),
        ("scanned.pdf", 1, EXPECTED_TEXT),
        ("blank.png", 1, ""),
        ("unclear.png", 1, "uncertain 7381"),
        ("scanned.pdf", 2, ""),
    ]:
        page = await asyncio.to_thread(read_page, name, number)
        cer = distance(expected, page["text"]) / max(1, len(expected))
        wer = distance(expected.split(), page["text"].split()) / max(
            1, len(expected.split())
        )
        passed = (
            cer <= 0.02
            and wer == 0
            and (
                bool(expected)
                or page["review_required"]
                and page["confidence_score"] is None
            )
        )
        criterion = "transcription_accuracy"
        if name == "unclear.png":
            criterion = "uncertainty_detection"
            passed = page["review_required"] and (
                page["confidence_score"] is None or page["confidence_score"] < 85
            )
        cases.append(
            dict(
                fixture=name,
                sha256=hashlib.sha256((FIXTURES / name).read_bytes()).hexdigest(),
                page=number,
                method=page["method"],
                engine=page["engine"],
                character_error_rate=cer,
                word_error_rate=wer,
                criterion=criterion,
                engine_score=page["confidence_score"],
                review_required=page["review_required"],
                passed=passed,
            )
        )
    with (FIXTURES / "scanned.pdf").open("rb") as source:
        native = await asyncio.to_thread(extract_pdf, source)
    prepared = await asyncio.to_thread(read_page, "table-vie.png", 1, "vlm")
    vision = await transcribe_image(prepared["image_base64"])
    rows = vision["tables"][0]["rows"] if len(vision["tables"]) == 1 else []
    matched = sum(
        index < len(rows)
        and column < len(rows[index])
        and rows[index][column].strip() == cell
        for index, row in enumerate(EXPECTED_ROWS)
        for column, cell in enumerate(row)
    )
    exact = rows == EXPECTED_ROWS
    versions = {}
    for name, command in [
        ("tesseract", ["/usr/bin/tesseract", "--version"]),
        ("poppler", ["/usr/bin/pdftoppm", "-v"]),
    ]:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
            env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"},
        )
        versions[name] = (result.stdout + result.stderr).splitlines()[0]
    metrics = dict(
        description="Synthetic local D21 OCR/VLM acceptance; scores are not calibrated probabilities or general accuracy claims.",
        measured_at=datetime.now(UTC).isoformat(),
        processor=OCR_VERSION,
        engine_versions=versions,
        cases=cases,
        native_pdf_has_no_text_on_scan=all(not page["text"] for page in native),
        vision=dict(
            fixture="table-vie.png",
            sha256=hashlib.sha256(
                (FIXTURES / "table-vie.png").read_bytes()
            ).hexdigest(),
            engine=vision["engine"],
            expected_cells=6,
            matched_cells=matched,
            cell_accuracy=matched / 6,
            exact_rows_match=exact,
            review_required=True,
            confidence_score=None,
            uncertain_regions_count=len(vision["uncertain_regions"]),
        ),
    )
    metrics["passed"] = (
        all(case["passed"] for case in cases)
        and metrics["native_pdf_has_no_text_on_scan"]
        and exact
    )
    logger.info(
        "ocr_acceptance_measured cases=%d matched_table_cells=%d passed=%s",
        len(cases),
        matched,
        metrics["passed"],
    )
    return metrics


def save_metrics(path, metrics):
    """Write synthetic numeric/version evidence without images, recognized text or credentials."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    logger.info("ocr_acceptance_metrics_saved passed=%s", metrics["passed"])


def main():
    """Run the reproducible local acceptance drill and return nonzero if any quality gate fails."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "benchmarks/results/d21-ocr-acceptance.json",
    )
    args = parser.parse_args()
    metrics = asyncio.run(measure_acceptance())
    save_metrics(args.output, metrics)
    return 0 if metrics["passed"] else 1


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    raise SystemExit(main())
