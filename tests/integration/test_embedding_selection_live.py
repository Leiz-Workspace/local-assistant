"""Require real pinned CPU embedding tradeoffs and an isolated existing-Qdrant schema probe."""

import json
import os

import pytest

from scripts.embedding_acceptance import measure_shortlist
from scripts.embedding_runtime import profiles
from scripts.qdrant_embedding_design import probe_design


def test_real_cpu_shortlist_and_frozen_quality_gates(tmp_path):
    """Measure both real models and retain failures of the smaller candidate rather than tuning labels."""
    if os.environ.get("LOCAL_ASSISTANT_LIVE_E2E") != "1":
        pytest.skip("LOCAL_ASSISTANT_LIVE_E2E not configured")
    report = measure_shortlist()
    assert report["passed"] and report["selected_candidate"] == "e5-base-int8", report
    assert len(report["candidates"]) == 2
    small, base = report["candidates"]
    assert not small["eligible"] and base["eligible"]
    assert base["recall_at_3"] == 0.925
    assert base["peak_rss_mib"] < 2048
    assert base["providers"] == ["CPUExecutionProvider"]
    path = tmp_path / "selection.json"
    path.write_text(json.dumps(report))
    for forbidden in ("Bản sao cơ sở", "query: how", "api_key", "postgresql://"):
        assert forbidden not in path.read_text()


def test_real_shared_qdrant_owned_schema_probe():
    """Validate tenant UUID/schema indexes using a Vault-delivered key and remove the owned probe."""
    key = os.environ.get("LOCAL_ASSISTANT_QDRANT_PROBE_KEY")
    if os.environ.get("LOCAL_ASSISTANT_LIVE_E2E") != "1" or not key:
        pytest.skip("live Qdrant probe credential not configured")
    report = probe_design(key, profiles()[1])
    assert report["passed"] and report["probe_removed"]
    assert report["before_sha256"] == report["after_sha256"]
    assert report["owner_uuid_tenant_index"] and report["dimension"] == 768
