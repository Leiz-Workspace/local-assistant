"""Read DOCX body structure and rewrite selected plain runs while preserving package parts."""

import io
import logging
import zipfile

from lxml import etree

from src.application.services.docx_contract import (
    DOCX_VERSION,
    MAX_OUTPUT_BYTES,
    validate_plan,
    validate_view,
)
from src.application.services.file_storage_policy import StoragePolicyError

logger = logging.getLogger(__name__)
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
XML_SPACE = "{http://www.w3.org/XML/1998/namespace}space"


def parse_xml(data):
    """Parse preverified XML without entities, DTD loading, network or huge-tree relaxation."""
    return etree.fromstring(
        data,
        parser=etree.XMLParser(
            resolve_entities=False, load_dtd=False, no_network=True, huge_tree=False
        ),
    )


def value(node, path):
    """Read an optional WordprocessingML value attribute without resolving style inheritance."""
    item = node.find(path)
    return None if item is None else item.get(W + "val")


def text_of(node):
    """Read native text, tabs and explicit line breaks in XML document order."""
    return "".join(
        (item.text or "")
        if item.tag == W + "t"
        else "\t"
        if item.tag == W + "tab"
        else "\n"
        if item.tag == W + "br"
        else ""
        for item in node.iter()
    )


def direct_flag(run, name):
    """Keep tri-state direct formatting so absence never falsely means inherited false."""
    node = run.find(W + "rPr/" + W + name)
    return (
        None
        if node is None
        else node.get(W + "val", "true") not in ("0", "false", "off")
    )


def editable(paragraph):
    """Refuse mutation when a paragraph contains structures beyond plain direct runs."""
    return (
        bool(paragraph.findall(W + "r"))
        and all(child.tag in (W + "pPr", W + "r") for child in paragraph)
        and all(
            child.tag in (W + "rPr", W + "t", W + "tab", W + "br")
            for run in paragraph.findall(W + "r")
            for child in run
        )
        and not any(
            node.tag in (W + "rPrChange", W + "pPrChange") for node in paragraph.iter()
        )
        and all(
            node.get(W + "type", "textWrapping") == "textWrapping"
            for node in paragraph.iter(W + "br")
        )
    )


def inspect_document(package, root):
    """Map body paragraphs, runs, tables, merges and style references into bounded structured text."""
    body = root.find(W + "body")
    if body is None:
        raise StoragePolicyError("invalid_docx_content", 415)
    nodes = list(body.iter(W + "p"))
    if len(nodes) > 10000 or sum(len(node.findall(W + "r")) for node in nodes) > 20000:
        raise StoragePolicyError("docx_limits_exceeded", 413)
    paragraphs = []
    ids = {node: number for number, node in enumerate(nodes, 1)}
    for number, node in enumerate(nodes, 1):
        runs = [
            {
                "run_index": index,
                "text": text_of(run),
                "style_id": value(run, W + "rPr/" + W + "rStyle"),
                "bold": direct_flag(run, "b"),
                "italic": direct_flag(run, "i"),
                "underline": value(run, W + "rPr/" + W + "u"),
            }
            for index, run in enumerate(node.findall(W + "r"), 1)
        ]
        paragraphs.append(
            {
                "paragraph_id": number,
                "text": text_of(node),
                "style_id": value(node, W + "pPr/" + W + "pStyle"),
                "editable": editable(node),
                "runs": runs,
            }
        )
    tables = []
    for number, table in enumerate(body.iter(W + "tbl"), 1):
        cells = []
        for row_number, row in enumerate(table.findall(W + "tr"), 1):
            for column, cell in enumerate(row.findall(W + "tc"), 1):
                merge = cell.find(W + "tcPr/" + W + "vMerge")
                cells.append(
                    {
                        "row": row_number,
                        "column": column,
                        "paragraph_ids": [ids[p] for p in cell.iter(W + "p")],
                        "grid_span": int(
                            value(cell, W + "tcPr/" + W + "gridSpan") or "1"
                        ),
                        "vertical_merge": None
                        if merge is None
                        else merge.get(W + "val", "continue"),
                    }
                )
        tables.append(
            {
                "table_id": number,
                "style_id": value(table, W + "tblPr/" + W + "tblStyle"),
                "cells": cells,
            }
        )
    styles = []
    if "word/styles.xml" in package.namelist():
        for node in parse_xml(package.read("word/styles.xml")).findall(W + "style"):
            styles.append(
                {
                    "style_id": node.get(W + "styleId", ""),
                    "kind": node.get(W + "type"),
                    "name": value(node, W + "name"),
                    "based_on": value(node, W + "basedOn"),
                }
            )
    if len(styles) > 1000 or sum(len(table["cells"]) for table in tables) > 10000:
        raise StoragePolicyError("docx_limits_exceeded", 413)
    result = validate_view(
        {
            "processor": DOCX_VERSION,
            "paragraphs": paragraphs,
            "tables": tables,
            "styles": styles,
        }
    )
    logger.info(
        "docx_content_inspected paragraphs=%d tables=%d", len(paragraphs), len(tables)
    )
    return result


def replace_run(run, text):
    """Replace text tokens only, retaining original run properties and Unicode whitespace."""
    for child in list(run):
        if child.tag != W + "rPr":
            run.remove(child)
    buffer = []
    for character in text + "\0":
        if character in ("\t", "\n", "\0"):
            if buffer:
                node = etree.SubElement(run, W + "t")
                node.set(XML_SPACE, "preserve")
                node.text = "".join(buffer)
                buffer.clear()
            if character != "\0":
                etree.SubElement(run, W + ("tab" if character == "\t" else "br"))
        else:
            buffer.append(character)


def rewrite_document(package, root, payload):
    """Change only requested supported runs and preserve every unrelated decompressed ZIP member."""
    plan = validate_plan(payload)
    if any(name.lower().startswith("_xmlsignatures/") for name in package.namelist()):
        raise StoragePolicyError("unsupported_docx_edit", 422)
    paragraphs = list(root.find(W + "body").iter(W + "p"))
    for edit in plan.edits:
        if edit.paragraph_id > len(paragraphs):
            raise StoragePolicyError("docx_edit_not_found", 422)
        paragraph = paragraphs[edit.paragraph_id - 1]
        if not editable(paragraph):
            raise StoragePolicyError("unsupported_docx_edit", 422)
        runs = paragraph.findall(W + "r")
        if edit.run_index > len(runs):
            raise StoragePolicyError("docx_edit_not_found", 422)
        replace_run(runs[edit.run_index - 1], edit.text)
    inspect_document(package, root)
    xml = etree.tostring(root, encoding="UTF-8", xml_declaration=True, standalone=True)
    if len(xml) > 2 * 1024 * 1024:
        raise StoragePolicyError("docx_limits_exceeded", 413)
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", allowZip64=False) as target:
        target.comment = package.comment
        for info in package.infolist():
            target.writestr(
                info,
                xml
                if info.filename == "word/document.xml"
                else package.read(info.filename),
            )
    data = output.getvalue()
    if len(data) > MAX_OUTPUT_BYTES:
        raise StoragePolicyError("docx_limits_exceeded", 413)
    logger.info(
        "docx_content_rewritten edits=%d output_bytes=%d", len(plan.edits), len(data)
    )
    return data
