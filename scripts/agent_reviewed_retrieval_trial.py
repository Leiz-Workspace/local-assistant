"""Evaluate owner-delegated AI relevance judgments through isolated paired source/HTTP trials with honest provenance."""

import hashlib
import logging

from scripts import retrieval_review_scoring as metrics
from scripts.human_reviewed_retrieval_trial import observe, upload_source
from scripts.qwen_reranker_trial_worker import verify_freeze as verify_http
from scripts.retrieval_relevance_review import digest, read_json, require

logger = logging.getLogger(__name__)
ROOT = metrics.ROOT
CORPUS = ROOT / "tests/fixtures/retrieval/d27-review-challenge-v2.json"
REVIEW = ROOT / "docs/evidence/d27-t03-agent-review-v2.json"
PLAN = ROOT / "docs/evidence/d27-t03-agent-paired-plan.json"
FREEZE = ROOT / "docs/evidence/d27-t03-agent-execution-freeze.json"


def verify_freeze():
    """Verify exact new AI-review policy, pre-inference judgments, plan and implementation plus inherited runtime."""
    metrics.verify_freeze()
    verify_http()
    manifest = read_json(FREEZE)
    expected = {
        "scripts/agent_reviewed_retrieval_trial.py",
        "tests/test_agent_reviewed_retrieval_trial.py",
        "tests/integration/test_agent_reviewed_trial.py",
        "tests/fixtures/retrieval/d27-review-challenge-v2.json",
        "docs/evidence/d27-t03-agent-review-v1.json",
        "docs/evidence/d27-t03-agent-review-v2.json",
        "docs/evidence/d27-t03-agent-paired-plan.json",
        "docs/ADR/042-owner-delegated-relevance-evaluation.md",
    }
    require(
        set(manifest["sha256"]) == expected
        and manifest["scope"] == "OWNER_DELEGATED_AI_REVIEW_NO_HUMAN_OR_ADOPTION_CLAIM",
        "agent_freeze_invalid",
    )
    for name, expected_hash in manifest["sha256"].items():
        require(
            hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected_hash,
            "agent_freeze_changed",
        )
    logger.info("agent_review_execution_freeze_verified")


def judgments(corpus, review, plan):
    """Validate complete AI-labeled pairs and exact provenance without manufacturing a human attestation."""
    require(
        review["reviewer_type"] == plan["reviewer_type"] == "assistant"
        and review["human_reviewed"] is False
        and plan["human_reviewed"] is False
        and review["review_provenance"] == "same_agent_authored_and_reviewed",
        "agent_review_provenance_invalid",
    )
    require(
        review["owner_delegation"]
        and review["corpus_sha256"] == plan["corpus_sha256"] == digest(corpus)
        and plan["review_sha256"] == digest(review),
        "agent_review_input_changed",
    )
    expected = {row["id"] for row in corpus["queries"]}
    docs = {row["id"] for row in corpus["documents"]}
    rows = review["queries"]
    require(
        isinstance(rows, list)
        and len(rows) == len(expected)
        and all(
            isinstance(row, dict)
            and set(row) == {"id", "documents"}
            and isinstance(row["id"], str)
            for row in rows
        ),
        "agent_review_queries_invalid",
    )
    require(
        len({row["id"] for row in rows}) == len(rows)
        and {row["id"] for row in rows} == expected
        and set(plan["query_groups"]) == expected,
        "agent_review_query_identity_invalid",
    )
    labels = {}
    for query in rows:
        pairs = query["documents"]
        require(
            isinstance(pairs, list)
            and len(pairs) == len(docs)
            and all(
                isinstance(row, dict)
                and set(row) == {"id", "relevant", "reason"}
                and isinstance(row["id"], str)
                and type(row["relevant"]) is bool
                and isinstance(row["reason"], str)
                and row["reason"].strip()
                for row in pairs
            ),
            "agent_review_pairs_invalid",
        )
        require(
            len({row["id"] for row in pairs}) == len(docs)
            and {row["id"] for row in pairs} == docs,
            "agent_review_pair_identity_invalid",
        )
        labels[query["id"]] = [row["id"] for row in pairs if row["relevant"]]
    logger.info("agent_review_judgments_verified queries=%d", len(labels))
    return labels


def score(corpus, review, plan, observations):
    """Score AI-reviewed paired ranks with separate absent support metrics and predeclared diagnostic gates."""
    labels = judgments(corpus, review, plan)
    indexed = metrics.validate_observations(corpus, observations)
    evaluated = {}
    for kind in ("baseline", "candidate"):
        rows = [
            dict(
                query_id=q["id"],
                group=plan["query_groups"][q["id"]],
                answerable=bool(labels[q["id"]]),
                **metrics.metrics_for(labels[q["id"]], indexed[kind][q["id"]]),
            )
            for q in corpus["queries"]
        ]
        evaluated[kind] = dict(
            metrics=metrics.mean_metrics(rows),
            groups={
                group: metrics.mean_metrics(
                    [row for row in rows if row["group"] == group]
                )
                for group in sorted(set(plan["query_groups"].values()))
            },
            queries=rows,
        )
    answerable = sum(bool(row) for row in labels.values())
    checks = dict(
        minimum_answerable_coverage=answerable >= plan["minimum_answerable_queries"],
        minimum_absent_coverage=len(labels) - answerable
        >= plan["minimum_absent_queries"],
    )
    for key in metrics.METRICS:
        old, new = (
            evaluated["baseline"]["metrics"][key],
            evaluated["candidate"]["metrics"][key],
        )
        checks[key + "_nonregression"] = (
            old is not None and new is not None and new + 1e-12 >= old
        )
    for group, old in evaluated["baseline"]["groups"].items():
        new = evaluated["candidate"]["groups"][group]
        checks[group + "_recall_at_3_nonregression"] = (
            old["recall_at_3"] is not None
            and new["recall_at_3"] is not None
            and new["recall_at_3"] + plan["max_group_recall_at_3_loss"] + 1e-12
            >= old["recall_at_3"]
        )
    changes = [
        {key: new[key] - old[key] for key in metrics.METRICS}
        for old, new in zip(
            evaluated["baseline"]["queries"],
            evaluated["candidate"]["queries"],
            strict=True,
        )
        if old["answerable"]
    ]
    logger.info(
        "agent_review_paired_ranks_scored answerable=%d absent=%d gates_met=%s",
        answerable,
        len(labels) - answerable,
        all(checks.values()),
    )
    return dict(
        description="Additional same-agent-authored/AI-reviewed diagnostic under explicit owner delegation; no independent-human, population-quality or adoption claim.",
        reviewer_type="assistant",
        human_reviewed=False,
        answerable_queries=answerable,
        absent_answer_queries=len(labels) - answerable,
        abstention_evaluated=False,
        evaluated=evaluated,
        diagnostic_checks=checks,
        diagnostic_checks_met=all(checks.values()),
        descriptive_paired_query_bootstrap95=metrics.paired_intervals(
            changes, plan["bootstrap"]
        ),
        review_sha256=digest(review),
        observations_sha256=digest(observations),
        adoption_approved=False,
    )


def run(client, headers):
    """Run three actual paired repetitions on frozen AI-reviewed sources and always restore isolated routing."""
    verify_freeze()
    corpus, review, plan = (read_json(path) for path in (CORPUS, REVIEW, PLAN))
    labels = judgments(corpus, review, plan)
    require(
        sum(bool(row) for row in labels.values()) >= plan["minimum_answerable_queries"]
        and sum(not row for row in labels.values()) >= plan["minimum_absent_queries"],
        "agent_review_pre_execution_coverage_failed",
    )
    trial = client.app.state.retrieval_service
    require(
        hasattr(trial, "dense") and hasattr(trial, "reranker"),
        "agent_trial_isolated_service_required",
    )
    bindings = [upload_source(client, headers, row) for row in corpus["documents"]]
    runs, raw_runs = [], []
    reference_points = None
    try:
        for repetition in range(3):
            paired, timing = (
                dict(baseline=[], candidate=[]),
                dict(baseline=[], candidate=[]),
            )
            for query in corpus["queries"]:
                client.app.state.retrieval_service = trial.dense
                old, old_time = observe(
                    client, headers, query, bindings, candidate=False
                )
                client.app.state.retrieval_service = trial
                new, new_time = observe(
                    client, headers, query, bindings, candidate=True
                )
                old_points = {
                    row["document_id"]: row for row in old_time["source_points"]
                }
                new_points = {
                    row["document_id"]: row for row in new_time["source_points"]
                }
                require(old_points == new_points, "agent_trial_paired_source_changed")
                if reference_points is None:
                    reference_points = old_points
                require(
                    old_points == reference_points,
                    "agent_trial_source_changed_between_queries",
                )
                paired["baseline"].append(old)
                paired["candidate"].append(new)
                timing["baseline"].append(old_time)
                timing["candidate"].append(new_time)
            runs.append(score(corpus, review, plan, paired))
            raw_runs.append(dict(observations=paired, actual_http=timing))
            logger.info("agent_review_paired_round_completed round=%d", repetition + 1)
    finally:
        client.app.state.retrieval_service = trial
    orders = [
        [
            [row["document_id"] for row in query["ranking"]]
            for query in item["observations"]["candidate"]
        ]
        for item in raw_runs
    ]
    stable = all(order == orders[0] for order in orders)
    return dict(
        description="Actual three-round isolated ASGI source/model execution using owner-delegated same-agent AI judgments, not human-independent or production quality.",
        status="PAIRED_EXECUTION_COMPLETE",
        inference_executed=True,
        reviewer_type="assistant",
        human_reviewed=False,
        corpus_sha256=digest(corpus),
        review_sha256=digest(review),
        plan_sha256=digest(plan),
        source_bindings=bindings,
        runs=runs,
        raw_runs=raw_runs,
        worker_observations=list(trial.observations),
        rankings_stable=stable,
        all_diagnostic_checks_met=stable
        and all(row["diagnostic_checks_met"] for row in runs),
        adoption_approved=False,
        production_routing_changed=False,
    )
