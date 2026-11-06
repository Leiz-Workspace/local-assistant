"""Run isolated paired source/HTTP evaluation only after a complete independently supplied relevance review."""

import hashlib
import logging
import time
from pathlib import Path

from scripts import retrieval_review_scoring as scoring
from scripts.retrieval_relevance_review import (
    digest,
    read_json,
    require,
    validate_review,
    write_new,
)

logger = logging.getLogger(__name__)
DEFAULT_REVIEW = scoring.ROOT / "data/backups/d27-t03-human-review.json"


def prepare(review_path=DEFAULT_REVIEW):
    """Refuse absent, incomplete or invalid review before touching a client, source store or model."""
    scoring.verify_freeze()
    corpus, packet, plan = (
        read_json(path) for path in (scoring.CORPUS, scoring.PACKET, scoring.PLAN)
    )
    path = Path(review_path)
    if not path.exists():
        logger.info("human_trial_waiting_review completed_pairs=0")
        return dict(
            status="PENDING_HUMAN_REVIEW", inference_executed=False, completed_pairs=0
        )
    review = read_json(path)
    complete = sum(
        type(row.get("relevant")) is bool
        for query in review.get("queries", [])
        for row in query.get("documents", [])
    )
    if complete != 64:
        logger.info("human_trial_waiting_review completed_pairs=%d", complete)
        return dict(
            status="PENDING_HUMAN_REVIEW",
            inference_executed=False,
            completed_pairs=complete,
        )
    verified = validate_review(corpus, packet, review)
    answerable = sum(bool(row["relevant"]) for row in verified["queries"])
    require(
        answerable >= plan["minimum_answerable_queries"]
        and len(verified["queries"]) - answerable >= plan["minimum_absent_queries"],
        "human_review_coverage_requires_adjudication",
    )
    require(
        plan["corpus_sha256"] == digest(corpus)
        and plan["packet_sha256"] == digest(packet),
        "human_trial_plan_changed",
    )
    logger.info(
        "human_trial_review_ready answerable=%d absent=%d",
        answerable,
        len(verified["queries"]) - answerable,
    )
    return dict(
        status="REVIEW_READY_EXECUTION_PENDING",
        inference_executed=False,
        completed_pairs=complete,
        corpus=corpus,
        packet=packet,
        plan=plan,
        review=review,
    )


def upload_source(client, headers, document):
    """Admit one exact frozen source through the existing authenticated immutable upload/index HTTP path."""
    raw = document["text"].encode()
    require(0 < len(raw) <= 256, "human_trial_source_chunk_policy_invalid")
    sha = hashlib.sha256(raw).hexdigest()
    response = client.post(
        "/api/v1/files",
        headers=headers,
        json=dict(
            filename="review.txt",
            size_bytes=len(raw),
            sha256=sha,
            request_key="d27-human-" + document["id"],
        ),
    )
    require(response.status_code == 201, "human_trial_reservation_failed")
    file_id = response.json()["id"]
    require(
        client.put(
            f"/api/v1/files/{file_id}/content", headers=headers, content=raw
        ).status_code
        == 200,
        "human_trial_upload_failed",
    )
    response = client.post(f"/api/v1/files/{file_id}/index", headers=headers)
    require(response.status_code == 202, "human_trial_index_failed")
    job_id = response.json()["id"]
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        state = client.get("/api/v1/ingestion/" + job_id, headers=headers)
        require(state.status_code == 200, "human_trial_status_failed")
        row = state.json()
        if row["status"] == "ready" and row["active"]:
            logger.info("human_trial_source_ready")
            return dict(document_id=document["id"], file_id=file_id, source_sha256=sha)
        require(
            row["status"] not in {"failed", "rejected", "superseded", "deleted"},
            "human_trial_index_terminal",
        )
        time.sleep(0.05)
    raise ValueError("human_trial_index_timeout")


def observe(client, headers, query, bindings, *, candidate):
    """Bind every returned point to exactly one frozen whole-source hash and retain actual response timing."""
    indexed = {row["file_id"]: row for row in bindings}
    started = time.monotonic()
    response = client.post(
        "/api/v1/retrieval/search",
        headers=headers,
        json=dict(query=query["text"], top_k=10, file_ids=list(indexed)),
    )
    seconds = time.monotonic() - started
    require(
        response.status_code == 200
        and response.headers.get("cache-control") == "private, no-store",
        "human_trial_search_failed",
    )
    data = response.json()
    require(
        len(data["hits"]) == len(bindings)
        and {row["file_id"] for row in data["hits"]} == set(indexed),
        "human_trial_candidate_pool_incomplete",
    )
    if candidate:
        require(
            data.get("ranking") == "evaluation_only_qwen_batch4",
            "human_trial_ranking_not_applied",
        )
    ranking, points = [], []
    for row in data["hits"]:
        binding = indexed[row["file_id"]]
        require(
            row["source_sha256"] == binding["source_sha256"],
            "human_trial_returned_source_changed",
        )
        ranking.append(
            dict(
                document_id=binding["document_id"],
                score=row["reranker_score"] if candidate else row["score"],
            )
        )
        points.append(
            dict(
                document_id=binding["document_id"],
                point_id=row["point_id"],
                file_id=row["file_id"],
                source_sha256=row["source_sha256"],
                generation=row["generation"],
            )
        )
    return dict(query_id=query["id"], ranking=ranking), dict(
        query_id=query["id"],
        seconds=seconds,
        source_points=points,
        response_sha256=hashlib.sha256(response.content).hexdigest(),
    )


def run(client, headers, *, review_path=DEFAULT_REVIEW, output_directory=None):
    """Run three actual paired repetitions in an explicitly owned test client and always restore its routing."""
    prepared = prepare(review_path)
    if prepared["status"] != "REVIEW_READY_EXECUTION_PENDING":
        return prepared
    from scripts.qwen_reranker_trial_worker import verify_freeze as verify_trial

    verify_trial()
    trial = client.app.state.retrieval_service
    require(
        hasattr(trial, "dense") and hasattr(trial, "reranker"),
        "human_trial_isolated_composition_required",
    )
    output_directory = Path(output_directory or scoring.ROOT / "data/backups")
    snapshot = output_directory / (
        "d27-human-review-" + digest(prepared["review"]) + ".json"
    )
    if snapshot.exists():
        require(
            read_json(snapshot) == prepared["review"],
            "human_trial_review_snapshot_changed",
        )
    else:
        write_new(snapshot, prepared["review"])
    bindings = [
        upload_source(client, headers, row) for row in prepared["corpus"]["documents"]
    ]
    runs, raw_runs = [], []
    try:
        for repetition in range(3):
            paired, timing = (
                dict(baseline=[], candidate=[]),
                dict(baseline=[], candidate=[]),
            )
            for query in prepared["corpus"]["queries"]:
                client.app.state.retrieval_service = trial.dense
                old, old_time = observe(
                    client, headers, query, bindings, candidate=False
                )
                client.app.state.retrieval_service = trial
                new, new_time = observe(
                    client, headers, query, bindings, candidate=True
                )
                require(
                    {row["document_id"]: row for row in old_time["source_points"]}
                    == {row["document_id"]: row for row in new_time["source_points"]},
                    "human_trial_paired_generation_changed",
                )
                paired["baseline"].append(old)
                paired["candidate"].append(new)
                timing["baseline"].append(old_time)
                timing["candidate"].append(new_time)
            runs.append(
                scoring.score(
                    prepared["corpus"],
                    prepared["packet"],
                    prepared["review"],
                    prepared["plan"],
                    paired,
                )
            )
            raw_runs.append(dict(observations=paired, actual_http=timing))
            logger.info("human_trial_paired_round_completed round=%d", repetition + 1)
    finally:
        client.app.state.retrieval_service = trial
    candidate_orders = [
        [
            [row["document_id"] for row in query["ranking"]]
            for query in run["observations"]["candidate"]
        ]
        for run in raw_runs
    ]
    rankings_stable = all(order == candidate_orders[0] for order in candidate_orders)
    return dict(
        rankings_stable=rankings_stable,
        description="Actual isolated ASGI HTTP paired source/model execution on supplied reviewed additional diagnostic; human identity/independence relies on supplied attestation, no general quality/adoption claim.",
        status="PAIRED_EXECUTION_COMPLETE",
        inference_executed=True,
        completed_pairs=64,
        review_sha256=digest(prepared["review"]),
        source_bindings=bindings,
        runs=runs,
        raw_runs=raw_runs,
        all_diagnostic_checks_met=all(row["diagnostic_checks_met"] for row in runs)
        and rankings_stable,
        production_quality_certified=False,
        adoption_approved=False,
    )
