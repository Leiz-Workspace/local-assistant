"""Verify exact chunk source mappings, deterministic IDs, access scope and bounded failures."""

import copy
import hashlib
import logging
import tempfile
from dataclasses import replace
from pathlib import Path
from uuid import UUID

import pytest

from src.application.services import document_chunks as module
from src.application.services.chunk_sources import (
    docx_units,
    heading_level,
    ocr_units,
    xlsx_units,
)
from src.application.services.document_chunks import (
    ChunkSource,
    build_chunks,
    canonical,
    row_unit,
    text_unit,
)
from src.application.services.file_storage_policy import StoragePolicyError
from src.infrastructure.docx_processor import process_docx
from src.infrastructure.pdf_extractor import extract_pdf
from src.infrastructure.xlsx_processor import process_xlsx

logger = logging.getLogger(__name__)
ROOT = Path(__file__).parent / "fixtures"
SOURCE = ChunkSource(UUID(int=1), UUID(int=2), UUID(int=3), "a" * 64, "test-v1")


def read_fixture(name, processor):
    """Read a golden through the actual isolated production parser."""
    with tempfile.TemporaryFile() as source:
        source.write((ROOT / name).read_bytes())
        source.seek(0)
        return processor(source)


@pytest.mark.parametrize(
    "text", ["a" * 800, "Việt Nam\n" * 80, "e\u0301ệ😀\t\r\n" * 90, " " * 600, ""]
)
def test_exact_unicode_reconstruction_and_byte_bound(text):
    """Reconstruct every code point without normalization, overlap or byte overflow."""
    result = build_chunks(SOURCE, [text_unit("source#text", text)], 256)
    assert "".join(c["text"] for c in result["chunks"]) == text
    cursor = 0
    for chunk in result["chunks"]:
        span = chunk["spans"][0]
        assert span["start"] == cursor
        assert text[span["start"] : span["end"]] == chunk["text"]
        assert 0 < len(chunk["text"].encode()) <= 256
        cursor = span["end"]
    assert cursor == len(text)
    assert bool(result["empty_sources"]) == (text == "")
    assert result[
        "span_unit"
    ] == "unicode_code_points" and "namespace" not in canonical(result)
    assert result["access"]["principal_id"] == str(SOURCE.owner_id)
    assert result["access"]["visibility"] == "private"
    logger.info("chunk_exact_reconstruction_verified chunks=%d", len(result["chunks"]))


@pytest.mark.parametrize(
    "change",
    [
        "owner_id",
        "namespace_id",
        "file_id",
        "sha256",
        "processor",
        "policy",
        "text",
        "quality",
        "section",
        "structure",
    ],
)
def test_identity_binds_access_source_policy_and_content(change):
    """Repeat exactly and invalidate each material source, access or content change."""
    source, size = SOURCE, 2048
    units = [text_unit("source#text", "payload")]
    baseline = build_chunks(source, units)
    assert build_chunks(source, copy.deepcopy(units)) == baseline
    if change in {"owner_id", "namespace_id", "file_id"}:
        source = replace(source, **{change: UUID(int=100)})
    elif change in {"sha256", "processor"}:
        source = replace(source, **{change: "b" * 64})
    elif change == "policy":
        size = 4096
    elif change == "structure":
        units = [row_unit("source#text", [["payload"]], spans=[])]
    else:
        units[0][change] = "changed" if change == "text" else {"changed": True}
    changed = build_chunks(source, units, size)
    assert changed["chunks"][0]["id"] != baseline["chunks"][0]["id"]
    if change in {"owner_id", "namespace_id", "file_id"}:
        assert changed["access"]["scope"] != baseline["access"]["scope"]


def test_actual_pdf_pages_and_blank():
    """Preserve exact golden pages and list the empty native page explicitly."""
    pages = read_fixture("pdf/native-pages.pdf", extract_pdf)
    units = [
        text_unit(f"file:{SOURCE.file_id}#page={p['page_number']}", p["text"])
        for p in pages
    ]
    result = build_chunks(SOURCE, units)
    assert [c["text"] for c in result["chunks"]] == [
        "Page one: Alpha 123\nSecond line.",
        "Xin ệ",
    ]
    assert result["empty_sources"][0]["locator"].endswith("#page=3")
    assert [c["locator"] for c in result["chunks"]] == [u["locator"] for u in units[:2]]


def test_actual_docx_paragraphs_sections_merged_rows_and_reorder():
    """Represent every paragraph once with heading references and native merged cell metadata."""
    view = read_fixture("docx/styled-table.docx", process_docx)
    result = build_chunks(SOURCE, docx_units(SOURCE.file_id, view))
    assert len(result["chunks"]) == 5
    assert result["chunks"][0]["text"] == "Báo cáo D19"
    assert result["chunks"][1]["text"] == "Alpha + Beta\tXin chào\nViệt Nam"
    assert all(
        c["section_path"]
        == [{"level": 1, "locator": f"file:{SOURCE.file_id}#paragraph=1"}]
        for c in result["chunks"]
    )
    spans = [s for c in result["chunks"] for s in c["spans"]]
    assert len(spans) == len(view["paragraphs"]) == len({s["locator"] for s in spans})
    last = result["chunks"][-1]["structure"]["rows"][0]["cells"][0]
    assert last["grid_span"] == 2
    assert last["paragraphs"][0]["text"] == view["paragraphs"][-1]["text"]
    view["paragraphs"].reverse()
    view["styles"].reverse()
    view["tables"][0]["cells"].reverse()
    assert build_chunks(SOURCE, docx_units(SOURCE.file_id, view)) == result


def test_actual_xlsx_rows_formula_cache_styles_merges_and_reorder():
    """Retain complete cell objects, lexical source spans and explicit stale-cache status."""
    view = read_fixture("xlsx/styled-formulas.xlsx", process_xlsx)
    result = build_chunks(SOURCE, xlsx_units(SOURCE.file_id, view))
    assert len(result["chunks"]) == 5
    row = result["chunks"][1]
    assert row["locator"].endswith("#sheet=1&row=2")
    cells = row["structure"]["rows"][0]["cells"]
    assert cells == view["sheets"][0]["cells"][1:4]
    assert cells[2]["formula"] == "SUM(A2:B2)" and cells[2]["cached_value"] == "30"
    assert cells[2]["formula_attributes"] == {"ca": "1"}
    assert row["quality"]["formula_cache_status"] == "preserved_not_recalculated"
    assert row["structure"]["merged_ranges"] == ["A4:B4"]
    span = next(s for s in row["spans"] if s["field"] == "formula")
    assert span["locator"].endswith("&cell=C2") and span["end"] == len("SUM(A2:B2)")
    for sheet in view["sheets"]:
        sheet["cells"].reverse()
    view["sheets"].reverse()
    assert build_chunks(SOURCE, xlsx_units(SOURCE.file_id, view)) == result


def test_ocr_separate_projections_uncertainty_and_changed_output():
    """Keep VLM table review mandatory and derive new IDs for changed model table content."""
    page = dict(
        page_number=2,
        processor="ocr-v1",
        text="Bút 3",
        method="local_vlm",
        engine="test",
        review_required=True,
        confidence_score=None,
        uncertainties=["unverified"],
        table_structure_status="unverified_vlm",
        words=[],
        coordinate_space="rendered_pixels",
        width=20,
        height=20,
        tables=[dict(rows=[["Bút", "3"]])],
    )
    result = build_chunks(SOURCE, ocr_units(SOURCE.file_id, page))
    narrative, table = result["chunks"]
    assert (
        narrative["kind"] == "page_text"
        and table["structure"]["projection"] == "unverified_table"
    )
    for chunk in result["chunks"]:
        assert (
            chunk["quality"]["review_required"]
            and chunk["quality"]["confidence_score"] is None
        )
        assert chunk["quality"]["uncertainties"] == ["unverified"]
        assert chunk["locator"].startswith(f"file:{SOURCE.file_id}#page=2")
    page["tables"][0]["rows"][0][0] = "Vở"
    changed = build_chunks(SOURCE, ocr_units(SOURCE.file_id, page))
    assert changed["chunks"][0]["id"] == narrative["id"]
    assert changed["chunks"][1]["id"] != table["id"]


@pytest.mark.parametrize("kind", ["row", "source", "count", "reply", "size"])
def test_limits_refuse_partial_output(monkeypatch, kind):
    """Fail on atomic row, source, count, metadata reply or invalid policy bounds."""
    units, size = [text_unit("source#text", "payload")], 256
    if kind == "row":
        units = [row_unit("source#row=1", [["a" * 257]], spans=[])]
    elif kind == "source":
        monkeypatch.setattr(module, "MAX_SOURCE_BYTES", 1)
    elif kind == "count":
        monkeypatch.setattr(module, "MAX_CHUNKS", 0)
    elif kind == "reply":
        monkeypatch.setattr(module, "MAX_REPLY_BYTES", 1)
    else:
        size = True
    with pytest.raises(StoragePolicyError):
        build_chunks(SOURCE, units, size)


@pytest.mark.parametrize("kind", ["cycle", "nested"])
def test_ambiguous_structure_rejected(kind):
    """Reject cyclic style ancestry and overlapping table paragraph membership."""
    if kind == "cycle":
        with pytest.raises(StoragePolicyError, match="unsupported_chunk_structure"):
            heading_level("A", {"A": {"based_on": "B"}, "B": {"based_on": "A"}})
    else:
        view = read_fixture("docx/styled-table.docx", process_docx)
        view["tables"].append(copy.deepcopy(view["tables"][0]))
        with pytest.raises(StoragePolicyError, match="unsupported_chunk_structure"):
            docx_units(SOURCE.file_id, view)


def test_heading_inheritance_and_subsection_boundaries():
    """Resolve basedOn headings and terminate deeper sections at the next parent heading."""
    view = dict(
        paragraphs=[
            dict(paragraph_id=i, style_id=s, text=f"text{i}")
            for i, s in enumerate(["Custom", "Heading2", None, "Heading1"], 1)
        ],
        tables=[],
        styles=[dict(style_id="Custom", based_on="Heading1")],
    )
    units = docx_units(SOURCE.file_id, view)
    assert [len(u["section"]) for u in units] == [1, 2, 2, 1]
    assert units[-1]["section"][0]["locator"].endswith("#paragraph=4")


def test_digest_independently_reproducible():
    """Recompute the documented identity digest independently of chunk construction."""
    chunk = dict(
        build_chunks(SOURCE, [text_unit("source#text", "payload")])["chunks"][0]
    )
    digest = chunk.pop("id")
    identity = dict(
        SOURCE.identity(),
        sha256=SOURCE.sha256,
        processor=SOURCE.processor,
        chunker=module.CHUNK_VERSION,
        max_bytes=2048,
    )
    expected = hashlib.sha256(
        canonical(dict(identity=identity, chunk=chunk)).encode()
    ).hexdigest()
    assert digest == "chk_" + expected


def test_metadata_budget_stops_consuming_units_early(monkeypatch):
    """Reject repeated metadata before materializing or serializing the complete source sequence."""
    monkeypatch.setattr(module, "MAX_REPLY_BYTES", 512)

    def units():
        """Fail if the chunker consumes another unit after an oversized metadata projection."""
        yield text_unit("source", "x", quality={"uncertainty": "x" * 1024})
        pytest.fail("overbudget sequence consumed beyond its first unit")

    with pytest.raises(StoragePolicyError, match="chunk_limits_exceeded"):
        build_chunks(SOURCE, units())


def test_empty_source_count_is_bounded(monkeypatch):
    """Count empty projections toward the response cardinality limit."""
    monkeypatch.setattr(module, "MAX_CHUNKS", 1)
    with pytest.raises(StoragePolicyError, match="chunk_limits_exceeded"):
        build_chunks(SOURCE, [text_unit("a", ""), text_unit("b", "")])
