"""Independently score synthetic document content, exact span coverage and structured chunk fidelity."""

import hashlib
import json
import logging
import re
from collections import defaultdict

logger = logging.getLogger(__name__)


def encoded(value):
    """Serialize the documented chunk identity format independently of production helpers."""
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode()


def chunk_checks(payload, fields, source, max_bytes):
    """Detect missing, overlapping, forged or misplaced source spans and changed identity metadata."""
    intervals = defaultdict(list)
    spans_valid = text_matches = identities_valid = True
    private = dict(
        owner=str(source.owner_id),
        namespace=str(source.namespace_id),
        file=str(source.file_id),
    )
    identity = dict(
        private,
        sha256=source.sha256,
        processor=source.processor,
        chunker="structured-chunks-v1",
        max_bytes=max_bytes,
    )
    for item in payload["chunks"]:
        chunk = dict(item)
        identifier = chunk.pop("id")
        identities_valid &= (
            identifier
            == "chk_"
            + hashlib.sha256(encoded(dict(identity=identity, chunk=chunk))).hexdigest()
        )
        for span in item["spans"]:
            key = (span["locator"], span["field"])
            start, end = span["start"], span["end"]
            valid = (
                key in fields
                and type(start) is int
                and type(end) is int
                and 0 <= start <= end <= len(fields[key])
            )
            spans_valid &= valid
            if valid:
                intervals[key].append((start, end))
        if item["kind"] != "rows":
            if len(item["spans"]) != 1:
                text_matches = False
                continue
            span = item["spans"][0]
            key = (span["locator"], span["field"])
            text_matches &= (
                key in fields
                and type(span["start"]) is int
                and type(span["end"]) is int
                and item["locator"] == key[0]
                and item["text"] == fields[key][span["start"] : span["end"]]
            )
        else:
            text_matches &= item["text"].encode() == encoded(item["structure"]["rows"])
    for item in payload["empty_sources"]:
        key = (item["locator"], "text")
        spans_valid &= (
            key in fields
            and fields[key] == ""
            and item["status"] == "empty_extracted_field"
        )
        intervals[key].append((0, 0))
    covered = 0
    for key, text in fields.items():
        ranges = sorted(intervals.get(key, []))
        cursor, valid = 0, bool(ranges)
        if not text:
            valid = ranges == [(0, 0)]
        for start, end in ranges:
            valid &= start == cursor and (end > start or not text)
            cursor = end
        if valid and cursor == len(text):
            covered += 1
    scope = hashlib.sha256(encoded(private)).hexdigest()
    checks = dict(
        span_valid=bool(spans_valid),
        span_coverage=covered == len(fields) and set(intervals) == set(fields),
        text_projection=bool(text_matches),
        identity_digest=bool(identities_valid),
        source_binding=payload["file_id"] == str(source.file_id)
        and payload["sha256"] == source.sha256
        and payload["processor"] == source.processor
        and payload["max_bytes"] == max_bytes
        and payload["chunker"] == "structured-chunks-v1"
        and payload["span_unit"] == "unicode_code_points",
        access_labels=payload["access"]
        == dict(visibility="private", principal_id=str(source.owner_id), scope=scope)
        and payload["content_trust"] == "untrusted",
        byte_limits=all(
            0 < len(c["text"].encode()) <= max_bytes for c in payload["chunks"]
        )
        and len(encoded(payload)) <= 8 * 1024**2
        and len(payload["chunks"]) + len(payload["empty_sources"]) <= 1000,
    )
    logger.info(
        "pipeline_chunk_oracle_scored fields=%d covered=%d passed=%s",
        len(fields),
        covered,
        all(checks.values()),
    )
    return checks, dict(
        source_fields=len(fields),
        covered_fields=covered,
        coverage_ratio=covered / max(1, len(fields)),
        chunks=len(payload["chunks"]),
        empty_sources=len(payload["empty_sources"]),
        reply_bytes=len(encoded(payload)),
    )


def native_checks(kind, view, expected):
    """Compare actual native projections against handwritten fixture content and structure oracles."""
    checks = {}
    if kind in {"text", "pdf", "docx"}:
        if kind == "text":
            texts = [view]
        elif kind == "pdf":
            texts = [page["text"] for page in view]
        else:
            texts = [paragraph["text"] for paragraph in view["paragraphs"]]
        checks["exact_text"] = texts == expected["texts"]
        if kind == "pdf":
            checks["page_mapping"] = [page["page_number"] for page in view] == list(
                range(1, len(texts) + 1)
            )
    if kind == "docx":
        cells = (
            [
                (
                    c["row"],
                    c["column"],
                    c["paragraph_ids"],
                    c["grid_span"],
                    c["vertical_merge"],
                )
                for c in view["tables"][0]["cells"]
            ]
            if len(view["tables"]) == 1
            else []
        )
        checks["table_structure"] = (
            cells
            == [
                (1, 1, [3], 1, None),
                (1, 2, [4], 1, None),
                (2, 1, [5], 1, None),
                (2, 2, [6], 1, None),
                (3, 1, [7], 2, None),
            ]
            and view["tables"][0]["style_id"] == "TableGrid"
        )
        runs = view["paragraphs"][1]["runs"]
        checks["styles"] = (
            view["paragraphs"][0]["style_id"] == "Heading1"
            and len(runs) == 3
            and runs[0]["bold"] is True
            and runs[1]["italic"] is True
            and runs[2]["underline"] == "single"
        )
    if kind == "xlsx":
        actual = [
            dict(
                sheet_id=s["sheet_id"],
                name=s["name"],
                merges=s["merged_ranges"],
                cells=[
                    [
                        c["cell"],
                        c["kind"],
                        c["value"],
                        c["formula"],
                        c["cached_value"],
                        c["style_index"],
                    ]
                    for c in s["cells"]
                ],
            )
            for s in view["sheets"]
        ]
        checks["exact_cells"] = actual == expected["sheets"]
        checks["formula_cache_uncertainty"] = (
            view["formula_cache_status"] == "preserved_not_recalculated"
        )
        checks["formula_attributes"] = view["sheets"][0]["cells"][3][
            "formula_attributes"
        ] == {"ca": "1"}
    return checks


def structure_checks(kind, view, payload, base):
    """Verify row cell payloads, section references and uncertainty survive their source projections."""
    checks = {}
    rows = [c for c in payload["chunks"] if c["kind"] == "rows"]
    if kind == "docx":
        paragraphs = {p["paragraph_id"]: p["text"] for p in view["paragraphs"]}
        expected = {}
        for table in view["tables"]:
            grouped = defaultdict(list)
            for cell in table["cells"]:
                grouped[cell["row"]].append(
                    dict(
                        cell,
                        paragraphs=[
                            dict(paragraph_id=i, text=paragraphs[i])
                            for i in cell["paragraph_ids"]
                        ],
                    )
                )
            for number, cells in grouped.items():
                expected[f"{base}#table={table['table_id']}&row={number}"] = dict(
                    table_id=table["table_id"],
                    style_id=table["style_id"],
                    rows=[dict(row=number, cells=cells)],
                )
        checks["row_structure"] = {
            c["locator"]: c["structure"] for c in rows
        } == expected
        checks["section_mapping"] = all(
            c["section_path"] == [dict(level=1, locator=base + "#paragraph=1")]
            for c in payload["chunks"]
        )
    if kind == "xlsx":
        expected = {}
        for sheet in view["sheets"]:
            grouped = defaultdict(list)
            for cell in sheet["cells"]:
                grouped[int(re.search(r"\d+$", cell["cell"])[0])].append(cell)
            for number, cells in grouped.items():
                expected[f"{base}#sheet={sheet['sheet_id']}&row={number}"] = dict(
                    sheet_id=sheet["sheet_id"],
                    sheet_name=sheet["name"],
                    merged_ranges=sorted(sheet["merged_ranges"]),
                    rows=[dict(row=number, cells=cells)],
                )
        checks["row_structure"] = {
            c["locator"]: c["structure"] for c in rows
        } == expected
        checks["cache_flag_propagation"] = all(
            c["quality"] == dict(formula_cache_status=view["formula_cache_status"])
            for c in payload["chunks"]
        )
    if kind == "ocr":
        quality = {
            k: v
            for k, v in view.items()
            if k not in {"text", "tables", "words", "processor", "page_number"}
        }
        checks["quality_propagation"] = all(
            c["quality"] == quality
            for c in [*payload["chunks"], *payload["empty_sources"]]
        )
        expected = {}
        for table_id, table in enumerate(view["tables"], 1):
            for number, row in enumerate(table["rows"], 1):
                expected[
                    f"{base}#page={view['page_number']}&table={table_id}&row={number}"
                ] = dict(
                    table_id=table_id,
                    projection="unverified_table",
                    rows=[dict(row=number, cells=row)],
                )
        checks["row_structure"] = {
            c["locator"]: c["structure"] for c in rows
        } == expected
    return checks
