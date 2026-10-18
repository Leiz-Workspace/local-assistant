"""Validate bounded DOCX edit plans and versioned paragraph/table/style worker replies."""

import logging
from importlib.metadata import version

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from src.application.services.file_storage_policy import StoragePolicyError

logger = logging.getLogger(__name__)
DOCX_VERSION = "docx-runs-v1:lxml-" + version("lxml")
DOCX_MEDIA = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
MAX_PLAN_BYTES = 64 * 1024
MAX_TEXT_BYTES = 1024 * 1024
MAX_RUN_BYTES = 64 * 1024
MAX_READ_BYTES = 8 * 1024 * 1024
MAX_OUTPUT_BYTES = 25 * 1024 * 1024


class StrictModel(BaseModel):
    """Reject unknown fields and coercion at both API and worker protocol boundaries."""

    model_config = ConfigDict(extra="forbid", strict=True)


class RunEdit(StrictModel):
    """Target one existing direct run without allowing XML or formatting mutation."""

    paragraph_id: int = Field(ge=1, le=10000)
    run_index: int = Field(ge=1, le=20000)
    text: str = Field(max_length=MAX_RUN_BYTES)


class RewritePlan(StrictModel):
    """Require a source hash precondition and bounded unique run edits."""

    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    edits: list[RunEdit] = Field(min_length=1, max_length=100)


def validate_plan(payload) -> RewritePlan:
    """Reject ambiguous indices, invalid XML characters and oversized UTF-8 run replacements."""
    try:
        plan = RewritePlan.model_validate(payload)
        seen = set()
        for edit in plan.edits:
            key = (edit.paragraph_id, edit.run_index)
            if key in seen or len(edit.text.encode("utf-8")) > MAX_RUN_BYTES:
                raise ValueError("Invalid edit")
            seen.add(key)
            if any(
                not (
                    character in "\t\n\r"
                    or 0x20 <= ord(character) <= 0xD7FF
                    or 0xE000 <= ord(character) <= 0xFFFD
                    or 0x10000 <= ord(character) <= 0x10FFFF
                )
                for character in edit.text
            ):
                raise ValueError("Invalid XML character")
            if "\r" in edit.text:
                raise ValueError("Use newline instead of carriage return")
    except (ValidationError, ValueError, UnicodeError):
        raise StoragePolicyError("invalid_docx_edits", 422) from None
    logger.info("docx_edit_plan_validated edits=%d", len(plan.edits))
    return plan


class RunView(StrictModel):
    """Expose native run text and direct formatting without inferring inherited styles."""

    run_index: int = Field(ge=1)
    text: str
    style_id: str | None
    bold: bool | None
    italic: bool | None
    underline: str | None


class ParagraphView(StrictModel):
    """Locate a main-body paragraph and identify whether plain-run editing is safe."""

    paragraph_id: int = Field(ge=1)
    text: str
    style_id: str | None
    editable: bool
    runs: list[RunView] = Field(max_length=20000)


class CellView(StrictModel):
    """Preserve logical row/cell coordinates and original merge metadata."""

    row: int = Field(ge=1)
    column: int = Field(ge=1)
    paragraph_ids: list[int] = Field(max_length=10000)
    grid_span: int = Field(ge=1, le=10000)
    vertical_merge: str | None


class TableView(StrictModel):
    """Expose table style and cell-to-paragraph provenance without flattening cell identity."""

    table_id: int = Field(ge=1)
    style_id: str | None
    cells: list[CellView] = Field(max_length=10000)


class StyleView(StrictModel):
    """Expose declared style identity and inheritance references without executing layout."""

    style_id: str
    kind: str | None
    name: str | None
    based_on: str | None


class DocxView(StrictModel):
    """Require a complete versioned read result with bounded collections."""

    processor: str
    paragraphs: list[ParagraphView] = Field(max_length=10000)
    tables: list[TableView] = Field(max_length=10000)
    styles: list[StyleView] = Field(max_length=1000)


def validate_view(payload) -> dict:
    """Validate worker output numbering, references and aggregate run/text/cell budgets."""
    try:
        view = DocxView.model_validate(payload)
        if view.processor != DOCX_VERSION:
            raise ValueError("Invalid processor")
        total = runs = cells = 0
        for number, paragraph in enumerate(view.paragraphs, 1):
            if paragraph.paragraph_id != number:
                raise ValueError("Invalid paragraph")
            total += len(paragraph.text.encode("utf-8"))
            for index, run in enumerate(paragraph.runs, 1):
                if run.run_index != index:
                    raise ValueError("Invalid run")
                if len(run.text.encode("utf-8")) > MAX_RUN_BYTES:
                    raise StoragePolicyError("docx_limits_exceeded", 413)
                runs += 1
        for number, table in enumerate(view.tables, 1):
            if table.table_id != number:
                raise ValueError("Invalid table")
            cells += len(table.cells)
            for cell in table.cells:
                if any(
                    type(pid) is not int or not 1 <= pid <= len(view.paragraphs)
                    for pid in cell.paragraph_ids
                ):
                    raise ValueError("Invalid paragraph reference")
        if total > MAX_TEXT_BYTES or runs > 20000 or cells > 10000:
            raise StoragePolicyError("docx_limits_exceeded", 413)
    except (ValidationError, ValueError, UnicodeError):
        raise StoragePolicyError("docx_processing_unavailable", 503) from None
    return view.model_dump()
