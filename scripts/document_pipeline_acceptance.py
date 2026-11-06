"""Evaluate the trusted synthetic D23 document corpus using actual production parsing and chunking."""

import argparse
import asyncio
import hashlib
import io
import json
import logging
import resource
import tempfile
import time
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid5

from apps.api.services.vision_ocr import transcribe_image
from scripts.document_pipeline_oracles import (
    chunk_checks,
    native_checks,
    structure_checks,
)
from scripts.ocr_acceptance import distance
from src.application.services.chunk_sources import docx_units, ocr_units, xlsx_units
from src.application.services.document_chunks import (
    ChunkSource,
    build_chunks,
    text_unit,
)
from src.application.services.file_storage_policy import StoragePolicyError
from src.application.services.ocr_contract import validate_page
from src.infrastructure.docx_processor import process_docx
from src.infrastructure.file_verifier import verify_file
from src.infrastructure.page_ocr import prepare_page
from src.infrastructure.pdf_extractor import EXTRACTOR_VERSION, extract_pdf
from src.infrastructure.xlsx_processor import process_xlsx

logger = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests/fixtures"
MANIFEST = FIXTURES / "pipeline/manifest.json"
OWNER, NAMESPACE = UUID(int=2301), UUID(int=2302)
REPORT_VERSION = "mixed-document-evaluation-v1"
KINDS = {"text", "pdf", "docx", "xlsx", "ocr", "docx_rewrite", "xlsx_rewrite"}


class StageLedger:
    """Retain only safe stage names and wall durations, including failed production stages."""

    def __init__(self):
        """Initialize one sequential synthetic case's stage inventory."""
        self.stages = []
        self.current = "input"

    def run(self, stage, function, *args, **kwargs):
        """Time owned synchronous work without copying content or exceptions into evidence."""
        self.current = stage
        start = time.perf_counter()
        try:
            return function(*args, **kwargs)
        finally:
            self.stages.append(
                dict(
                    stage=stage, wall_ms=round((time.perf_counter() - start) * 1000, 3)
                )
            )
            logger.info("document_pipeline_stage_complete stage=%s", stage)

    async def run_async(self, stage, function, *args):
        """Time an explicitly requested local vision call without logging recognized data."""
        self.current = stage
        start = time.perf_counter()
        try:
            return await function(*args)
        finally:
            self.stages.append(
                dict(
                    stage=stage, wall_ms=round((time.perf_counter() - start) * 1000, 3)
                )
            )
            logger.info("document_pipeline_stage_complete stage=%s", stage)


def load_manifest():
    """Load only the repository's bounded trusted synthetic case inventory and validate scope."""
    manifest = json.loads(MANIFEST.read_text())
    cases = manifest["cases"]
    if manifest["version"] != "mixed-documents-v1" or not 1 <= len(cases) <= 64:
        raise ValueError("Invalid synthetic corpus")
    identifiers = set()
    for case in cases:
        path = (FIXTURES / case["fixture"]).resolve()
        if (
            not path.is_relative_to(FIXTURES.resolve())
            or not path.is_file()
            or path.stat().st_size > 1024**2
            or case["kind"] not in KINDS
            or case["id"] in identifiers
        ):
            raise ValueError("Invalid synthetic case")
        identifiers.add(case["id"])
    logger.info("document_pipeline_manifest_loaded cases=%d", len(cases))
    return manifest


def run_source(data, function, *args, **kwargs):
    """Supply a real regular read-only parser source through an anonymous temporary descriptor."""
    with tempfile.TemporaryFile() as source:
        source.write(data)
        source.seek(0)
        source.flush()
        with Path(f"/proc/self/fd/{source.fileno()}").open("rb") as reader:
            return function(reader, *args, **kwargs)


def rewrite_source(data, kind):
    """Run fixed synthetic edits with actual source-hash-bound DOCX/XLSX processors."""
    plan = dict(source_sha256=hashlib.sha256(data).hexdigest())
    if kind == "docx":
        plan["edits"] = [dict(paragraph_id=2, run_index=1, text="Đã sửa")]
        return run_source(data, process_docx, "rewrite", plan)
    plan["edits"] = [dict(sheet_id=1, cell="A2", kind="number", value="99.5")]
    return run_source(data, process_xlsx, "rewrite", plan)


def independent_reopen(original, output, kind):
    """Independently reopen trusted golden edits and compare untouched package members byte-for-byte."""
    changed = "word/document.xml" if kind == "docx" else "xl/worksheets/sheet1.xml"
    with (
        zipfile.ZipFile(io.BytesIO(original)) as before,
        zipfile.ZipFile(io.BytesIO(output)) as after,
    ):
        preserved = before.namelist() == after.namelist() and all(
            before.read(name) == after.read(name)
            for name in before.namelist()
            if name != changed
        )
    if kind == "docx":
        from docx import Document

        doc = Document(io.BytesIO(output))
        correct = (
            doc.paragraphs[1].text == "Đã sửa + Beta\tXin chào\nViệt Nam"
            and doc.paragraphs[1].runs[0].bold
            and doc.paragraphs[1].runs[1].italic
            and doc.paragraphs[0].style.style_id == "Heading1"
        )
    else:
        from openpyxl import load_workbook

        formulas = load_workbook(io.BytesIO(output), data_only=False)
        caches = load_workbook(io.BytesIO(output), data_only=True)
        sheet = formulas["Dữ liệu"]
        correct = (
            sheet["A2"].value == 99.5
            and sheet["A2"].number_format == "0.00"
            and sheet["C2"].value == "=SUM(A2:B2)"
            and caches["Dữ liệu"]["C2"].value == 30
            and caches["Summary"]["A1"].value == 60
            and str(sheet.merged_cells) == "A4:B4"
        )
        formulas.close()
        caches.close()
    return dict(independent_reopen=bool(correct), untouched_members=preserved)


def projection(kind, view, base):
    """Build independent exact lexical field references alongside production source adapters."""
    fields = {}
    if kind == "text":
        fields[(base + "#text", "text")] = view
        return [text_unit(base + "#text", view)], fields, "utf8-text-v1"
    if kind == "pdf":
        for page in view:
            fields[(f"{base}#page={page['page_number']}", "text")] = page["text"]
        units = [
            text_unit(locator, text, kind="page_text")
            for (locator, _), text in fields.items()
        ]
        return units, fields, EXTRACTOR_VERSION
    file_id = UUID(base.removeprefix("file:"))
    if kind == "docx":
        for paragraph in view["paragraphs"]:
            fields[(f"{base}#paragraph={paragraph['paragraph_id']}", "text")] = (
                paragraph["text"]
            )
        units = docx_units(file_id, view)
    elif kind == "xlsx":
        for sheet in view["sheets"]:
            for cell in sheet["cells"]:
                for field in ("value", "formula", "cached_value"):
                    if cell[field] is not None:
                        fields[
                            (
                                f"{base}#sheet={sheet['sheet_id']}&cell={cell['cell']}",
                                field,
                            )
                        ] = cell[field]
            if not sheet["cells"]:
                fields[(f"{base}#sheet={sheet['sheet_id']}", "text")] = ""
        units = xlsx_units(file_id, view)
    else:
        locator = f"{base}#page={view['page_number']}"
        fields[(locator, "text")] = view["text"]
        for table_id, table in enumerate(view["tables"], 1):
            for number, row in enumerate(table["rows"], 1):
                for column, value in enumerate(row, 1):
                    fields[
                        (
                            f"{locator}&table={table_id}&row={number}&cell={column}",
                            "text",
                        )
                    ] = value
        units = ocr_units(file_id, view)
    processor = view["processor"]
    if kind == "ocr":
        processor += ":" + view["method"] + ":" + view["engine"]
    return units, fields, processor


def ocr_checks(view, expected, mode):
    """Score exact OCR errors separately from successful uncertainty detection or VLM table matching."""
    metrics, checks = {}, {}
    if mode == "vlm":
        rows = view["tables"][0]["rows"] if len(view["tables"]) == 1 else []
        expected_rows = expected["rows"]
        matches = sum(
            i < len(rows) and j < len(rows[i]) and value == rows[i][j]
            for i, row in enumerate(expected_rows)
            for j, value in enumerate(row)
        )
        metrics.update(
            matched_cells=matches, expected_cells=sum(map(len, expected_rows))
        )
        checks.update(
            exact_table=rows == expected_rows,
            model_review=view["method"] == "local_vlm"
            and view["review_required"]
            and view["confidence_score"] is None,
        )
    else:
        text = expected["texts"][0]
        cer = distance(text, view["text"]) / max(1, len(text))
        wer = distance(text.split(), view["text"].split()) / max(1, len(text.split()))
        metrics.update(
            character_error_rate=cer,
            word_error_rate=wer,
            transcription_passed=cer == 0 and wer == 0,
        )
        if expected["outcome"] == "degraded":
            checks["uncertainty_detection"] = view["review_required"] and (
                view["confidence_score"] is None or view["confidence_score"] < 85
            )
        else:
            checks["exact_text"] = cer == 0 and wer == 0
        if expected["outcome"] == "empty":
            checks["empty_review"] = (
                view["review_required"] and view["confidence_score"] is None
            )
    metrics.update(
        review_required=view["review_required"],
        method=view["method"],
        engine=view["engine"],
    )
    return checks, metrics


async def evaluate_case(case, *, include_vlm=False):
    """Evaluate one trusted case and retain sanitized failures without aborting the remaining corpus."""
    ledger = StageLedger()
    started = time.perf_counter()
    before = resource.getrusage(resource.RUSAGE_CHILDREN)
    data = (FIXTURES / case["fixture"]).read_bytes()
    result = dict(
        id=case["id"],
        fixture=case["fixture"],
        source_sha256=hashlib.sha256(data).hexdigest(),
        input_bytes=len(data),
        expected_outcome=case["expected"]["outcome"],
        checks={},
        metrics={},
    )
    expected = case["expected"]
    kind = case["kind"].removesuffix("_rewrite")
    source_data = data
    try:
        if case.get("mode") == "vlm" and not include_vlm:
            result.update(
                outcome="not_run",
                passed=False,
                error=dict(stage="vision", code="explicit_vlm_not_requested"),
            )
            return result
        await asyncio.to_thread(
            ledger.run,
            "verify",
            run_source,
            data,
            verify_file,
            Path(case["fixture"]).name,
        )
        if case["kind"].endswith("_rewrite"):
            source_data = await asyncio.to_thread(
                ledger.run, "rewrite", rewrite_source, data, kind
            )
            result["checks"].update(
                await asyncio.to_thread(
                    ledger.run,
                    "independent_reopen",
                    independent_reopen,
                    data,
                    source_data,
                    kind,
                )
            )
        if kind == "text":
            view = ledger.run("parse", source_data.decode, "utf-8")
        elif kind == "ocr":
            view = await asyncio.to_thread(
                ledger.run,
                "parse",
                run_source,
                source_data,
                prepare_page,
                Path(case["fixture"]).suffix[1:],
                case.get("page", 1),
                case.get("mode", "auto"),
            )
            if case.get("mode") == "vlm":
                vision = await ledger.run_async(
                    "vision", transcribe_image, view["image_base64"]
                )
                view.update(
                    method="local_vlm",
                    engine=vision["engine"],
                    text=vision["text"],
                    tables=vision["tables"],
                    table_structure_status="unverified_vlm",
                    uncertainties=view["uncertainties"] + vision["uncertain_regions"],
                )
            view["image_base64"] = None
            view = validate_page(view)
            view.pop("image_base64")
        else:
            processor = {
                "pdf": extract_pdf,
                "docx": process_docx,
                "xlsx": process_xlsx,
            }[kind]
            view = await asyncio.to_thread(
                ledger.run, "parse", run_source, source_data, processor
            )
        if expected["outcome"] != "rejected":
            if kind == "ocr":
                checks, metrics = ocr_checks(view, expected, case.get("mode", "auto"))
                result["metrics"].update(metrics)
                checks["page_mapping"] = view["page_number"] == case.get(
                    "page", 1
                ) and view["page_count"] == (
                    2 if case["fixture"].endswith("scanned.pdf") else 1
                )
            else:
                checks = native_checks(kind, view, expected)
            result["checks"].update(checks)
        file_id = uuid5(
            NAMESPACE, case["fixture"] + (":rewritten" if source_data != data else "")
        )
        base = f"file:{file_id}"
        units, fields, processor = ledger.run("adapt", projection, kind, view, base)
        source = ChunkSource(
            OWNER,
            NAMESPACE,
            file_id,
            hashlib.sha256(source_data).hexdigest(),
            processor,
        )
        max_bytes = case.get("max_bytes", 2048)
        payload = ledger.run("chunk", build_chunks, source, units, max_bytes)
        repeated = ledger.run("repeat_chunk", build_chunks, source, units, max_bytes)
        checks, metrics = ledger.run(
            "score", chunk_checks, payload, fields, source, max_bytes
        )
        result["checks"].update(checks, deterministic_repeat=payload == repeated)
        result["checks"].update(structure_checks(kind, view, payload, base))
        result["metrics"].update(metrics)
        result.update(processor=processor, chunk_input_sha256=source.sha256)
        result["outcome"] = (
            "unexpected_acceptance"
            if expected["outcome"] == "rejected"
            else "degraded"
            if expected["outcome"] == "degraded"
            and not result["metrics"].get("transcription_passed")
            else "empty"
            if not payload["chunks"]
            else "accepted"
        )
        result["passed"] = expected["outcome"] != "rejected" and all(
            result["checks"].values()
        )
    except StoragePolicyError as error:
        result["error"] = dict(
            stage=ledger.current, code=error.code, status=error.status_code
        )
        result["passed"] = expected["outcome"] == "rejected" and all(
            result["error"][key] == expected[key] for key in ("stage", "code", "status")
        )
        result["outcome"] = (
            "expected_rejection" if result["passed"] else "unexpected_rejection"
        )
    except Exception:
        result.update(
            outcome="failed",
            passed=False,
            error=dict(stage=ledger.current, code="evaluation_failed"),
        )
        logger.error(
            "document_pipeline_case_failed case=%s stage=%s", case["id"], ledger.current
        )
    finally:
        after = resource.getrusage(resource.RUSAGE_CHILDREN)
        result["stages"] = ledger.stages
        result["resources"] = dict(
            wall_ms=round((time.perf_counter() - started) * 1000, 3),
            child_cpu_ms=round(
                (
                    (after.ru_utime + after.ru_stime)
                    - (before.ru_utime + before.ru_stime)
                )
                * 1000,
                3,
            ),
            child_peak_rss_kib_cumulative=after.ru_maxrss,
        )
        logger.info(
            "document_pipeline_case_complete case=%s passed=%s",
            case["id"],
            result.get("passed", False),
        )
    return result


async def measure_pipeline(*, include_vlm=False):
    """Execute the complete versioned corpus and separate gate failures from known quality limitations."""
    manifest = load_manifest()
    cases = [
        await evaluate_case(case, include_vlm=include_vlm) for case in manifest["cases"]
    ]
    failures = [
        dict(
            case=c["id"],
            failed_checks=[key for key, passed in c["checks"].items() if not passed],
            **({"error": c["error"]} if "error" in c else {}),
        )
        for c in cases
        if not c["passed"]
    ]
    quality_failures = [
        dict(
            case=c["id"],
            code="transcription_inaccurate",
            character_error_rate=c["metrics"]["character_error_rate"],
            word_error_rate=c["metrics"]["word_error_rate"],
        )
        for c in cases
        if c["metrics"].get("transcription_passed") is False
    ]
    return dict(
        description="Synthetic D23 pipeline evidence; case acceptance is distinct from transcription accuracy, API authorization and production load certification.",
        version=REPORT_VERSION,
        corpus_version=manifest["version"],
        corpus_sha256=hashlib.sha256(MANIFEST.read_bytes()).hexdigest(),
        measured_at=datetime.now(UTC).isoformat(),
        scope="trusted_synthetic_offline_production_parsers_and_chunker",
        vision_explicitly_requested=include_vlm,
        complete=all(c["outcome"] != "not_run" for c in cases),
        passed=not failures,
        cases=cases,
        failures=failures,
        quality_failures=quality_failures,
        resource_notes="Sequential wall/child CPU measurements; child peak RSS is cumulative Linux KiB, not per-case memory or CORE GPU usage. Parser kernel budgets are certified by regression, not inferred from these timings.",
    )


def save_report(path, report):
    """Persist numeric/hash/version/check evidence without source text, images, model output or exceptions."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    logger.info(
        "document_pipeline_report_saved cases=%d passed=%s",
        len(report["cases"]),
        report["passed"],
    )


def main():
    """Run the explicit synthetic evaluation CLI and fail on any unrun or failed required case."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--include-vlm",
        action="store_true",
        help="Explicitly evaluate the retained synthetic image using the existing local CORE.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "benchmarks/results/d23-document-pipeline.json",
    )
    args = parser.parse_args()
    report = asyncio.run(measure_pipeline(include_vlm=args.include_vlm))
    save_report(args.output, report)
    return 0 if report["passed"] and report["complete"] else 1


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    raise SystemExit(main())
