"""Reproduce real buffered-source/native-descriptor handoff failures across all affected document subprocess adapters."""

import base64
import logging
import os
from pathlib import Path

import pytest

from src.infrastructure.docx_processor import process_docx
from src.infrastructure.file_verifier import verify_file
from src.infrastructure.page_ocr import prepare_page
from src.infrastructure.pdf_extractor import extract_pdf
from src.infrastructure.xlsx_processor import process_xlsx

logger = logging.getLogger(__name__)


def native_operation(kind, source):
    """Run one actual accepted native adapter with unchanged input/format/policy and no model request."""
    if kind == "verify":
        return verify_file(source, "handoff.txt")
    if kind == "pdf":
        return extract_pdf(source)
    if kind == "docx":
        return process_docx(source)
    if kind == "xlsx":
        return process_xlsx(source)
    if kind == "ocr":
        return prepare_page(source, "png", 1, "vlm")
    raise ValueError("unknown_handoff_fixture")


@pytest.mark.parametrize(
    "kind,name",
    [
        ("verify", None),
        ("pdf", "pdf/native-pages.pdf"),
        ("docx", "docx/styled-table.docx"),
        ("xlsx", "xlsx/styled-formulas.xlsx"),
        ("ocr", "ocr/clean.png"),
    ],
)
def test_preread_buffered_source_has_identical_complete_native_result_and_kernel_position(
    kind, name, tmp_path
):
    """Require full original bytes after buffered read-ahead and restore both Python and native FD position after the child exits."""
    path = Path("tests/fixtures") / name if name else tmp_path / "handoff.txt"
    if name is None:
        path.write_bytes(b"An authored complete native handoff fixture.\n")
    with path.open("rb") as source:
        expected = native_operation(kind, source)
    with path.open("rb") as source:
        assert (
            source.read(1)
            and source.tell() == 1
            and os.lseek(source.fileno(), 0, os.SEEK_CUR) > 1
        )
        result = native_operation(kind, source)
        assert (
            result == expected
            and source.tell() == 0
            and os.lseek(source.fileno(), 0, os.SEEK_CUR) == 0
        )
    logger.info("actual_native_buffered_handoff_verified kind=%s", kind)


@pytest.mark.parametrize("page,mode", [(1, "vlm"), (1, "ocr"), (3, "auto")])
def test_small_searchable_pdf_raster_has_complete_native_stdin_after_python_parse(
    page, mode
):
    """Render the original sub-buffer-size native PDF after pypdf read-ahead instead of passing an empty/partial native stream."""
    path = Path("tests/fixtures/pdf/native-pages.pdf")
    assert path.stat().st_size < 8192
    with path.open("rb") as source:
        result = prepare_page(source, "pdf", page, mode)
    assert (
        result["page_number"] == page
        and result["page_count"] == 3
        and result["width"] > 0
        and result["height"] > 0
    )
    if mode == "vlm":
        assert base64.b64decode(result["image_base64"], validate=True).startswith(
            b"\x89PNG\r\n\x1a\n"
        )
    if page == 3:
        assert result["text"] == "" and result["review_required"]
    logger.info("actual_small_pdf_raster_handoff_verified page=%d mode=%s", page, mode)
