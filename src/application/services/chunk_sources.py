"""Adapt native document and uncertain OCR views into exact chunk source units."""

import logging
import re

from src.application.services.document_chunks import (
    MAX_CHUNKS,
    row_unit,
    source_span,
    text_unit,
)
from src.application.services.file_storage_policy import StoragePolicyError
from src.application.services.xlsx_contract import coordinate

logger = logging.getLogger(__name__)


def heading_level(style_id, styles):
    """Resolve declared heading ancestry and reject cyclic style inheritance."""
    visited, level = set(), None
    while style_id:
        if style_id in visited:
            raise StoragePolicyError("unsupported_chunk_structure", 422)
        visited.add(style_id)
        match = re.fullmatch(r"heading([1-9])", style_id, re.IGNORECASE)
        if match and level is None:
            level = int(match[1])
        style_id = styles.get(style_id, {}).get("based_on")
    return level


def docx_units(file_id, view):
    """Keep body paragraphs and atomic table rows in source order with heading references."""
    base = f"file:{file_id}"
    paragraphs = {p["paragraph_id"]: p for p in view["paragraphs"]}
    styles = {s["style_id"]: s for s in view["styles"]}
    membership, events = set(), []
    for table in sorted(view["tables"], key=lambda item: item["table_id"]):
        rows = {}
        for cell in sorted(
            table["cells"], key=lambda item: (item["row"], item["column"])
        ):
            ids = cell["paragraph_ids"]
            if any(pid in membership or pid not in paragraphs for pid in ids) or len(
                ids
            ) != len(set(ids)):
                raise StoragePolicyError("unsupported_chunk_structure", 422)
            membership.update(ids)
            rows.setdefault(cell["row"], []).append(cell)
        for number, cells in sorted(rows.items()):
            ids = [pid for cell in cells for pid in cell["paragraph_ids"]]
            if not ids:
                raise StoragePolicyError("unsupported_chunk_structure", 422)
            locator = f"{base}#table={table['table_id']}&row={number}"
            values, spans = [], []
            for cell in cells:
                values.append(
                    dict(
                        cell,
                        paragraphs=[
                            dict(paragraph_id=pid, text=paragraphs[pid]["text"])
                            for pid in cell["paragraph_ids"]
                        ],
                    )
                )
                spans.extend(
                    source_span(
                        f"{base}#paragraph={pid}", "text", paragraphs[pid]["text"]
                    )
                    for pid in cell["paragraph_ids"]
                )
            events.append(
                (
                    min(ids),
                    row_unit(
                        locator,
                        [dict(row=number, cells=values)],
                        spans=spans,
                        structure=dict(
                            table_id=table["table_id"], style_id=table["style_id"]
                        ),
                    ),
                )
            )
    for pid, paragraph in sorted(paragraphs.items()):
        if pid not in membership:
            locator = f"{base}#paragraph={pid}"
            events.append((pid, text_unit(locator, paragraph["text"])))
    sections, units = [], []
    for pid, unit in sorted(events, key=lambda item: item[0]):
        if unit["kind"] != "rows":
            level = heading_level(paragraphs[pid]["style_id"], styles)
            if level:
                sections = [s for s in sections if s["level"] < level]
                sections.append(dict(level=level, locator=unit["locator"]))
        unit["section"] = list(sections)
        units.append(unit)
    logger.info("docx_chunk_sources_prepared units=%d", len(units))
    return units


def xlsx_units(file_id, view):
    """Preserve lexical cell values/formulas/caches and native sheet row/merge metadata."""
    units = []
    for sheet in sorted(view["sheets"], key=lambda item: item["sheet_id"]):
        base = f"file:{file_id}#sheet={sheet['sheet_id']}"
        rows = {}
        merged_ranges = sorted(sheet["merged_ranges"])
        for cell in sorted(
            sheet["cells"], key=lambda item: coordinate(item["cell"])[::-1]
        ):
            _, number = coordinate(cell["cell"])
            rows.setdefault(number, []).append(cell)
        for number, cells in sorted(rows.items()):
            if len(units) >= MAX_CHUNKS:
                raise StoragePolicyError("chunk_limits_exceeded", 413)
            spans = []
            for cell in cells:
                for field in ("value", "formula", "cached_value"):
                    if cell[field] is not None:
                        spans.append(
                            source_span(
                                f"{base}&cell={cell['cell']}", field, cell[field]
                            )
                        )
            units.append(
                row_unit(
                    f"{base}&row={number}",
                    [dict(row=number, cells=cells)],
                    spans=spans,
                    structure=dict(
                        sheet_id=sheet["sheet_id"],
                        sheet_name=sheet["name"],
                        merged_ranges=merged_ranges,
                    ),
                    quality=dict(formula_cache_status=view["formula_cache_status"]),
                )
            )
        if not rows:
            units.append(
                text_unit(
                    base,
                    "",
                    quality=dict(formula_cache_status=view["formula_cache_status"]),
                )
            )
    logger.info("xlsx_chunk_sources_prepared units=%d", len(units))
    return units


def ocr_units(file_id, page):
    """Keep narrative and table projections distinct without laundering model uncertainty."""
    base = f"file:{file_id}#page={page['page_number']}"
    quality = {
        key: value
        for key, value in page.items()
        if key not in {"text", "tables", "words", "processor", "page_number"}
    }
    units = [text_unit(base, page["text"], quality=quality, kind="page_text")]
    for table_id, table in enumerate(page["tables"], 1):
        for number, row in enumerate(table["rows"], 1):
            locator = f"{base}&table={table_id}&row={number}"
            spans = [
                source_span(f"{locator}&cell={column}", "text", value)
                for column, value in enumerate(row, 1)
            ]
            units.append(
                row_unit(
                    locator,
                    [dict(row=number, cells=row)],
                    spans=spans,
                    quality=quality,
                    structure=dict(table_id=table_id, projection="unverified_table"),
                )
            )
    logger.info("ocr_chunk_sources_prepared units=%d", len(units))
    return units
