"""Verify that supplied review gates all model/source access and binds real HTTP observations to frozen sources."""

import json
from types import SimpleNamespace

import pytest

from scripts import human_reviewed_retrieval_trial as human
from scripts.retrieval_relevance_review import build_packet, read_json, review_template


def verified():
    """Bypass only frozen-file access for deterministic input-gate unit tests."""
    return None


def pending_response(tmp_path):
    """Create an explicitly pending test response with no actual human relevance labels."""
    corpus = read_json(human.scoring.CORPUS)
    path = tmp_path / "review.json"
    path.write_text(json.dumps(review_template(build_packet(corpus))))
    return path


def test_pending_review_never_touches_client_or_model(tmp_path, monkeypatch):
    """Refuse all source/model work while user labels remain incomplete."""
    monkeypatch.setattr(human.scoring, "verify_freeze", verified)
    result = human.run(object(), {}, review_path=pending_response(tmp_path))
    assert result == dict(
        status="PENDING_HUMAN_REVIEW", inference_executed=False, completed_pairs=0
    )
    assert human.prepare(tmp_path / "missing.json")["status"] == "PENDING_HUMAN_REVIEW"


def test_full_labels_without_attestation_are_rejected(tmp_path, monkeypatch):
    """Never infer reviewer metadata or independence from completed booleans alone."""
    monkeypatch.setattr(human.scoring, "verify_freeze", verified)
    path = pending_response(tmp_path)
    r = json.loads(path.read_text())
    for query in r["queries"]:
        for row in query["documents"]:
            row.update(relevant=False, reason="TEST ONLY")
    path.write_text(json.dumps(r))
    with pytest.raises(ValueError):
        human.prepare(path)


@pytest.mark.parametrize("fault", ["hash", "missing", "ranking", "status"])
def test_observation_requires_complete_source_binding(fault):
    """Refuse forged source identity, incomplete pool or missing ranking activation on returned HTTP data."""
    row = dict(
        file_id="file-a",
        point_id="point-a",
        source_sha256="sha-a",
        generation=1,
        score=0.7,
        reranker_score=0.9,
    )
    data = dict(hits=[row], ranking="evaluation_only_qwen_batch4")
    status = 200
    if fault == "hash":
        row["source_sha256"] = "changed"
    elif fault == "missing":
        data["hits"] = []
    elif fault == "ranking":
        data["ranking"] = "dense"
    else:
        status = 503

    class Client:
        """Return only an injected HTTP observation for source-binding failure tests."""

        def post(self, *args, **kwargs):
            """Expose a protocol response without using any actual source or model."""

            def response_body():
                """Return the fixed synthetic protocol payload without any inference."""
                return data

            return SimpleNamespace(
                status_code=status,
                headers={"cache-control": "private, no-store"},
                json=response_body,
                content=b"TEST ONLY",
            )

    with pytest.raises(ValueError):
        human.observe(
            Client(),
            {},
            dict(id="q", text="query"),
            [dict(document_id="doc-a", file_id="file-a", source_sha256="sha-a")],
            candidate=True,
        )


def test_observation_preserves_own_point_identity():
    """Translate source-verified file IDs to corpus IDs without treating scores as calibrated confidence."""
    data = dict(
        hits=[
            dict(
                file_id="file-a",
                point_id="point-a",
                source_sha256="sha-a",
                generation=1,
                score=0.7,
                reranker_score=0.9,
            )
        ],
        ranking="evaluation_only_qwen_batch4",
    )

    class Client:
        """Provide a complete explicit synthetic source-binding response."""

        def post(self, *args, **kwargs):
            """Require caller scope narrowing to the exact owned candidate source set."""
            assert kwargs["json"]["file_ids"] == ["file-a"]

            def response_body():
                """Return the fixed synthetic protocol payload without any inference."""
                return data

            return SimpleNamespace(
                status_code=200,
                headers={"cache-control": "private, no-store"},
                json=response_body,
                content=b"TEST ONLY",
            )

    row, evidence = human.observe(
        Client(),
        {},
        dict(id="q", text="query"),
        [dict(document_id="doc-a", file_id="file-a", source_sha256="sha-a")],
        candidate=True,
    )
    assert row == dict(query_id="q", ranking=[dict(document_id="doc-a", score=0.9)])
    assert evidence["source_points"][0]["point_id"] == "point-a"


@pytest.fixture
def ready_review(tmp_path, monkeypatch):
    """Create test-only complete review metadata and labels exclusively in the pytest private directory."""
    monkeypatch.setattr(human.scoring, "verify_freeze", verified)
    path = pending_response(tmp_path)
    review = json.loads(path.read_text())
    review.update(
        reviewer="TEST FIXTURE ONLY",
        reviewed_at="2026-10-19T12:00:00+07:00",
        attestation="I independently reviewed every query and document without viewing model rankings or scores.",
    )
    for index, query in enumerate(review["queries"]):
        for row in query["documents"]:
            row.update(
                relevant=index < 4 and row["id"] == "doc-a",
                reason="Synthetic protocol fixture only.",
            )
    path.write_text(json.dumps(review))
    return path


def test_ready_review_and_coverage_requirements(ready_review):
    """Require completed review and predeclared answerable/absent coverage before any client work."""
    result = human.prepare(ready_review)
    assert (
        result["status"] == "REVIEW_READY_EXECUTION_PENDING"
        and not result["inference_executed"]
    )
    review = json.loads(ready_review.read_text())
    for query in review["queries"]:
        for row in query["documents"]:
            row["relevant"] = False
    ready_review.write_text(json.dumps(review))
    with pytest.raises(ValueError, match="coverage_requires_adjudication"):
        human.prepare(ready_review)


@pytest.mark.parametrize("fault", [None, "failure", "generation"])
def test_three_round_trial_protocol_and_routing_restore(
    ready_review, tmp_path, monkeypatch, fault
):
    """Verify workflow and exact point/generation pairing with stub transports, never real quality claims."""
    from scripts import qwen_reranker_trial_worker as worker

    monkeypatch.setattr(worker, "verify_freeze", verified)
    trial = SimpleNamespace(dense=object(), reranker=object())
    client = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(retrieval_service=trial))
    )
    calls = []

    def upload(client, headers, document):
        """Return explicit synthetic source bindings without touching storage or inference."""
        return dict(
            document_id=document["id"],
            file_id="file-" + document["id"],
            source_sha256="test-sha-" + document["id"],
        )

    def observe(client, headers, query, bindings, *, candidate):
        """Expose deterministic stub ranks and optional post-baseline generation/failure faults."""
        assert client.app.state.retrieval_service is (
            trial if candidate else trial.dense
        )
        calls.append(candidate)
        if candidate and fault == "failure":
            raise ValueError("controlled_failure")
        ranking = [
            dict(document_id=row["document_id"], score=1 - index / 10)
            for index, row in enumerate(bindings)
        ]
        points = [
            dict(
                row,
                point_id="point-" + row["document_id"],
                generation=2 if candidate and fault == "generation" else 1,
            )
            for row in bindings
        ]
        return dict(query_id=query["id"], ranking=ranking), dict(source_points=points)

    monkeypatch.setattr(human, "upload_source", upload)
    monkeypatch.setattr(human, "observe", observe)
    if fault:
        with pytest.raises(ValueError):
            human.run(client, {}, review_path=ready_review, output_directory=tmp_path)
    else:
        result = human.run(
            client, {}, review_path=ready_review, output_directory=tmp_path
        )
        assert (
            result["status"] == "PAIRED_EXECUTION_COMPLETE" and len(result["runs"]) == 3
        )
        assert (
            len(calls) == 48
            and result["rankings_stable"]
            and result["all_diagnostic_checks_met"]
        )
        assert result["adoption_approved"] is False
    assert client.app.state.retrieval_service is trial
