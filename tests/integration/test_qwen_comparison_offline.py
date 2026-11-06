"""Exercise both real CPU embedding workers offline without database, Qdrant or deployment mutations."""

import hashlib
import json
import os

import pytest

from scripts.embedding_runtime import ROOT
from scripts.qwen_embedding_comparison import run_one


def test_real_qwen_e5_workers_preserve_selected_configuration():
    """Verify real model-specific accuracy/guards while keeping the selected configuration and original D24 evidence intact."""
    if os.environ.get("LOCAL_ASSISTANT_EMBEDDING_COMPARE_LIVE") != "1":
        pytest.skip("explicit offline model comparison flag not configured")
    protected = [
        ROOT / "configs/models.yaml",
        ROOT / "configs/embedding-selected.json",
        ROOT / "configs/embedding-candidates.json",
        ROOT / "docs/evidence/d24-embedding-selection.json",
        ROOT / "docs/evidence/d24-qdrant-design.json",
    ]
    before = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in protected}
    baseline = run_one("e5")
    candidate = run_one("qwen")
    assert "error" not in baseline and "error" not in candidate, (baseline, candidate)
    assert baseline["input_manifest_sha256"] == candidate["input_manifest_sha256"]
    assert baseline["corpus_sha256"] == candidate["corpus_sha256"]
    assert baseline["dimension"] == 768 and candidate["dimension"] == 1024
    selected = json.loads((ROOT / "configs/embedding-selected.json").read_text())
    assert selected["candidate"]["repository"] == candidate["repository"]
    assert selected["candidate"]["revision"] == candidate["revision"]
    assert selected["runtime"]["fingerprint"] == candidate["runtime"]["fingerprint"]
    assert selected["runtime"]["packages"] == candidate["runtime"]["packages"]
    assert (
        selected["collection"]["create"]["vectors"]["dense"]["size"]
        == candidate["dimension"]
    )
    assert baseline["recall_at_3"] == 0.925 and candidate["recall_at_3"] == 0.975
    assert candidate["recall_at_5"] == candidate["recall_at_10"] == 1
    for measured in [baseline, candidate]:
        assert (
            measured["runtime"]["device"] == "cpu"
            and measured["gpu_allocation_bytes"] == 0
        )
        assert (
            measured["overflow_rejected"]
            and measured["repeat_max_absolute_delta"] <= 1e-6
        )
        assert measured["unit_norm_max_error"] < 1e-5
        assert (
            measured["qdrant_ingest_throughput"] is None
            and measured["qdrant_disk_index_bytes"] is None
        )
        encoded = json.dumps(measured)
        assert "What happens when" not in encoded and "DATABASE_URL" not in encoded
    assert {
        str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in protected
    } == before
