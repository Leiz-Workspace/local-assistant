"""Measure isolated pinned CPU embeddings against frozen multilingual retrieval relevance oracles."""

import argparse
import hashlib
import json
import logging
import os
import resource
import subprocess
import sys
import time
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path

import numpy as np

from scripts.embedding_runtime import ROOT, CpuE5, fingerprint, profiles, provision

logger = logging.getLogger(__name__)
CORPUS = ROOT / "tests/fixtures/embedding/retrieval.json"


def rank_metrics(scores, documents, queries):
    """Compute exact relevant-source ranks with deterministic ID tie breaking and per-group recalls."""
    if scores.shape != (len(queries), len(documents)) or not np.isfinite(scores).all():
        raise ValueError("embedding_scores_invalid")
    ids = [doc["id"] for doc in documents]
    if len(ids) != len(set(ids)):
        raise ValueError("embedding_corpus_invalid")
    ranks, groups = [], {}
    for query, row in zip(queries, scores, strict=True):
        relevant = set(query["relevant"])
        if not relevant or not relevant.issubset(ids):
            raise ValueError("embedding_relevance_invalid")
        order = sorted(
            range(len(ids)), key=lambda index: (-float(row[index]), ids[index])
        )
        relevant_ranks = [
            position
            for position, index in enumerate(order, 1)
            if ids[index] in relevant
        ]
        first = min(relevant_ranks)
        recall = sum(rank <= 3 for rank in relevant_ranks) / len(relevant)
        result = dict(
            query_id=query["id"],
            group=query["group"],
            first_relevant_rank=first,
            recall_at_3=recall,
            reciprocal_rank_at_10=1 / first if first <= 10 else 0,
            top3=[ids[index] for index in order[:3]],
        )
        ranks.append(result)
        groups.setdefault(query["group"], []).append(recall)
    return dict(
        recall_at_3=float(np.mean([r["recall_at_3"] for r in ranks])),
        mrr_at_10=float(np.mean([r["reciprocal_rank_at_10"] for r in ranks])),
        group_recall_at_3={
            key: float(np.mean(values)) for key, values in groups.items()
        },
        queries=ranks,
    )


def candidate_gate(result, gates):
    """Require frozen quality/resource thresholds without hiding ineligible candidates."""
    if "error" in result:
        return False
    return (
        result["recall_at_3"] >= gates["recall_at_3"]
        and result["mrr_at_10"] >= gates["mrr_at_10"]
        and all(
            value >= gates["group_recall_at_3"]
            for value in result["group_recall_at_3"].values()
        )
        and result["peak_rss_mib"] <= gates["peak_rss_mib"]
        and result["warm_query_p95_ms"] <= gates["warm_query_p95_ms"]
        and result["overflow_rejected"]
        and result["repeat_max_absolute_delta"] <= 1e-6
    )


def select_candidate(results, tolerance):
    """Choose minimum peak memory within the predeclared quality tolerance among eligible models."""
    eligible = [r for r in results if r["eligible"]]
    if not eligible:
        return None
    best = max(r["mrr_at_10"] for r in eligible)
    near_best = [r for r in eligible if r["mrr_at_10"] >= best - tolerance]
    return min(
        near_best,
        key=lambda r: (r["peak_rss_mib"], r["warm_query_p95_ms"], r["candidate"]),
    )["candidate"]


def measure_candidate(profile, corpus):
    """Measure one real CPU model in its own process so peak RSS is candidate-specific."""
    started = time.perf_counter()
    encoder = CpuE5(profile)
    load_ms = (time.perf_counter() - started) * 1000
    documents, queries = corpus["documents"], corpus["queries"]
    passage_texts = [item["text"] for item in documents]
    query_texts = [item["text"] for item in queries]
    passage_tokens = [
        len(encoder.tokens(text, "passage").ids) for text in passage_texts
    ]
    query_tokens = [len(encoder.tokens(text, "query").ids) for text in query_texts]
    started = time.perf_counter()
    passages = encoder.encode(passage_texts, "passage")
    passage_ms = (time.perf_counter() - started) * 1000
    encoder.encode([query_texts[0]], "query")
    latencies, vectors = [], []
    for text in query_texts:
        started = time.perf_counter()
        vectors.append(encoder.encode([text], "query")[0])
        latencies.append((time.perf_counter() - started) * 1000)
    vectors = np.stack(vectors)
    repeated = encoder.encode([query_texts[0]], "query")[0]
    overflow = False
    try:
        encoder.encode(["overflow " * 600], "passage")
    except ValueError as error:
        overflow = str(error) == "embedding_token_limit"
    metrics = rank_metrics(vectors @ passages.T, documents, queries)
    metrics.update(
        candidate=profile["id"],
        model_fingerprint=fingerprint(profile),
        repository=profile["repository"],
        revision=profile["revision"],
        dimension=profile["dimension"],
        license=profile["license"],
        artifact_bytes=sum(item["bytes"] for item in profile["artifacts"]),
        artifacts=profile["artifacts"],
        providers=encoder.session.get_providers(),
        load_ms=round(load_ms, 3),
        passage_encode_ms=round(passage_ms, 3),
        warm_query_p50_ms=round(float(np.percentile(latencies, 50)), 3),
        warm_query_p95_ms=round(float(np.percentile(latencies, 95)), 3),
        peak_rss_mib=round(
            resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 3
        ),
        max_passage_tokens=max(passage_tokens),
        max_query_tokens=max(query_tokens),
        overflow_rejected=overflow,
        repeat_max_absolute_delta=float(np.max(np.abs(repeated - vectors[0]))),
        unit_norm_max_error=float(
            max(
                np.max(np.abs(np.linalg.norm(passages, axis=1) - 1)),
                np.max(np.abs(np.linalg.norm(vectors, axis=1) - 1)),
            )
        ),
    )
    metrics["eligible"] = (
        candidate_gate(metrics, corpus["gates"])
        and metrics["unit_norm_max_error"] < 1e-5
    )
    logger.info(
        "embedding_candidate_measured candidate=%s eligible=%s",
        profile["id"],
        metrics["eligible"],
    )
    return metrics


def run_candidate(profile):
    """Run a credential-free benchmark child with fixed CPU/virtual-memory/wall budgets."""
    env = dict(
        PATH=os.defpath,
        LANG="C.UTF-8",
        PYTHONPATH=str(ROOT),
        OPENBLAS_NUM_THREADS="1",
        OMP_NUM_THREADS="2",
        TOKENIZERS_PARALLELISM="false",
    )
    try:
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "scripts.embedding_acceptance",
                "--candidate",
                profile["id"],
            ],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
        if result.returncode or len(result.stdout) > 128 * 1024:
            raise ValueError("embedding_worker_failed")
        measured = json.loads(result.stdout)
        if measured["candidate"] != profile["id"] or measured[
            "model_fingerprint"
        ] != fingerprint(profile):
            raise ValueError("embedding_worker_identity_invalid")
        return measured
    except (ValueError, OSError, subprocess.TimeoutExpired):
        logger.error("embedding_candidate_failed candidate=%s", profile["id"])
        return dict(
            candidate=profile["id"], eligible=False, error="embedding_worker_failed"
        )


def measure_shortlist():
    """Retain complete candidate results and apply the frozen choice rule without training/tuning labels."""
    corpus = json.loads(CORPUS.read_text())
    results = [run_candidate(profile) for profile in profiles()]
    chosen = select_candidate(results, corpus["selection_mrr_tolerance"])
    return dict(
        description="D24 trusted synthetic local CPU embedding tradeoffs; not a general retrieval, tenant-security or load certification.",
        version="embedding-selection-v1",
        measured_at=datetime.now(UTC).isoformat(),
        corpus_version=corpus["version"],
        corpus_sha256=hashlib.sha256(CORPUS.read_bytes()).hexdigest(),
        documents=len(corpus["documents"]),
        queries=len(corpus["queries"]),
        runtime=dict(
            onnxruntime=version("onnxruntime"),
            tokenizers=version("tokenizers"),
            numpy=version("numpy"),
            provider="CPUExecutionProvider",
            intra_op_threads=2,
            inter_op_threads=1,
            max_tokens=512,
            batch_size=4,
            pooling="attention_mask_mean",
            normalization="l2",
            distance="Cosine",
            query_prefix="query: ",
            passage_prefix="passage: ",
        ),
        gates=corpus["gates"],
        selection_mrr_tolerance=corpus["selection_mrr_tolerance"],
        candidates=results,
        selected_candidate=chosen,
        passed=chosen is not None and all("error" not in result for result in results),
    )


def main():
    """Explicitly provision or measure trusted candidates and emit only safe numeric/hash evidence."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--download", action="store_true")
    parser.add_argument("--candidate", choices=[p["id"] for p in profiles()])
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "benchmarks/results/d24-embedding-selection.json",
    )
    args = parser.parse_args()
    if args.candidate:
        resource.setrlimit(resource.RLIMIT_AS, (4 * 1024**3, 4 * 1024**3))
        resource.setrlimit(resource.RLIMIT_CPU, (120, 121))
        profile = next(p for p in profiles() if p["id"] == args.candidate)
        print(json.dumps(measure_candidate(profile, json.loads(CORPUS.read_text()))))
        return 0
    if args.download:
        for profile in profiles():
            provision(profile)
    report = measure_shortlist()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    logger.info(
        "embedding_shortlist_report_saved passed=%s selected=%s",
        report["passed"],
        report["selected_candidate"],
    )
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    raise SystemExit(main())
