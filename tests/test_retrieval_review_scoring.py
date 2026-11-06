"""Verify independent golden paired metrics, explicit absent answers and strict review/ranking completeness."""

import copy
import math

import pytest

from scripts import retrieval_review_scoring as scoring
from scripts.retrieval_relevance_review import (
    build_packet,
    read_json,
    review_template,
)


@pytest.fixture
def inputs():
    """Create test-only judgments and rank arrays with known analytic metrics, never human evidence."""
    corpus = read_json(scoring.CORPUS)
    packet = build_packet(corpus)
    review = review_template(packet)
    plan = read_json(scoring.PLAN)
    review.update(
        reviewer="TEST FIXTURE ONLY",
        reviewed_at="2026-10-19T12:00:00+07:00",
        attestation="I independently reviewed every query and document without viewing model rankings or scores.",
    )
    for i, query in enumerate(review["queries"]):
        for row in query["documents"]:
            row.update(
                relevant=i < 4 and row["id"] == "doc-a",
                reason="Synthetic protocol fixture only.",
            )
    orders = {
        "baseline": [
            "doc-b",
            "doc-c",
            "doc-d",
            "doc-a",
            "doc-e",
            "doc-f",
            "doc-g",
            "doc-h",
        ],
        "candidate": [
            "doc-a",
            "doc-b",
            "doc-c",
            "doc-d",
            "doc-e",
            "doc-f",
            "doc-g",
            "doc-h",
        ],
    }
    observations = {
        kind: [
            dict(
                query_id=q["id"],
                ranking=[
                    dict(document_id=name, score=1 - index / 10)
                    for index, name in enumerate(order)
                ],
            )
            for q in corpus["queries"]
        ]
        for kind, order in orders.items()
    }
    return corpus, packet, review, plan, observations


def test_golden_rank4_to_rank1_and_absent_denominator(inputs):
    """Check exact binary rank metrics and exclude four absent answers rather than scoring them perfect."""
    report = scoring.score(*inputs)
    assert report["answerable_queries"] == 4 and report["absent_answer_queries"] == 4
    baseline = report["evaluated"]["baseline"]["metrics"]
    candidate = report["evaluated"]["candidate"]["metrics"]
    assert baseline == pytest.approx(
        dict(
            recall_at_3=0,
            recall_at_5=1,
            recall_at_10=1,
            mrr_at_10=0.25,
            ndcg_at_10=1 / math.log2(5),
        )
    )
    assert all(value == 1 for value in candidate.values())
    assert all(
        all(row[key] is None for key in scoring.METRICS)
        for row in report["evaluated"]["candidate"]["queries"]
        if not row["answerable"]
    )
    assert report["diagnostic_checks_met"] and not report["abstention_evaluated"]
    assert (
        not report["inference_proven_by_this_scorer"]
        and not report["adoption_approved"]
    )
    assert (
        report["descriptive_paired_query_bootstrap95"]
        == scoring.score(*inputs)["descriptive_paired_query_bootstrap95"]
    )


def test_golden_multi_relevant_and_missing_source():
    """Compare recall and ideal-normalized binary DCG against independent hand-computed ranks."""
    ranking = [dict(document_id=name) for name in ["x", "a", "y", "b"]]
    result = scoring.metrics_for(["a", "b"], ranking)
    assert result["recall_at_3"] == 0.5 and result["mrr_at_10"] == 0.5
    assert result["ndcg_at_10"] == pytest.approx(
        (1 / math.log2(3) + 1 / math.log2(5)) / (1 + 1 / math.log2(3))
    )
    missing = scoring.metrics_for(["a", "b"], ranking[:2])
    assert missing["recall_at_10"] == 0.5
    assert all(value == 0 for value in scoring.metrics_for(["a"], []).values())


def test_all_absent_is_not_quality_success(inputs):
    """Return null macro metrics and failed coverage rather than divide by zero or claim perfect retrieval."""
    for query in inputs[2]["queries"]:
        for row in query["documents"]:
            row["relevant"] = False
    report = scoring.score(*inputs)
    assert all(
        value is None for value in report["evaluated"]["baseline"]["metrics"].values()
    )
    assert report["answerable_queries"] == 0 and not report["diagnostic_checks_met"]
    assert all(
        value is None
        for value in report["descriptive_paired_query_bootstrap95"].values()
    )


def test_regression_and_no_absent_coverage_reported(inputs):
    """Retain a losing candidate and absent-coverage failures instead of changing frozen labels or gates."""
    observations = inputs[-1]
    observations["baseline"], observations["candidate"] = (
        observations["candidate"],
        observations["baseline"],
    )
    report = scoring.score(*inputs)
    assert (
        not report["diagnostic_checks_met"]
        and not report["diagnostic_checks"]["mrr_at_10_nonregression"]
    )
    for query in inputs[2]["queries"]:
        for row in query["documents"]:
            row["relevant"] = row["id"] == "doc-a"
    assert not scoring.score(*inputs)["diagnostic_checks"]["minimum_absent_coverage"]


@pytest.mark.parametrize(
    "fault",
    [
        "missing_query",
        "duplicate_query",
        "foreign_query",
        "missing_candidate",
        "duplicate_candidate",
        "foreign_document",
        "unsorted",
        "nan",
        "boolean",
        "extra",
        "candidate_range",
        "plan",
        "groups",
        "pending_review",
    ],
)
def test_invalid_pairing_or_judgment_rejected(inputs, fault):
    """Reject incomplete paired observations, post-freeze input drift and unfinished human judgment."""
    corpus, packet, review, plan, observations = inputs
    candidate = observations["candidate"]
    row = candidate[0]["ranking"][0]
    if fault == "missing_query":
        candidate.pop()
    elif fault == "duplicate_query":
        candidate[1] = copy.deepcopy(candidate[0])
    elif fault == "foreign_query":
        candidate[0]["query_id"] = "foreign"
    elif fault == "missing_candidate":
        candidate[0]["ranking"].pop()
    elif fault == "duplicate_candidate":
        candidate[0]["ranking"][1] = copy.deepcopy(row)
    elif fault == "foreign_document":
        row["document_id"] = "foreign"
    elif fault == "unsorted":
        candidate[0]["ranking"].reverse()
    elif fault == "nan":
        row["score"] = float("nan")
    elif fault == "boolean":
        row["score"] = True
    elif fault == "extra":
        row["text"] = "forged"
    elif fault == "candidate_range":
        row["score"] = -0.1
    elif fault == "plan":
        plan["packet_sha256"] = "changed"
    elif fault == "groups":
        plan["query_groups"].pop("review-q01")
    else:
        review["queries"][0]["documents"][0]["relevant"] = None
    with pytest.raises(ValueError):
        scoring.score(corpus, packet, review, plan, observations)


def test_pending_cli_never_writes_acceptance(tmp_path, monkeypatch):
    """Refuse generated pending review before accepting supplied rankings or creating any output evidence."""
    from scripts.retrieval_relevance_review import write_new

    corpus = read_json(scoring.CORPUS)
    packet = build_packet(corpus)
    pending = tmp_path / "pending.json"
    observed = tmp_path / "observed.json"
    output = tmp_path / "out.json"
    write_new(pending, review_template(packet))
    write_new(observed, dict(baseline=[], candidate=[]))

    def verified():
        """Bypass disk freeze verification to isolate CLI pending-review refusal."""
        return None

    monkeypatch.setattr(scoring, "verify_freeze", verified)
    assert (
        scoring.main(
            [
                "--review",
                str(pending),
                "--observations",
                str(observed),
                "--output",
                str(output),
            ]
        )
        == 1
    )
    assert not output.exists()
