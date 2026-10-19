"""Verify grounded native-field citations against real DOCX/XLSX processors and independent fixture goldens."""

import json
import logging
from pathlib import Path

import pytest
from test_file_http import body, declaration
from test_file_http import owned_service as owned_service

from apps.api.services.chunks import chunk_operation
from src.application.services.grounded_answer import evidence_units, parse_answer
from src.application.services.ingestion_contract import plan_ingestion

logger = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parents[2]
DOCX_GOLDEN = {
    ("paragraph=1", "text"): "Báo cáo D19",
    ("paragraph=2", "text"): "Alpha + Beta\tXin chào\nViệt Nam",
    ("paragraph=3", "text"): "Tên",
    ("paragraph=4", "text"): "Giá trị",
    ("paragraph=5", "text"): "một",
    ("paragraph=6", "text"): "42",
    ("paragraph=7", "text"): "merged",
}
XLSX_GOLDEN = {
    ("sheet=1&cell=A1", "value"): "Xin chào",
    ("sheet=1&cell=A2", "value"): "10",
    ("sheet=1&cell=B2", "value"): "20",
    ("sheet=1&cell=C2", "formula"): "SUM(A2:B2)",
    ("sheet=1&cell=C2", "cached_value"): "30",
    ("sheet=1&cell=A3", "value"): "1",
    ("sheet=1&cell=B3", "value"): "shared text",
    ("sheet=1&cell=A4", "value"): "merged",
    ("sheet=2&cell=A1", "formula"): "'Dữ liệu'!C2*2",
    ("sheet=2&cell=A1", "cached_value"): "60",
    ("sheet=2&cell=B1", "value"): "Untouched sheet",
}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "fixture,golden",
    [
        ("docx/styled-table.docx", DOCX_GOLDEN),
        ("xlsx/styled-formulas.xlsx", XLSX_GOLDEN),
    ],
)
async def test_real_native_fields_resolve_exact_original_spans(
    owned_service, fixture, golden
):
    """Resolve every hand-golden lexical field through real retained extraction and production citation parsing."""
    service, owners = owned_service
    path = ROOT / "tests/fixtures" / fixture
    data = path.read_bytes()
    row = await service.reserve(owners[0], **declaration(data, path.name))
    await service.upload(owners[0], row["id"], body(data))
    selection = json.loads((ROOT / "configs/embedding-selected.json").read_text())
    observed = {}
    async with chunk_operation(service, owners[0], row["id"], max_bytes=8192) as (
        source,
        view,
    ):
        plan = plan_ingestion(
            source, owners[0], service.storage.namespace_id, view, selection
        )
        for point in plan.points:
            hit = dict(
                point_id=str(point.point_id),
                file_id=str(row["id"]),
                chunk_id=point.chunk_id,
                source_sha256=plan.source_sha256,
                generation=plan.generation,
                text=point.text,
                provenance=json.loads(point.payload_json),
            )
            for unit in evidence_units([hit]):
                span = unit["source_span"]
                key = (span["locator"].split("#", 1)[1], span["field"])
                assert key not in observed
                assert unit["text"] == golden[key]
                observed[key] = unit["text"]
                model_output = json.dumps(
                    dict(
                        status="answered",
                        answer="Test-only source-field citation.",
                        citations=[
                            dict(source_id=unit["source_id"], quote=golden[key])
                        ],
                    ),
                    ensure_ascii=False,
                )
                citation = parse_answer(model_output, [hit])["citations"][0]
                native = citation["source_span"]
                assert native["locator"] == "file:" + str(row["id"]) + "#" + key[0]
                assert native["field"] == key[1]
                assert native["start"] == 0 and native["end"] == len(golden[key])
                assert citation["source_sha256"] == plan.source_sha256
                assert citation["provenance"] == hit["provenance"]
                assert citation["quote"] == golden[key]
    assert observed == golden
    assert not service._chunk_operations
    logger.info("grounded_native_field_golden_passed fields=%d", len(observed))
