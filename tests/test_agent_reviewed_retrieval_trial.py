"""Verify truthful delegated AI provenance, independent golden rank metrics and source-pair execution fences."""

import copy
from types import SimpleNamespace

import pytest

from scripts import agent_reviewed_retrieval_trial as agent
from scripts.retrieval_relevance_review import digest, read_json


@pytest.fixture
def inputs():
    """Read pre-inference AI diagnostic inputs without representing them as human-reviewed data."""
    corpus, review, plan = (
        read_json(path) for path in (agent.CORPUS, agent.REVIEW, agent.PLAN)
    )
    docs = [row["id"] for row in corpus["documents"]]
    observations = {
        kind: [
            dict(
                query_id=q["id"],
                ranking=[
                    dict(document_id=name, score=1 - index / 10)
                    for index, name in enumerate(docs)
                ],
            )
            for q in corpus["queries"]
        ]
        for kind in ("baseline", "candidate")
    }
    return corpus, review, plan, observations


def test_truthful_ai_provenance_and_absent_metrics(inputs):
    """Retain explicit AI authorship, separate the absent query and never emit human/adoption approval."""
    result = agent.score(*inputs)
    assert result["reviewer_type"] == "assistant" and result["human_reviewed"] is False
    assert result["answerable_queries"] == 7 and result["absent_answer_queries"] == 1
    absent = next(
        row
        for row in result["evaluated"]["candidate"]["queries"]
        if row["query_id"] == "review-q04"
    )
    assert all(absent[key] is None for key in agent.metrics.METRICS)
    assert not result["abstention_evaluated"] and not result["adoption_approved"]
    assert result["diagnostic_checks_met"]


@pytest.mark.parametrize(
    "fault",
    [
        "human",
        "provenance",
        "hash",
        "query",
        "pair",
        "duplicate",
        "label",
        "reason",
        "group",
        "candidate",
    ],
)
def test_invalid_review_or_observation_rejected(inputs, fault):
    """Reject falsely human provenance, incomplete AI review, input drift and changed candidate pools."""
    corpus, review, plan, observations = inputs
    if fault == "human":
        review["human_reviewed"] = True
    elif fault == "provenance":
        review["review_provenance"] = "human_independent"
    elif fault == "hash":
        review["corpus_sha256"] = "changed"
    elif fault == "query":
        review["queries"][1] = copy.deepcopy(review["queries"][0])
    elif fault == "pair":
        review["queries"][0]["documents"].pop()
    elif fault == "duplicate":
        review["queries"][0]["documents"][1] = copy.deepcopy(
            review["queries"][0]["documents"][0]
        )
    elif fault == "label":
        review["queries"][0]["documents"][0]["relevant"] = 1
    elif fault == "reason":
        review["queries"][0]["documents"][0]["reason"] = " "
    elif fault == "group":
        plan["query_groups"].pop("review-q01")
    else:
        observations["candidate"][0]["ranking"].pop()
    if fault not in {"hash", "candidate"}:
        plan["review_sha256"] = digest(review)
    with pytest.raises(ValueError):
        agent.score(corpus, review, plan, observations)


def test_v1_coverage_failure_is_retained_before_inference():
    """Keep the original ambiguous absent-case finding instead of relabeling a negative answer as irrelevant."""
    old = read_json(agent.ROOT / "docs/evidence/d27-t03-agent-review-v1.json")
    assert old["pre_execution_coverage"]["minimum_absent_gate_met"] is False
    assert not old["pre_execution_coverage"]["model_inference_executed"]
    q = next(row for row in old["queries"] if row["id"] == "review-q04")
    assert [row["id"] for row in q["documents"] if row["relevant"]] == ["doc-d"]


@pytest.mark.parametrize("fault", [None, "generation", "failure"])
def test_three_round_execution_and_routing_restore(inputs, monkeypatch, fault):
    """Verify exact point/generation consistency and final restoration using explicit stub transport only."""
    corpus, review, plan, _ = inputs

    def verified():
        """Bypass only disk freeze checks for a synthetic workflow fault test."""
        return None

    monkeypatch.setattr(agent, "verify_freeze", verified)
    trial = SimpleNamespace(dense=object(), reranker=object(), observations=[])
    client = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(retrieval_service=trial))
    )
    calls = []

    def upload(client, headers, doc):
        """Return synthetic source bindings without writing actual vectors or files."""
        return dict(
            document_id=doc["id"],
            file_id="file-" + doc["id"],
            source_sha256="hash-" + doc["id"],
        )

    def observe(client, headers, query, bindings, *, candidate):
        """Return explicit synthetic ranks with optional candidate-generation or transport faults."""
        assert client.app.state.retrieval_service is (
            trial if candidate else trial.dense
        )
        if candidate and fault == "failure":
            raise ValueError("controlled_failure")
        calls.append(candidate)
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

    monkeypatch.setattr(agent, "upload_source", upload)
    monkeypatch.setattr(agent, "observe", observe)
    if fault:
        with pytest.raises(ValueError):
            agent.run(client, {})
    else:
        result = agent.run(client, {})
        assert (
            len(result["runs"]) == 3 and len(calls) == 48 and result["rankings_stable"]
        )
        assert result["all_diagnostic_checks_met"] and result["human_reviewed"] is False
    assert client.app.state.retrieval_service is trial
