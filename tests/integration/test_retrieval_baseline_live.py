"""Measure the frozen D27 corpus through actual approved CPU encoding and isolated source/SQL/Qdrant retrieval."""

import json
import os
from pathlib import Path

import pytest
from test_file_http import owned_service as owned_service
from test_ingestion_worker import worker_context as worker_context

from scripts.retrieval_baseline import encode_corpus, load_frozen, measure_baseline
from src.infrastructure.qwen_embedding import QwenEmbedding


@pytest.mark.asyncio
async def test_actual_frozen_cpu_source_retrieval_baseline(worker_context):
    """Retain truthful quality/misses from real vectors and verify replay/ACL gates without adopting any model."""
    if os.environ.get("LOCAL_ASSISTANT_EMBEDDING_COMPARE_LIVE") != "1":
        pytest.skip("explicit existing actual Qwen evaluation flag required")
    corpus, plan = load_frozen()
    record, prefix, encoding = await encode_corpus(corpus, plan, QwenEmbedding())
    worker = await worker_context["create"](encoder=record)
    report = await measure_baseline(
        worker, worker_context["owners"], corpus, plan, record, prefix, encoding
    )
    path = Path("data/backups/d27-latest-baseline.json")
    path.touch(mode=0o600, exist_ok=True)
    path.chmod(0o600)
    path.write_text(json.dumps(report, indent=2) + "\n")
    assert report["complete"] and report["protocol_passed"]
    assert report["document_count"] == 24 and report["query_count"] == 36
    assert report["encoding"]["actual_inputs"] == 60
    assert len(report["source_bindings"]) == 24
    assert report["reranker_status"] == "NOT_PROVISIONED_NOT_EVALUATED"
    assert all(0 <= value <= 1 for value in report["metrics"].values())
    assert len(report["queries"]) == 36
    assert len(report["replay_rankings"]) == 2
    assert worker.files._chunk_operations == 0 and not worker.files.active
