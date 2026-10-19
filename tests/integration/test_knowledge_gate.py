"""Evaluate frozen D32 native-document retrieval and exact relevant citations with approved live models."""

import hashlib
import json
import logging
from pathlib import Path

from test_file_http import reserve
from test_grounded_http import RecordingCore, answer
from test_grounded_http import grounded_client as grounded_client
from test_ingestion_http import wait_job
from test_retrieval_http import search

logger = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parents[2]
PLAN = ROOT / "docs/evidence/d32-knowledge-plan.json"


def save_report(report):
    """Retain incremental synthetic results privately even if a later frozen gate fails."""
    path = ROOT / "data/backups/d32-latest-knowledge-live.json"
    path.touch(mode=0o600, exist_ok=True)
    path.chmod(0o600)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    logger.info("knowledge_gate_checkpoint cases=%d", len(report["cases"]))


def publish(client, headers, source, key):
    """Upload immutable fixture bytes and await actual approved whole-chunk embedding publication."""
    raw = (
        source["text"].encode()
        if "text" in source
        else (ROOT / source["path"]).read_bytes()
    )
    assert hashlib.sha256(raw).hexdigest() == source["sha256"]
    identifier = reserve(client, headers, raw, source["filename"], key)["id"]
    response = client.put(
        f"/api/v1/files/{identifier}/content", headers=headers, content=raw
    )
    assert response.status_code == 200, response.text
    response = client.post(
        f"/api/v1/files/{identifier}/index",
        headers=headers,
        params={"max_bytes": source["max_bytes"]},
    )
    assert response.status_code == 202, response.text
    job = wait_job(client, headers, response.json()["id"])
    assert job["active"] and job["chunk_count"] > 0
    logger.info(
        "knowledge_source_published format=%s chunks=%d", key, job["chunk_count"]
    )
    return identifier, job


def verify_native_citations(result, case, source, identifier, owner):
    """Resolve every citation against predeclared relevant native fields and require the answer-bearing quote."""
    assert (
        result["status"] == "answered" and result["answer_trust"] == "model_generated"
    )
    assert case["expected"] in result["answer"] and result["citations"]
    required = False
    for cite in result["citations"]:
        assert cite["file_id"] == identifier
        assert cite["source_sha256"] == source["sha256"]
        span = cite["source_span"]
        prefix = "file:" + identifier + "#"
        assert span["locator"].startswith(prefix)
        key = span["locator"][len(prefix) :] + ":" + span["field"]
        assert key in case["relevant_fields"], key
        native_text = source["golden_fields"][key]
        assert span["unit"] == "unicode_code_points"
        assert native_text[span["start"] : span["end"]] == cite["quote"]
        assert cite["quote"] and native_text.count(cite["quote"]) == 1
        assert cite["content_trust"] == "untrusted"
        assert cite["provenance"]["owner_id"] == str(owner)
        assert cite["chunk_id"] == cite["provenance"]["chunk_id"]
        assert cite["generation"] == cite["provenance"]["index_generation"]
        if key == case["required_field"] and case["expected"] in cite["quote"]:
            required = True
        if case["source"] == "xlsx":
            assert (
                cite["provenance"]["quality"]["formula_cache_status"]
                == "preserved_not_recalculated"
            )
    assert required, "No exact citation contains the predeclared answer-bearing field"
    return len(result["citations"])


def test_frozen_native_knowledge_gate(grounded_client):
    """Run four native formats, cross-file retrieval, absent fact and foreign refusal without tuning model output."""
    plan = json.loads(PLAN.read_text())
    client, auth = grounded_client
    headers, foreign_headers = auth["headers"]
    recorder = RecordingCore(client.app.state.grounded_service.inference)
    client.app.state.grounded_service.inference = recorder
    selected = (ROOT / "configs/embedding-selected.json").read_bytes()
    report = dict(
        description="Frozen same-agent synthetic D32 evaluation; actual approved embedding and CORE, no human-independent/general quality claim.",
        plan_sha256=hashlib.sha256(PLAN.read_bytes()).hexdigest(),
        sources={},
        cases=[],
        actual_core_calls=recorder.calls,
        complete=False,
    )
    save_report(report)
    for name, source in plan["sources"].items():
        identifier, job = publish(client, headers, source, "d32-" + name)
        report["sources"][name] = dict(
            file_id=identifier, sha256=source["sha256"], job=job
        )
        save_report(report)
    citations = 0
    for case in plan["answerable"]:
        identifier = report["sources"][case["source"]]["file_id"]
        options = dict(top_k=3)
        if case["scoped"]:
            options["file_ids"] = [identifier]
        retrieved = search(client, headers, case["query"], **options)
        assert identifier in {hit["file_id"] for hit in retrieved["hits"]}
        result = answer(client, headers, case["query"], **options)
        report["cases"].append(
            dict(case=case["id"], result=result, retrieval=retrieved)
        )
        save_report(report)
        citations += verify_native_citations(
            result,
            case,
            plan["sources"][case["source"]],
            identifier,
            auth["principals"][0],
        )
    result = answer(client, headers, plan["absent_query"])
    report["cases"].append(dict(case="absent", result=result))
    save_report(report)
    assert result["status"] == "insufficient_evidence"
    assert result["answer"] is None and result["citations"] == []
    foreign, job = publish(client, foreign_headers, plan["foreign"], "d32-foreign")
    report["foreign_source"] = dict(file_id=foreign, job=job)
    before = len(recorder.calls)
    result = answer(client, headers, plan["foreign_query"], file_ids=[foreign])
    report["cases"].append(dict(case="foreign", result=result))
    save_report(report)
    assert result["status"] == "no_sources" and result["answer"] is None
    assert result["citations"] == [] and len(recorder.calls) == before
    assert plan["foreign"]["text"].strip() not in json.dumps(result)
    assert len(recorder.calls) == 6
    assert all(
        c["profile"] == "core"
        and c["preset"] == "fast"
        and c["finish_reason"] == "stop"
        for c in recorder.calls
    )
    assert (ROOT / "configs/embedding-selected.json").read_bytes() == selected
    report.update(
        complete=True,
        answerable_passed=5,
        absent_passed=1,
        foreign_passed=1,
        relevant_exact_citations=citations,
        total_citations=citations,
        citation_precision=1.0,
        foreign_model_calls=0,
        selected_embedding_unchanged=True,
    )
    save_report(report)
    logger.info(
        "knowledge_gate_passed answerable=5 absent=1 foreign=1 citations=%d", citations
    )
