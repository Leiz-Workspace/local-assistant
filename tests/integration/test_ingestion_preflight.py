"""Exercise actual locked Qwen tokenizer admission without database, vector or selected-model mutations."""

import hashlib
import json
import os
from pathlib import Path
from uuid import UUID

import pytest

from src.application.services.document_chunks import (
    ChunkSource,
    build_chunks,
    text_unit,
)
from src.application.services.file_storage_policy import StoragePolicyError
from src.application.services.ingestion_contract import plan_ingestion
from src.infrastructure.qwen_token_preflight import preflight_plan

ROOT = Path(__file__).resolve().parents[2]


def make_plan(texts):
    """Build trusted D22 output with source/private identity and the owner-approved Qwen selection."""
    owner, namespace, file_id = (UUID(int=value) for value in (21, 22, 23))
    source = ChunkSource(owner, namespace, file_id, "c" * 64, "utf8-text-v1")
    row = dict(
        id=file_id,
        owner_id=owner,
        actual_sha256=source.sha256,
        state="ready",
        deleted_at=None,
        policy_snapshot={"_storage_namespace": str(namespace)},
    )
    view = build_chunks(
        source,
        [text_unit(f"source:{index}", text) for index, text in enumerate(texts)],
        max_bytes=8192,
    )
    selected = json.loads((ROOT / "configs/embedding-selected.json").read_text())
    return plan_ingestion(row, owner, namespace, view, selected)


@pytest.mark.parametrize("length", [512, 513])
def test_actual_qwen_token_boundary_refuses_silent_truncation(length):
    """Accept the complete512-token passage and reject513 tokens without changing any config/evidence."""
    if os.environ.get("LOCAL_ASSISTANT_EMBEDDING_COMPARE_LIVE") != "1":
        pytest.skip("explicit offline Qwen tokenizer integration flag not configured")
    paths = [
        ROOT / name
        for name in (
            "configs/embedding-selected.json",
            "configs/embedding-e5-rollback.json",
            "docs/evidence/d24-embedding-selection.json",
            "docs/evidence/model-eval-001-qwen-e5-comparison.json",
        )
    ]
    before = [hashlib.sha256(path.read_bytes()).hexdigest() for path in paths]
    plan = make_plan([" x" * (length - 1)])
    assert plan.points[0].text == " x" * (length - 1)
    if length == 512:
        assert preflight_plan(plan) == (512,)
    else:
        with pytest.raises(StoragePolicyError) as caught:
            preflight_plan(plan)
        assert (
            caught.value.code == "ingestion_token_limit"
            and caught.value.status_code == 422
        )
    assert before == [hashlib.sha256(path.read_bytes()).hexdigest() for path in paths]


def test_actual_qwen_unicode_batch_matches_exact_point_count(caplog):
    """Count complete private Unicode/plain passages without logging text or returning partial results."""
    if os.environ.get("LOCAL_ASSISTANT_EMBEDDING_COMPARE_LIVE") != "1":
        pytest.skip("explicit offline Qwen tokenizer integration flag not configured")
    texts = ["Việt e\u0301\nGiữ nguyên\t", "private-ingestion-marker"]
    plan = make_plan(texts)
    counts = preflight_plan(plan)
    assert len(counts) == 2 and all(1 <= count <= 512 for count in counts)
    assert [point.text for point in plan.points] == texts
    assert "private-ingestion-marker" not in caplog.text
