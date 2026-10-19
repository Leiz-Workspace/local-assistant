"""Compare authorized Qwen/E5 configurations in isolated processes without changing selected models or indexes."""

import argparse
import hashlib
import json
import logging
import os
import resource
import shutil
import subprocess
import sys
import time
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path

import numpy as np

from scripts.embedding_acceptance import CORPUS, candidate_gate
from scripts.embedding_runtime import ROOT, CpuE5, fingerprint, profiles
from scripts.qwen_embedding_evaluation import (
    QwenCpu,
    qwen_fingerprint,
    qwen_profile,
    retrieval_metrics,
)

logger = logging.getLogger(__name__)
WORKER = ROOT / "scripts/qwen_embedding_worker.py"


def measure_one(candidate):
    """Measure one real pinned CPU model on the identical frozen corpus with no stateful service calls."""
    corpus = json.loads(CORPUS.read_text())
    started = time.perf_counter()
    if candidate == "qwen":
        profile = qwen_profile()
        encoder = QwenCpu(profile)
        identity = qwen_fingerprint(profile)
        runtime = dict(
            engine="pytorch",
            device="cpu",
            weight_dtype="bfloat16",
            pooling="last_attended_token_float32",
            fingerprint=identity,
            packages={
                name: version(name)
                for name in (
                    "torch",
                    "transformers",
                    "numpy",
                    "tokenizers",
                    "safetensors",
                )
            },
        )
    elif candidate == "e5":
        profile = next(p for p in profiles() if p["id"] == "e5-base-int8")
        encoder = CpuE5(profile)
        identity = fingerprint(profile)
        runtime = dict(
            engine="onnxruntime",
            device="cpu",
            weight_dtype="int8",
            pooling="attention_mask_mean",
            fingerprint=identity,
            packages={
                name: version(name) for name in ("onnxruntime", "tokenizers", "numpy")
            },
        )
    else:
        raise ValueError("comparison_candidate_invalid")
    load_ms = (time.perf_counter() - started) * 1000
    docs, queries = corpus["documents"], corpus["queries"]
    doc_texts = [d["text"] for d in docs]
    query_texts = [q["text"] for q in queries]
    token_counts = []
    for kind, texts in [("passage", doc_texts), ("query", query_texts)]:
        encoded = [encoder.tokens(text, kind) for text in texts]
        token_counts.append(
            [len(item if isinstance(item, list) else item.ids) for item in encoded]
        )
    encoder.encode([doc_texts[0]], "passage")
    passage_ms = []
    for text in doc_texts:
        start = time.perf_counter()
        encoder.encode([text], "passage")
        passage_ms.append((time.perf_counter() - start) * 1000)
    start = time.perf_counter()
    passages = encoder.encode(doc_texts, "passage")
    document_batch_ms = (time.perf_counter() - start) * 1000
    encoder.encode([query_texts[0]], "query")
    query_ms, vectors = [], []
    for text in query_texts:
        start = time.perf_counter()
        vectors.append(encoder.encode([text], "query")[0])
        query_ms.append((time.perf_counter() - start) * 1000)
    vectors = np.stack(vectors)
    repeated = encoder.encode([query_texts[0]], "query")[0]
    overflow = False
    try:
        encoder.encode(["overflow " * 700], "passage")
    except ValueError as error:
        overflow = str(error) == "embedding_token_limit"
    start = time.perf_counter()
    flat_index = np.array(passages, dtype=np.float32, copy=True, order="C")
    build_ms = (time.perf_counter() - start) * 1000
    start = time.perf_counter()
    scores = vectors @ flat_index.T
    query_index_ms = (time.perf_counter() - start) * 1000
    metrics = retrieval_metrics(scores, docs, queries)
    result = dict(
        candidate=candidate,
        profile_id=profile["id"],
        repository=profile["repository"],
        revision=profile["revision"],
        dimension=profile["dimension"],
        runtime=runtime,
        artifacts=profile["artifacts"],
        artifact_bytes=sum(a["bytes"] for a in profile["artifacts"]),
        corpus_sha256=hashlib.sha256(CORPUS.read_bytes()).hexdigest(),
        input_manifest_sha256=hashlib.sha256(
            json.dumps(
                dict(documents=docs, queries=queries),
                sort_keys=True,
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode()
        ).hexdigest(),
        documents=len(docs),
        query_count=len(queries),
        max_passage_tokens=max(token_counts[0]),
        max_query_tokens=max(token_counts[1]),
        load_ms=round(load_ms, 3),
        document_batch_ms=round(document_batch_ms, 3),
        document_batch_per_second=round(len(docs) * 1000 / document_batch_ms, 3),
        warm_document_p50_ms=round(float(np.percentile(passage_ms, 50)), 3),
        warm_document_p95_ms=round(float(np.percentile(passage_ms, 95)), 3),
        warm_query_p50_ms=round(float(np.percentile(query_ms, 50)), 3),
        warm_query_p95_ms=round(float(np.percentile(query_ms, 95)), 3),
        peak_rss_mib=round(
            resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 3
        ),
        gpu_allocation_bytes=0,
        overflow_rejected=overflow,
        repeat_max_absolute_delta=float(np.max(np.abs(repeated - vectors[0]))),
        unit_norm_max_error=float(
            max(
                np.max(np.abs(np.linalg.norm(passages, axis=1) - 1)),
                np.max(np.abs(np.linalg.norm(vectors, axis=1) - 1)),
            )
        ),
        flat_index=dict(
            bytes=flat_index.nbytes,
            build_ms=round(build_ms, 6),
            query_all_ms=round(query_index_ms, 6),
            build_vectors_per_second=round(len(docs) * 1000 / max(build_ms, 1e-9), 3),
        ),
        qdrant_ingest_throughput=None,
        qdrant_disk_index_bytes=None,
        **metrics,
    )
    gate_view = dict(
        result,
        group_recall_at_3={
            group: values["recall_at_3"] for group, values in metrics["groups"].items()
        },
    )
    result["meets_d24_reference_gates"] = (
        candidate_gate(gate_view, corpus["gates"])
        and result["unit_norm_max_error"] < 1e-5
    )
    logger.info(
        "embedding_comparison_run_measured candidate=%s recall3=%.3f",
        candidate,
        result["recall_at_3"],
    )
    return result


def comparison_command(candidate):
    """Use the locked CPU-only uv script environment for Qwen and unchanged project runtime for E5."""
    if candidate == "qwen":
        executable = shutil.which("uv")
        if executable is None:
            raise ValueError("comparison_uv_unavailable")
        return [
            executable,
            "run",
            "--offline",
            "--frozen",
            "--script",
            str(WORKER),
            "--candidate",
            "qwen",
        ]
    if candidate == "e5":
        return [sys.executable, str(WORKER), "--candidate", "e5"]
    raise ValueError("comparison_candidate_invalid")


def run_one(candidate):
    """Launch bounded workers without Vault/DB/API/Hub credentials or proxy inheritance."""
    env = dict(
        PATH=os.defpath,
        LANG="C.UTF-8",
        PYTHONPATH=str(ROOT),
        OPENBLAS_NUM_THREADS="1",
        OMP_NUM_THREADS="2",
        TOKENIZERS_PARALLELISM="false",
        HF_HUB_OFFLINE="1",
        TRANSFORMERS_OFFLINE="1",
        HF_HUB_DISABLE_IMPLICIT_TOKEN="1",
        CUDA_VISIBLE_DEVICES="",
        UV_CACHE_DIR=str(Path.home() / ".cache/uv"),
    )
    try:
        result = subprocess.run(
            comparison_command(candidate),
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=600,
            check=False,
        )
        if result.returncode or len(result.stdout) > 256 * 1024:
            raise ValueError("comparison_worker_failed")
        payload = json.loads(result.stdout)
        if (
            payload["candidate"] != candidate
            or payload["corpus_sha256"]
            != hashlib.sha256(CORPUS.read_bytes()).hexdigest()
        ):
            raise ValueError("comparison_worker_identity_invalid")
        return payload
    except (ValueError, OSError, subprocess.TimeoutExpired):
        logger.error("embedding_comparison_worker_failed candidate=%s", candidate)
        return dict(candidate=candidate, error="comparison_worker_failed")


def summarize_runs(candidate, runs):
    """Retain every repetition and distinguish incomplete results from stable quality/resource observations."""
    if any("error" in r for r in runs):
        return dict(candidate=candidate, complete=False, runs=runs)
    rankings = [
        [(q["query_id"], q["relevant_ranks"], q["top10"]) for q in r["queries"]]
        for r in runs
    ]
    quality_keys = ("recall_at_3", "recall_at_5", "recall_at_10", "mrr_at_10")
    return dict(
        candidate=candidate,
        complete=True,
        rankings_stable=all(r == rankings[0] for r in rankings),
        quality={
            key: dict(min=min(r[key] for r in runs), max=max(r[key] for r in runs))
            for key in quality_keys
        },
        peak_rss_mib_max=max(r["peak_rss_mib"] for r in runs),
        warm_query_p95_ms_max=max(r["warm_query_p95_ms"] for r in runs),
        all_d24_reference_gates_met=all(r["meets_d24_reference_gates"] for r in runs),
        runs=runs,
    )


def compare():
    """Measure three repetitions per candidate without changing frozen thresholds, configs or routing."""
    measurements = {candidate: [] for candidate in ("e5", "qwen")}
    for repetition in range(3):
        for candidate in ("e5", "qwen"):
            logger.info(
                "embedding_comparison_started candidate=%s repetition=%d",
                candidate,
                repetition + 1,
            )
            measurements[candidate].append(run_one(candidate))
    summaries = [
        summarize_runs(candidate, runs) for candidate, runs in measurements.items()
    ]
    complete = all(s["complete"] for s in summaries)
    same_inputs = (
        complete
        and len({r["input_manifest_sha256"] for s in summaries for r in s["runs"]}) == 1
    )
    return dict(
        description="MODEL-EVAL-001 authorized offline Qwen BF16/PyTorch versus preserved E5 int8/ONNX configuration comparison; no deployment approval or Qdrant throughput claim.",
        version="qwen-e5-comparison-v1",
        measured_at=datetime.now(UTC).isoformat(),
        complete=complete,
        same_inputs=same_inputs,
        corpus_sha256=hashlib.sha256(CORPUS.read_bytes()).hexdigest(),
        script_lock_sha256=hashlib.sha256(
            Path(str(WORKER) + ".lock").read_bytes()
        ).hexdigest(),
        repetitions=3,
        common_policy=dict(
            max_tokens=512,
            threads=2,
            inter_op_threads=1,
            batch_size=4,
            device="cpu",
            distance="Cosine",
            reranker=False,
            no_truncation=True,
        ),
        candidates=summaries,
        configuration_precision_difference="Qwen official BF16 weights with FP32 pooling/normalization versus E5 official int8 ONNX; not a controlled same-precision model-only ablation.",
        qdrant_measurement_status="NOT MEASURED: no stateful service calls authorized; flat-index metrics are memory copies/matrix products only.",
        cutover_status="OWNER_APPROVAL_PENDING",
        passed=complete
        and same_inputs
        and all(s["rankings_stable"] for s in summaries),
    )


def main():
    """Save truthful comparison evidence and fail on incomplete/inconsistent worker measurements."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "benchmarks/results/qwen-e5-comparison.json",
    )
    args = parser.parse_args()
    report = compare()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    logger.info(
        "embedding_comparison_saved complete=%s passed=%s",
        report["complete"],
        report["passed"],
    )
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    raise SystemExit(main())
