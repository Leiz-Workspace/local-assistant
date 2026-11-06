"""Inspect workbook XML and replace literal cells while retaining formula/cache/style package data."""

import io
import logging
import posixpath
import zipfile

from lxml import etree

from src.application.services.file_storage_policy import StoragePolicyError
from src.application.services.xlsx_contract import (
    CACHE_STATUS,
    MAX_OUTPUT_BYTES,
    MAX_TEXT_BYTES,
    XLSX_VERSION,
    coordinate,
    valid_text,
    validate_plan,
    validate_view,
)

logger = logging.getLogger(__name__)
S = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
P = "{http://schemas.openxmlformats.org/package/2006/relationships}"


def reject():
    """Reject unsupported or ambiguous workbook structure without exposing parser diagnostics."""
    raise StoragePolicyError("invalid_xlsx_content", 415)


def parse_xml(data):
    """Parse already verified XML with external/entity/DTD and huge-tree behavior disabled."""
    return etree.fromstring(
        data,
        parser=etree.XMLParser(
            resolve_entities=False, load_dtd=False, no_network=True, huge_tree=False
        ),
    )


def native_text(node):
    """Collect inline/shared string text without evaluating rich text or phonetic metadata."""
    if node is None:
        return ""
    return "".join(
        item.text or ""
        for item in node.iter(S + "t")
        if item.getparent().tag != S + "rPh"
    )


def workbook_parts(package):
    """Resolve unique sheet relationships and retain package-native worksheet roots."""
    book = parse_xml(package.read("xl/workbook.xml"))
    relationships = parse_xml(package.read("xl/_rels/workbook.xml.rels"))
    parts = []
    targets = set()
    sheets = book.findall(S + "sheets/" + S + "sheet")
    if not 1 <= len(sheets) <= 100:
        raise StoragePolicyError("xlsx_limits_exceeded", 413)
    for sheet in sheets:
        matches = [
            rel
            for rel in relationships
            if rel.get("Id") == sheet.get(R + "id")
            and rel.get("Type", "").endswith("/worksheet")
        ]
        if len(matches) != 1:
            reject()
        path = posixpath.normpath(posixpath.join("xl", matches[0].get("Target", "")))
        if path in targets:
            reject()
        targets.add(path)
        root = parse_xml(package.read(path))
        if root.tag != S + "worksheet":
            reject()
        parts.append(
            (int(sheet.get("sheetId", "0")), sheet.get("name", ""), path, root)
        )
    return parts


def string_table(package):
    """Bound shared strings before resolving any cell references or duplicating string values."""
    values = []
    if "xl/sharedStrings.xml" not in package.namelist():
        return values
    root = parse_xml(package.read("xl/sharedStrings.xml"))
    if root.tag != S + "sst":
        reject()
    total = 0
    for item in root.findall(S + "si"):
        text = native_text(item)
        total += len(text.encode("utf-8"))
        if len(values) >= 100000 or total > MAX_TEXT_BYTES:
            raise StoragePolicyError("xlsx_limits_exceeded", 413)
        values.append((text, any(child.tag != S + "t" for child in item)))
    return values


def inspect_workbook(package, parts):
    """Build bounded native sheets/cells/formulas/styles with explicit uncomputed cache semantics."""
    shared = string_table(package)
    style_count = 1
    if "xl/styles.xml" in package.namelist():
        styles = parse_xml(package.read("xl/styles.xml"))
        style_count = len(styles.findall(S + "cellXfs/" + S + "xf"))
        if not 1 <= style_count <= 10000:
            raise StoragePolicyError("xlsx_limits_exceeded", 413)
    sheets = []
    total = count = 0
    for sheet_id, name, _, root in parts:
        merged = [
            item.get("ref", "")
            for item in root.findall(S + "mergeCells/" + S + "mergeCell")
        ]
        if len(merged) > 10000:
            raise StoragePolicyError("xlsx_limits_exceeded", 413)
        ranges = []
        for reference in merged:
            endpoints = reference.split(":")
            if len(endpoints) != 2:
                reject()
            ranges.append(tuple(map(coordinate, endpoints)))
        cells = []
        seen_rows = set()
        for row in root.findall(S + "sheetData/" + S + "row"):
            row_id = int(row.get("r", "0"))
            if not 1 <= row_id <= 1048576 or row_id in seen_rows:
                reject()
            seen_rows.add(row_id)
            for node in row.findall(S + "c"):
                address = node.get("r", "")
                column, row_number = coordinate(address)
                if row_number != row_id:
                    reject()
                kind = node.get("t", "n")
                raw = node.find(S + "v")
                raw = None if raw is None else raw.text
                formula = node.find(S + "f")
                rich = False
                if kind == "s":
                    if (
                        raw is None
                        or not raw.isascii()
                        or not raw.isdecimal()
                        or int(raw) >= len(shared)
                    ):
                        reject()
                    value, rich = shared[int(raw)]
                elif kind == "inlineStr":
                    inline = node.find(S + "is")
                    value = native_text(inline)
                    rich = inline is not None and any(
                        child.tag != S + "t" for child in inline
                    )
                else:
                    value = raw
                is_merged = any(
                    start[0] <= column <= end[0] and start[1] <= row_number <= end[1]
                    for start, end in ranges
                )
                cell = {
                    "cell": address,
                    "kind": kind,
                    "value": value if formula is None else None,
                    "formula": None if formula is None else formula.text or "",
                    "formula_attributes": {}
                    if formula is None
                    else dict(formula.attrib),
                    "cached_value": raw if formula is not None else None,
                    "style_index": int(node.get("s", "0")),
                    "editable": formula is None
                    and not rich
                    and not is_merged
                    and kind in ("n", "s", "inlineStr", "b")
                    and all(child.tag in (S + "v", S + "is") for child in node)
                    and set(node.attrib) <= {"r", "s", "t"},
                }
                for text in (cell["value"], cell["formula"], cell["cached_value"]):
                    if text is not None:
                        try:
                            valid_text(text)
                        except ValueError:
                            raise StoragePolicyError(
                                "xlsx_limits_exceeded", 413
                            ) from None
                        total += len(text.encode("utf-8"))
                count += 1
                if count > 50000 or total > MAX_TEXT_BYTES:
                    raise StoragePolicyError("xlsx_limits_exceeded", 413)
                cells.append(cell)
        sheets.append(
            {
                "sheet_id": sheet_id,
                "name": name,
                "cells": cells,
                "merged_ranges": merged,
            }
        )
    result = validate_view(
        {
            "processor": XLSX_VERSION,
            "formula_cache_status": CACHE_STATUS,
            "style_count": style_count,
            "sheets": sheets,
        }
    )
    logger.info("xlsx_content_inspected sheets=%d cells=%d", len(sheets), count)
    return result


def rewrite_workbook(package, parts, view, payload):
    """Edit supported existing literal values and preserve formula nodes and unrelated members."""
    plan = validate_plan(payload)
    if any(name.lower().startswith("_xmlsignatures/") for name in package.namelist()):
        raise StoragePolicyError("unsupported_xlsx_edit", 422)
    lookup = {
        sheet["sheet_id"]: {cell["cell"]: cell for cell in sheet["cells"]}
        for sheet in view["sheets"]
    }
    roots = {sheet_id: (path, root) for sheet_id, _, path, root in parts}
    nodes = {
        sheet_id: {
            node.get("r"): node
            for node in root.findall(S + "sheetData/" + S + "row/" + S + "c")
        }
        for sheet_id, _, _, root in parts
    }
    changed = set()
    for edit in plan.edits:
        cell = lookup.get(edit.sheet_id, {}).get(edit.cell)
        if cell is None:
            raise StoragePolicyError("xlsx_edit_not_found", 422)
        if not cell["editable"]:
            raise StoragePolicyError("unsupported_xlsx_edit", 422)
        node = nodes[edit.sheet_id][edit.cell]
        for child in list(node):
            node.remove(child)
        node.set("t", {"string": "inlineStr", "number": "n", "boolean": "b"}[edit.kind])
        if edit.kind == "string":
            text = etree.SubElement(etree.SubElement(node, S + "is"), S + "t")
            text.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
            text.text = edit.value
        else:
            etree.SubElement(node, S + "v").text = (
                ("1" if edit.value else "0") if edit.kind == "boolean" else edit.value
            )
        changed.add(edit.sheet_id)
    inspect_workbook(package, parts)
    replacements = {}
    for sheet_id in changed:
        path, root = roots[sheet_id]
        xml = etree.tostring(
            root, encoding="UTF-8", xml_declaration=True, standalone=True
        )
        if len(xml) > 2 * 1024 * 1024:
            raise StoragePolicyError("xlsx_limits_exceeded", 413)
        replacements[path] = xml
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", allowZip64=False) as target:
        target.comment = package.comment
        for info in package.infolist():
            target.writestr(
                info, replacements.get(info.filename, package.read(info.filename))
            )
    data = output.getvalue()
    if len(data) > MAX_OUTPUT_BYTES:
        raise StoragePolicyError("xlsx_limits_exceeded", 413)
    logger.info(
        "xlsx_content_rewritten edits=%d changed_sheets=%d",
        len(plan.edits),
        len(changed),
    )
    return data
