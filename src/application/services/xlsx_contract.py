"""Validate bounded workbook views and source-bound literal cell edits without evaluating formulas."""

import logging
import math
import re
from decimal import Decimal, InvalidOperation
from importlib.metadata import version
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from src.application.services.file_storage_policy import StoragePolicyError

logger = logging.getLogger(__name__)
XLSX_MEDIA = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
XLSX_VERSION = "xlsx-literals-v1:lxml-" + version("lxml")
CACHE_STATUS = "preserved_not_recalculated"
MAX_PLAN_BYTES = 64 * 1024
MAX_READ_BYTES = 8 * 1024 * 1024
MAX_OUTPUT_BYTES = 25 * 1024 * 1024
MAX_TEXT_BYTES = 1024 * 1024
MAX_CELL_BYTES = 64 * 1024


def coordinate(address):
    """Validate canonical A1 addresses and return bounded numeric column/row coordinates."""
    if not isinstance(address, str) or not re.fullmatch(
        r"[A-Z]{1,3}[1-9][0-9]{0,6}", address
    ):
        raise ValueError("Invalid cell reference")
    match = re.fullmatch(r"([A-Z]+)([0-9]+)", address)
    column = 0
    for character in match[1]:
        column = column * 26 + ord(character) - 64
    row = int(match[2])
    if column > 16384 or row > 1048576:
        raise ValueError("Cell outside Excel bounds")
    return column, row


def valid_text(text):
    """Reject oversized or XML-invalid cell text without silently changing Unicode content."""
    if (
        len(text.encode("utf-8")) > MAX_CELL_BYTES
        or len(text.encode("utf-16-le")) // 2 > 32767
    ):
        raise ValueError("Cell text limit")
    if any(
        not (
            char in "\t\n"
            or 0x20 <= ord(char) <= 0xD7FF
            or 0xE000 <= ord(char) <= 0xFFFD
            or 0x10000 <= ord(char) <= 0x10FFFF
        )
        for char in text
    ):
        raise ValueError("Invalid XML character")


def valid_number(text):
    """Reject nonfinite, overflowing or underflowing Excel numeric lexical values."""
    if len(text) > 128 or not re.fullmatch(
        r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?",
        text,
    ):
        raise ValueError("Numeric lexical value required")
    number = Decimal(text)
    converted = float(number)
    if (
        not number.is_finite()
        or not math.isfinite(converted)
        or (number != 0 and converted == 0)
    ):
        raise ValueError("Unrepresentable number")


class StrictModel(BaseModel):
    """Reject coercion and unknown fields at API and isolated worker boundaries."""

    model_config = ConfigDict(extra="forbid", strict=True)


class CellEdit(StrictModel):
    """Target one existing literal cell with an explicit native storage kind."""

    sheet_id: int = Field(ge=1, le=2147483647)
    cell: str
    kind: Literal["string", "number", "boolean"]
    value: str | bool


class RewritePlan(StrictModel):
    """Bind a bounded unique cell-edit set to the immutable source SHA-256."""

    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    edits: list[CellEdit] = Field(min_length=1, max_length=100)


def validate_plan(payload):
    """Reject ambiguous coordinates, formula injection and nonrepresentable numeric literals."""
    try:
        plan = RewritePlan.model_validate(payload)
        seen = set()
        for edit in plan.edits:
            coordinate(edit.cell)
            key = (edit.sheet_id, edit.cell)
            if key in seen:
                raise ValueError("Duplicate edit")
            seen.add(key)
            if edit.kind == "boolean":
                if type(edit.value) is not bool:
                    raise ValueError("Boolean required")
            else:
                if type(edit.value) is not str:
                    raise ValueError("String required")
                valid_text(edit.value)
                if edit.kind == "number":
                    valid_number(edit.value)
    except (ValidationError, ValueError, UnicodeError, InvalidOperation, OverflowError):
        raise StoragePolicyError("invalid_xlsx_edits", 422) from None
    logger.info("xlsx_edit_plan_validated edits=%d", len(plan.edits))
    return plan


class CellView(StrictModel):
    """Expose lexical source values and formulas without evaluating or trusting cached results."""

    cell: str
    kind: Literal["n", "s", "inlineStr", "b", "str", "e", "d"]
    value: str | None
    formula: str | None
    formula_attributes: dict[str, str]
    cached_value: str | None
    style_index: int = Field(ge=0, le=9999)
    editable: bool


class SheetView(StrictModel):
    """Preserve workbook sheet identity, cells and native merged-range references."""

    sheet_id: int = Field(ge=1, le=2147483647)
    name: str
    cells: list[CellView] = Field(max_length=50000)
    merged_ranges: list[str] = Field(max_length=10000)


class WorkbookView(StrictModel):
    """Require a bounded versioned workbook reply with an explicit cache uncertainty label."""

    processor: str
    formula_cache_status: Literal["preserved_not_recalculated"]
    style_count: int = Field(ge=1, le=10000)
    sheets: list[SheetView] = Field(min_length=1, max_length=100)


def validate_view(payload):
    """Validate unique sheet/cell identities, style references and aggregate lexical text budgets."""
    try:
        view = WorkbookView.model_validate(payload)
        if view.processor != XLSX_VERSION:
            raise ValueError("Invalid processor")
        ids, names = set(), set()
        total = count = 0
        for sheet in view.sheets:
            if (
                sheet.sheet_id in ids
                or sheet.name.casefold() in names
                or not 1 <= len(sheet.name) <= 31
                or any(char in sheet.name for char in "\\/*?:[]")
                or sheet.name.startswith("'")
                or sheet.name.endswith("'")
            ):
                raise ValueError("Invalid sheet identity")
            ids.add(sheet.sheet_id)
            names.add(sheet.name.casefold())
            seen = set()
            for cell in sheet.cells:
                coordinate(cell.cell)
                if cell.cell in seen or cell.style_index >= view.style_count:
                    raise ValueError("Invalid cell identity/style")
                seen.add(cell.cell)
                count += 1
                for text in (cell.value, cell.formula, cell.cached_value):
                    if text is not None:
                        valid_text(text)
                        total += len(text.encode("utf-8"))
                numeric = cell.cached_value if cell.formula is not None else cell.value
                if cell.kind == "n" and numeric is not None:
                    valid_number(numeric)
                if cell.kind == "b" and numeric not in (None, "0", "1"):
                    raise ValueError("Invalid native boolean")
                if cell.formula is not None and cell.editable:
                    raise ValueError("Editable formula")
            for reference in sheet.merged_ranges:
                parts = reference.split(":")
                if len(parts) != 2:
                    raise ValueError("Invalid merge range")
                start, end = map(coordinate, parts)
                if start[0] > end[0] or start[1] > end[1]:
                    raise ValueError("Reversed range")
        if count > 50000 or total > MAX_TEXT_BYTES:
            raise StoragePolicyError("xlsx_limits_exceeded", 413)
    except (ValidationError, ValueError, UnicodeError, InvalidOperation, OverflowError):
        raise StoragePolicyError("xlsx_processing_unavailable", 503) from None
    return view.model_dump()
