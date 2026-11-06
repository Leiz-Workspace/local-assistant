"""Compare only frozen original-candidate reranking against retained D27 baseline without source/vector mutations."""

import asyncio
import hashlib
import json
import logging
import math
import os
import re
import shutil
import signal
from pathlib import Path

import numpy as np

from scripts.qwen_reranker_runtime import (
    INSTRUCTION,
    PREFIX,
    PROFILE,
    SUFFIX,
    profile,
    yes_probability,
)
from scripts.retrieval_baseline import (
    ROOT,
    confidence_intervals,
    load_frozen,
    score_rankings,
)
from src.infrastructure.qwen_embedding import join_task

logger = logging.getLogger(__name__)
BASELINE = ROOT / "docs/evidence/d27-retrieval-baseline.json"
BASELINE_SHA256 = "cb4248e1dd2a16d43b0c861a2c17a358dfa405b9da981bb6db10af38154f74fd"
WORKER = ROOT / "scripts/qwen_reranker_worker.py"


EXECUTION = ROOT / "docs/evidence/d27-t02-execution-manifest.json"


def verify_execution():
    """Require the separately frozen non-adoption manifest and exact local code/artifact contract before launch."""
    execution = json.loads(EXECUTION.read_text())
    required = {
        "scripts/qwen_reranker_runtime.py",
        "scripts/qwen_reranker_worker.py",
        "scripts/qwen_reranker_worker.py.lock",
        "scripts/reranker_comparison.py",
        "configs/reranker-qwen-evaluation.json",
        "configs/reranker-qwen-batch4-evaluation.json",
        "tests/fixtures/retrieval/d27-corpus.json",
        "tests/fixtures/retrieval/d27-plan.json",
        "docs/evidence/d27-retrieval-baseline.json",
    }
    if (
        execution["scope"] != "EVALUATION_ONLY_NO_ADOPTION"
        or set(execution["sha256"]) != required
    ):
        raise ValueError("reranker_execution_manifest_invalid")
    for name, expected in execution["sha256"].items():
        if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != expected:
            raise ValueError("reranker_execution_manifest_invalid")
    logger.info("reranker_execution_manifest_verified")
    return execution


def build_request():
    """Bind every candidate text/hash/ID to frozen judgments and retained actual source evidence before inference."""
    corpus, plan = load_frozen()
    if hashlib.sha256(BASELINE.read_bytes()).hexdigest() != BASELINE_SHA256:
        raise ValueError("reranker_baseline_changed")
    baseline = json.loads(BASELINE.read_text())
    if (
        baseline["corpus_sha256"] != plan["corpus_sha256"]
        or not baseline["protocol_passed"]
    ):
        raise ValueError("reranker_baseline_invalid")
    documents = {row["id"]: row["text"] for row in corpus["documents"]}
    bindings = {row["document_id"]: row for row in baseline["source_bindings"]}
    observed = {row["query_id"]: row["ranking"] for row in baseline["queries"]}
    if len(bindings) != 24 or len(observed) != 36:
        raise ValueError("reranker_baseline_invalid")
    queries = []
    for query in corpus["queries"]:
        candidates = []
        for row in observed[query["id"]]:
            identifier = row["document_id"]
            if (
                row["source_sha256"]
                != hashlib.sha256(documents[identifier].encode()).hexdigest()
                or row["source_sha256"] != bindings[identifier]["source_sha256"]
                or row["point_id"] != bindings[identifier]["point_id"]
            ):
                raise ValueError("reranker_source_binding_invalid")
            candidates.append(dict(id=identifier, text=documents[identifier]))
        if len(candidates) != 10 or len({row["id"] for row in candidates}) != 10:
            raise ValueError("reranker_candidates_incomplete")
        queries.append(dict(id=query["id"], text=query["text"], documents=candidates))
    logger.info("reranker_frozen_candidates_verified queries=%d", len(queries))
    return dict(
        profile_sha256=hashlib.sha256(PROFILE.read_bytes()).hexdigest(), queries=queries
    )


def validate_reply(request, reply):
    """Reject incomplete, foreign, nonfinite, inconsistent or over-budget candidate replies without diagnostic leakage."""
    try:
        configuration = profile()
        if (
            not isinstance(reply, dict)
            or set(reply)
            != {
                "profile_sha256",
                "model_fingerprint",
                "contract",
                "cold_load_seconds",
                "last_logits_reference_parity",
                "peak_candidate_rss_mib",
                "candidate_gpu_allocation_bytes",
                "gpu_measurement",
                "rounds",
            }
            or reply["profile_sha256"] != request["profile_sha256"]
        ):
            raise ValueError("identity")
        contract = reply["contract"]
        expected = dict(
            profile=configuration,
            prefix=PREFIX,
            suffix=SUFFIX,
            instruction=INSTRUCTION,
            scoring="last_position_float32_softmax_no_yes",
            device="cpu",
            dtype="bfloat16",
            attention="sdpa",
            batch=configuration["batch_size"],
            threads=2,
            interop_threads=1,
            use_cache=False,
            logits_to_keep=1,
            no_id=configuration["class_token_ids"]["no"],
            yes_id=configuration["class_token_ids"]["yes"],
            runtime=dict(
                torch="2.10.0+cpu",
                transformers="4.57.6",
                numpy="2.5.4",
                tokenizers="0.22.2",
                safetensors="0.8.0",
            ),
        )
        identity = hashlib.sha256(
            json.dumps(contract, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        if (
            contract != expected
            or reply["model_fingerprint"] != identity
            or not re.fullmatch("[0-9a-f]{64}", identity)
        ):
            raise ValueError("model")
        parity = reply["last_logits_reference_parity"]
        if (
            set(parity) != {"exact", "reference_logits", "optimized_logits"}
            or parity["exact"] is not True
            or parity["reference_logits"] != parity["optimized_logits"]
        ):
            raise ValueError("reference_parity")
        yes_probability(parity["reference_logits"])
        for key in ["cold_load_seconds", "peak_candidate_rss_mib"]:
            if (
                type(reply[key]) not in (int, float)
                or not math.isfinite(reply[key])
                or reply[key] <= 0
            ):
                raise ValueError("measurement")
        if (
            type(reply["candidate_gpu_allocation_bytes"]) is not int
            or reply["candidate_gpu_allocation_bytes"] != 0
        ):
            raise ValueError("device")
        rounds = reply["rounds"]
        if not isinstance(rounds, list) or len(rounds) != configuration["repetitions"]:
            raise ValueError("rounds")
        for rows in rounds:
            if not isinstance(rows, list) or len(rows) != len(request["queries"]):
                raise ValueError("queries")
            for query, row in zip(request["queries"], rows, strict=True):
                if (
                    set(row) != {"query_id", "documents", "wall_seconds"}
                    or row["query_id"] != query["id"]
                    or type(row["wall_seconds"]) not in (float, int)
                    or not math.isfinite(row["wall_seconds"])
                    or row["wall_seconds"] <= 0
                ):
                    raise ValueError("query")
                if not isinstance(row["documents"], list) or len(
                    row["documents"]
                ) != len(query["documents"]):
                    raise ValueError("documents")
                for expected_doc, actual in zip(
                    query["documents"], row["documents"], strict=True
                ):
                    if (
                        set(actual) != {"document_id", "score", "tokens", "logits"}
                        or actual["document_id"] != expected_doc["id"]
                        or type(actual["tokens"]) is not int
                        or not 1 <= actual["tokens"] <= 512
                        or type(actual["score"]) not in (float, int)
                        or not math.isfinite(actual["score"])
                        or not 0 <= actual["score"] <= 1
                        or abs(actual["score"] - yes_probability(actual["logits"]))
                        > 1e-7
                    ):
                        raise ValueError("score")
        logger.info("reranker_complete_reply_verified")
        return reply
    except (ValueError, TypeError, KeyError, AttributeError, OverflowError):
        logger.warning("reranker_evaluation_reply_rejected")
        raise ValueError("reranker_evaluation_reply_invalid") from None


class RerankerEvaluation:
    """Own one isolated credential-free candidate process until complete output or joined cancellation/timeout."""

    def __init__(self, *, timeout=600):
        """Set bounded evaluation-only timeout and a process-local nonqueued admission slot."""
        if not 0 < timeout <= 600:
            raise ValueError("reranker_timeout_invalid")
        self.timeout = timeout
        self.admission = asyncio.Lock()

    async def run(self, request):
        """Launch only frozen offline uv worker and kill/join the owned process group on all incomplete paths."""
        verify_execution()
        if self.admission.locked():
            raise ValueError("reranker_evaluation_busy")
        await self.admission.acquire()
        child, work = None, None
        try:
            body = json.dumps(request, ensure_ascii=False).encode()
            if len(body) > 1024**2:
                raise ValueError("reranker_input_limit")
            executable = shutil.which("uv")
            if executable is None:
                raise ValueError("reranker_runtime_missing")
            env = dict(
                PATH=os.environ.get("PATH", "/usr/bin:/bin"),
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
                UV_PYTHON_DOWNLOADS="never",
                QWEN_INGESTION_PARENT_PID=str(os.getpid()),
                QWEN_INGESTION_PARENT_START=Path("/proc/self/stat")
                .read_text()
                .rsplit(")", 1)[1]
                .split()[19],
            )
            launch = asyncio.create_task(
                asyncio.create_subprocess_exec(
                    executable,
                    "run",
                    "--offline",
                    "--frozen",
                    "--script",
                    str(WORKER),
                    cwd=ROOT,
                    env=env,
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    start_new_session=True,
                )
            )
            try:
                child = await asyncio.shield(launch)
            except asyncio.CancelledError:
                child = await join_task(launch)
                raise
            work = asyncio.create_task(child.communicate(body))
            stdout, stderr = await asyncio.wait_for(asyncio.shield(work), self.timeout)
            if child.returncode:
                rounds_completed = len(
                    re.findall(rb"reranker_evaluation_round_completed", stderr)
                )
                logger.warning(
                    "reranker_worker_nonzero exit_code=%d completed_rounds=%d",
                    child.returncode,
                    rounds_completed,
                )
            if child.returncode or len(stdout) > 2 * 1024**2:
                raise ValueError("reranker_worker_failed")
            return validate_reply(request, json.loads(stdout))
        except asyncio.CancelledError:
            logger.warning("reranker_evaluation_cancelled")
            raise
        except (ValueError, OSError, TimeoutError):
            logger.warning("reranker_evaluation_failed_safely")
            raise ValueError("reranker_evaluation_failed") from None
        finally:
            try:
                if child is not None and child.returncode is None:
                    try:
                        os.killpg(child.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    if work is None:
                        work = asyncio.create_task(child.communicate())
                if work is not None:
                    try:
                        await join_task(work)
                    except Exception:
                        logger.warning("reranker_pipe_join_failed")
            finally:
                self.admission.release()


def compare_reply(request, reply):
    """Score paired fixed candidates and retain each failed quality/resource gate instead of selecting a model."""
    reply = validate_reply(request, reply)
    corpus, plan = load_frozen()
    baseline = json.loads(BASELINE.read_text())
    summaries = []
    for rows in reply["rounds"]:
        observations = [
            dict(
                query_id=row["query_id"],
                ranking=[
                    dict(document_id=d["document_id"], score=d["score"])
                    for d in sorted(
                        row["documents"], key=lambda d: (-d["score"], d["document_id"])
                    )
                ],
            )
            for row in rows
        ]
        summaries.append(score_rankings(corpus, observations))
    base = baseline["metrics"]
    gates = plan["candidate_comparison_gates"]
    evaluations = []
    for scored in summaries:
        delta = {key: scored["metrics"][key] - value for key, value in base.items()}
        checks = dict(
            recall_at_10_nonregression=delta["recall_at_10"]
            >= gates["recall_at_10_min_delta"],
            recall_at_3_nonregression=delta["recall_at_3"]
            >= gates["recall_at_3_min_delta"],
            mrr_nonregression=delta["mrr_at_10"] >= gates["mrr_at_10_min_delta"],
            ndcg_min_improvement=delta["ndcg_at_10"]
            >= gates["ndcg_at_10_min_improvement"],
            group_recall_nonregression=all(
                baseline["groups"][group]["recall_at_3"] - values["recall_at_3"]
                <= gates["group_recall_at_3_max_loss"]
                for group, values in scored["groups"].items()
            ),
        )
        paired = [
            {key: row[key] - old[key] for key in base}
            for row, old in zip(scored["queries"], baseline["queries"], strict=True)
        ]
        evaluations.append(
            dict(
                delta=delta,
                checks=checks,
                all_quality_gates_met=all(checks.values()),
                descriptive_paired_query_bootstrap95=confidence_intervals(
                    paired, plan["bootstrap"]
                ),
                **scored,
            )
        )
    orders = [
        [[doc["document_id"] for doc in row["ranking"]] for row in s["queries"]]
        for s in summaries
    ]
    stable = all(order == orders[0] for order in orders)
    walls = [row["wall_seconds"] for rows in reply["rounds"] for row in rows]
    configuration = profile()
    resource_checks = dict(
        rss_budget=reply["peak_candidate_rss_mib"] <= configuration["max_rss_mib"],
        query_wall_budget=max(walls) <= configuration["max_query_seconds"],
        cpu_only=reply["candidate_gpu_allocation_bytes"] == 0,
    )
    logger.info("reranker_paired_comparison_scored stable=%s", stable)
    return dict(
        description="D27-T02 actual isolated original-candidate CPU reranker comparison on unchanged authored synthetic frozen top10 candidates; no adoption/production approval.",
        version="d27-reranker-comparison-v1",
        corpus_sha256=plan["corpus_sha256"],
        baseline_sha256=BASELINE_SHA256,
        profile_sha256=request["profile_sha256"],
        complete=True,
        rankings_stable=stable,
        resource_checks=resource_checks,
        all_resource_gates_met=all(resource_checks.values()),
        all_quality_gates_met=all(row["all_quality_gates_met"] for row in evaluations),
        baseline_metrics=base,
        baseline_groups=baseline["groups"],
        runs=evaluations,
        actual_worker=reply,
        candidate_query_wall_ms=dict(
            p50=float(np.percentile(walls, 50) * 1000),
            p95=float(np.percentile(walls, 95) * 1000),
            max=float(max(walls) * 1000),
            samples=len(walls),
            definition="Ten candidate pairs per query with model already loaded; excludes cold load, embedding, retrieval and HTTP.",
        ),
        independent_human_quality_status="NOT_VALIDATED",
        adoption_authorized=False,
        production_configuration_changed=False,
        decision="REVIEW_REQUIRED_NO_AUTOMATIC_ADOPTION",
    )
