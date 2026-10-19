"""Score frozen human-reviewed paired rankings with explicit absent-answer and small-sample boundaries."""

import argparse
import hashlib
import logging
import math
from pathlib import Path

import numpy as np

from scripts.retrieval_relevance_review import (
    digest,
    read_json,
    require,
    validate_review,
    write_new,
)

logger = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "tests/fixtures/retrieval/d27-review-challenge.json"
PACKET = ROOT / "docs/evidence/d27-t03-review-packet.json"
PLAN = ROOT / "docs/evidence/d27-t03-paired-review-plan.json"
FREEZE = ROOT / "docs/evidence/d27-t03-paired-scoring-freeze.json"
METRICS = ("recall_at_3", "recall_at_5", "recall_at_10", "mrr_at_10", "ndcg_at_10")


def verify_freeze():
    """Bind exact challenge, packet, plan and scoring/tool tests before interpreting any supplied rankings."""
    manifest = read_json(FREEZE)
    expected = {
        "scripts/retrieval_review_scoring.py",
        "tests/test_retrieval_review_scoring.py",
        "docs/evidence/d27-t03-paired-review-plan.json",
        "tests/fixtures/retrieval/d27-review-challenge.json",
        "docs/evidence/d27-t03-review-packet.json",
        "scripts/human_reviewed_retrieval_trial.py",
        "tests/test_human_reviewed_retrieval_trial.py",
        "tests/integration/test_human_reviewed_trial_gate.py",
    }
    require(set(manifest["sha256"]) == expected, "paired_freeze_shape_invalid")
    for name, sha in manifest["sha256"].items():
        require(
            hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == sha,
            "paired_freeze_changed",
        )
    logger.info("paired_review_scoring_freeze_verified")


def validate_observations(corpus, observations):
    """Require complete known queries and identical unique candidate sets across both finite sorted rankings."""
    require(
        isinstance(observations, dict)
        and set(observations) == {"baseline", "candidate"},
        "paired_observation_shape_invalid",
    )
    expected = {row["id"] for row in corpus["queries"]}
    documents = {row["id"] for row in corpus["documents"]}
    indexed = {}
    for kind in ("baseline", "candidate"):
        rows = observations[kind]
        require(
            isinstance(rows, list) and len(rows) == len(expected),
            "paired_queries_incomplete",
        )
        require(
            all(
                isinstance(row, dict)
                and set(row) == {"query_id", "ranking"}
                and isinstance(row["query_id"], str)
                for row in rows
            ),
            "paired_query_invalid",
        )
        indexed[kind] = {row["query_id"]: row["ranking"] for row in rows}
        require(
            len(indexed[kind]) == len(rows) and set(indexed[kind]) == expected,
            "paired_query_identity_invalid",
        )
        for ranking in indexed[kind].values():
            require(
                isinstance(ranking, list) and len(ranking) <= 10,
                "paired_ranking_invalid",
            )
            seen, previous = set(), float("inf")
            for row in ranking:
                require(
                    isinstance(row, dict)
                    and set(row) == {"document_id", "score"}
                    and isinstance(row["document_id"], str),
                    "paired_document_invalid",
                )
                identifier, value = row["document_id"], row["score"]
                require(
                    identifier in documents
                    and identifier not in seen
                    and type(value) in (int, float)
                    and math.isfinite(value)
                    and (-1 if kind == "baseline" else 0) <= value <= 1
                    and value <= previous,
                    "paired_document_or_score_invalid",
                )
                seen.add(identifier)
                previous = value
    for query_id in expected:
        require(
            {row["document_id"] for row in indexed["baseline"][query_id]}
            == {row["document_id"] for row in indexed["candidate"][query_id]},
            "paired_candidate_set_changed",
        )
    logger.info("paired_observations_verified queries=%d", len(expected))
    return indexed


def metrics_for(relevant, ranking):
    """Compute binary support retrieval metrics only when at least one human-relevant source exists."""
    if not relevant:
        return {key: None for key in METRICS}
    ranks = {row["document_id"]: index for index, row in enumerate(ranking, 1)}
    found = [ranks[name] for name in relevant if name in ranks]
    ideal = sum(
        1 / math.log2(index + 1) for index in range(1, min(10, len(relevant)) + 1)
    )
    result = {
        f"recall_at_{k}": sum(rank <= k for rank in found) / len(relevant)
        for k in (3, 5, 10)
    }
    result.update(
        mrr_at_10=1 / min(found) if found else 0,
        ndcg_at_10=sum(1 / math.log2(rank + 1) for rank in found) / ideal,
    )
    return result


def mean_metrics(rows):
    """Average answerable queries only and retain null rather than perfect zero-denominator metrics."""
    usable = [row for row in rows if row["answerable"]]
    return {
        key: sum(row[key] for row in usable) / len(usable) if usable else None
        for key in METRICS
    }


def paired_intervals(deltas, settings):
    """Compute predeclared descriptive query-bootstrap intervals without implying independent population evidence."""
    if not deltas:
        return {key: None for key in METRICS}
    values = np.array([[row[key] for key in METRICS] for row in deltas], dtype=float)
    samples = np.random.default_rng(settings["seed"]).integers(
        0, len(deltas), size=(settings["resamples"], len(deltas))
    )
    limits = np.percentile(values[samples].mean(axis=1), [2.5, 97.5], axis=0)
    return {
        key: [float(limits[0, index]), float(limits[1, index])]
        for index, key in enumerate(METRICS)
    }


def score(corpus, packet, review, plan, observations):
    """Compare supplied paired ranks against actual supplied review without claiming inference or adoption."""
    reviewed = validate_review(corpus, packet, review)
    require(
        plan["corpus_sha256"] == digest(corpus)
        and plan["packet_sha256"] == digest(packet),
        "paired_plan_input_changed",
    )
    require(
        set(plan["query_groups"]) == {row["id"] for row in corpus["queries"]},
        "paired_plan_groups_invalid",
    )
    indexed = validate_observations(corpus, observations)
    evaluated = {}
    for kind in ("baseline", "candidate"):
        rows = []
        for query in reviewed["queries"]:
            rows.append(
                dict(
                    query_id=query["id"],
                    group=plan["query_groups"][query["id"]],
                    answerable=bool(query["relevant"]),
                    relevant_count=len(query["relevant"]),
                    candidate_count=len(indexed[kind][query["id"]]),
                    **metrics_for(query["relevant"], indexed[kind][query["id"]]),
                )
            )
        groups = {
            group: mean_metrics([row for row in rows if row["group"] == group])
            for group in sorted(set(plan["query_groups"].values()))
        }
        evaluated[kind] = dict(metrics=mean_metrics(rows), groups=groups, queries=rows)
    answerable = sum(bool(row["relevant"]) for row in reviewed["queries"])
    absent = len(reviewed["queries"]) - answerable
    changes = [
        {key: new[key] - old[key] for key in METRICS}
        for old, new in zip(
            evaluated["baseline"]["queries"],
            evaluated["candidate"]["queries"],
            strict=True,
        )
        if old["answerable"]
    ]
    gates = dict(
        minimum_answerable_coverage=answerable >= plan["minimum_answerable_queries"],
        minimum_absent_coverage=absent >= plan["minimum_absent_queries"],
    )
    for key in METRICS:
        old, new = (
            evaluated["baseline"]["metrics"][key],
            evaluated["candidate"]["metrics"][key],
        )
        gates[key + "_nonregression"] = (
            old is not None and new is not None and new + 1e-12 >= old
        )
    for group, old in evaluated["baseline"]["groups"].items():
        new = evaluated["candidate"]["groups"][group]
        gates[group + "_recall_at_3_nonregression"] = (
            old["recall_at_3"] is not None
            and new["recall_at_3"] is not None
            and new["recall_at_3"] + plan["max_group_recall_at_3_loss"] + 1e-12
            >= old["recall_at_3"]
        )
    logger.info(
        "paired_review_rankings_scored answerable=%d absent=%d diagnostic_gates_met=%s",
        answerable,
        absent,
        all(gates.values()),
    )
    return dict(
        description="Scores of supplied rank observations against structurally validated supplied human review; observation provenance and reviewer independence require separate execution evidence. Small additional diagnostic, not general quality or adoption approval.",
        corpus_sha256=digest(corpus),
        packet_sha256=digest(packet),
        review_sha256=digest(review),
        plan_sha256=digest(plan),
        observations_sha256=digest(observations),
        answerable_queries=answerable,
        absent_answer_queries=absent,
        abstention_evaluated=False,
        absent_metric_policy="Null support-retrieval metrics; absent answers excluded from answerable macro means. No score threshold or abstention confidence is inferred.",
        evaluated=evaluated,
        diagnostic_checks=gates,
        diagnostic_checks_met=all(gates.values()),
        descriptive_paired_query_bootstrap95=paired_intervals(
            changes, plan["bootstrap"]
        ),
        inference_proven_by_this_scorer=False,
        production_quality_certified=False,
        adoption_approved=False,
    )


def main(argv=None):
    """Validate an actual supplied review and complete frozen paired ranks before exclusive audited output."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--review", required=True)
    parser.add_argument("--observations", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        verify_freeze()
        result = score(
            read_json(CORPUS),
            read_json(PACKET),
            read_json(args.review),
            read_json(PLAN),
            read_json(args.observations),
        )
        write_new(args.output, result)
    except (ValueError, OSError, KeyError, TypeError):
        logger.warning("paired_review_scoring_failed_safely")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
