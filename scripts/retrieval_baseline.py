"""Measure frozen synthetic D26 source retrieval with real CPU embeddings and explicit evaluation-only vector replay."""

import hashlib
import json
import logging
import math
import time
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import numpy as np

from apps.api.services.files import file_io
from apps.api.services.retrieval import RetrievalService
from src.infrastructure.qwen_embedding import EncodedBatch
from src.infrastructure.qwen_token_preflight import preflight_plan

logger = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "tests/fixtures/retrieval/d27-corpus.json"
PLAN = ROOT / "tests/fixtures/retrieval/d27-plan.json"
PLAN_SHA256 = "4f39578e917b8a07175ea86946e21e76f577a0d7c6ffd5397ad1a6aaf6423048"
METRICS = ("recall_at_3", "recall_at_5", "recall_at_10", "mrr_at_10", "ndcg_at_10")


def load_frozen(corpus_path=CORPUS, plan_path=PLAN):
    """Reject changed bytes, duplicate identities or invalid judgments before any model/service work."""
    raw = Path(corpus_path).read_bytes()
    plan_raw = Path(plan_path).read_bytes()
    plan, corpus = json.loads(plan_raw), json.loads(raw)
    documents, queries = corpus["documents"], corpus["queries"]
    ids = {row["id"] for row in documents}
    if (
        hashlib.sha256(plan_raw).hexdigest() != PLAN_SHA256
        or hashlib.sha256(raw).hexdigest() != plan["corpus_sha256"]
        or len(documents) != plan["document_count"]
        or len(queries) != plan["query_count"]
        or len(ids) != len(documents)
        or len({row["id"] for row in queries}) != len(queries)
        or any(
            not row["text"].strip() or len(row["text"].encode()) > plan["chunk_bytes"]
            for row in documents
        )
        or any(
            not row["relevant"]
            or len(row["relevant"]) != len(set(row["relevant"]))
            or not set(row["relevant"]).issubset(ids)
            for row in queries
        )
        or {row["group"] for row in queries} != {"vi", "en", "cross_language"}
    ):
        raise ValueError("retrieval_evaluation_freeze_invalid")
    logger.info(
        "retrieval_evaluation_freeze_verified documents=%d queries=%d",
        len(documents),
        len(queries),
    )
    return corpus, plan


def aggregate(rows):
    """Compute query-macro means without treating omitted relevant documents as successful ranks."""
    if not rows:
        raise ValueError("retrieval_evaluation_empty")
    return {key: sum(row[key] for row in rows) / len(rows) for key in METRICS}


def score_rankings(corpus, observations):
    """Validate complete top10 source observations and compute binary recall, reciprocal rank and nDCG."""
    documents, queries = corpus["documents"], corpus["queries"]
    ids = {row["id"] for row in documents}
    expected = {row["id"] for row in queries}
    if len(ids) != len(documents) or len(expected) != len(queries) or not expected:
        raise ValueError("retrieval_evaluation_identity_invalid")
    if (
        not isinstance(observations, list)
        or len(observations) != len(expected)
        or {row["query_id"] for row in observations} != expected
    ):
        raise ValueError("retrieval_evaluation_incomplete")
    indexed = {row["query_id"]: row for row in observations}
    results = []
    for query in queries:
        relevant = set(query["relevant"])
        if (
            not relevant
            or len(relevant) != len(query["relevant"])
            or not relevant.issubset(ids)
        ):
            raise ValueError("retrieval_evaluation_judgment_invalid")
        observed = indexed[query["id"]]["ranking"]
        if not isinstance(observed, list) or len(observed) > 10:
            raise ValueError("retrieval_evaluation_ranking_invalid")
        seen, previous = set(), float("inf")
        for row in observed:
            identifier, score = row["document_id"], row["score"]
            if (
                identifier not in ids
                or identifier in seen
                or type(score) not in (int, float)
                or not math.isfinite(score)
                or not -1.0001 <= score <= 1.0001
                or score > previous
            ):
                raise ValueError("retrieval_evaluation_ranking_invalid")
            seen.add(identifier)
            previous = score
        ranks = {row["document_id"]: index for index, row in enumerate(observed, 1)}
        relevant_ranks = [ranks[name] for name in relevant if name in ranks]
        first = min(relevant_ranks) if relevant_ranks else None
        ideal = sum(
            1 / math.log2(index + 1) for index in range(1, min(10, len(relevant)) + 1)
        )
        row = dict(
            query_id=query["id"],
            group=query["group"],
            intent=query.get("intent"),
            first_relevant_rank=first,
            relevant_ranks={name: ranks.get(name) for name in sorted(relevant)},
            mrr_at_10=1 / first if first is not None else 0,
            ndcg_at_10=sum(1 / math.log2(rank + 1) for rank in relevant_ranks) / ideal,
            ranking=observed,
        )
        for k in (3, 5, 10):
            row[f"recall_at_{k}"] = sum(rank <= k for rank in relevant_ranks) / len(
                relevant
            )
        results.append(row)
    groups = {
        group: aggregate([row for row in results if row["group"] == group])
        for group in sorted({q["group"] for q in queries})
    }
    logger.info("retrieval_evaluation_scored queries=%d", len(results))
    return dict(metrics=aggregate(results), groups=groups, queries=results)


def confidence_intervals(rows, settings):
    """Compute deterministic descriptive query-bootstrap intervals without implying independent human sampling."""
    values = np.array([[row[key] for key in METRICS] for row in rows], dtype=float)
    rng = np.random.default_rng(settings["seed"])
    samples = rng.integers(0, len(rows), size=(settings["resamples"], len(rows)))
    limits = np.percentile(values[samples].mean(axis=1), settings["percentile"], axis=0)
    return {
        key: [float(limits[0, index]), float(limits[1, index])]
        for index, key in enumerate(METRICS)
    }


class RecordedEmbeddings:
    """Replay only immutable real CPU vectors bound to exact text bytes and the frozen model identity."""

    def __init__(self, model, texts, batch):
        """Require complete model-bound inputs and retain no synthetic fallback vectors."""
        if (
            batch.model_fingerprint != model
            or len(texts) != len(batch.counts)
            or len(texts) != len(batch.vectors)
        ):
            raise ValueError("retrieval_evaluation_encoding_invalid")
        self.model = model
        self.values = dict(
            zip(texts, zip(batch.counts, batch.vectors, strict=True), strict=True)
        )

    async def encode(self, plan):
        """Return real precomputed passage vectors only when every source text and model is known exactly."""
        if plan.model_fingerprint != self.model:
            raise ValueError("retrieval_evaluation_encoding_invalid")
        pairs = [self.values[point.text] for point in plan.points]
        logger.info("retrieval_evaluation_passage_replayed points=%d", len(pairs))
        return EncodedBatch(
            self.model,
            tuple(pair[0] for pair in pairs),
            tuple(pair[1] for pair in pairs),
        )


class RecordedQueries:
    """Replay real instructed-query vectors solely inside the frozen evaluation harness."""

    def __init__(self, recorded, prefix):
        """Bind an exact approved query prefix and the same actual CPU encoding record."""
        self.recorded, self.prefix = recorded, prefix

    async def encode(self, query):
        """Lookup only the exact instructed query bytes without loading another model or changing production."""
        logger.info("retrieval_evaluation_query_replayed")
        return self.recorded.values[self.prefix + query][1]


async def encode_corpus(corpus, plan, encoder):
    """Measure one actual credential-free batch over complete passages and fully instructed queries."""
    profile = json.loads((ROOT / "configs/embedding-qwen-evaluation.json").read_text())
    prefix = profile["query_prefix"]
    if (
        hashlib.sha256(prefix.encode()).hexdigest() != plan["query_prefix_sha256"]
        or profile["passage_prefix"]
    ):
        raise ValueError("retrieval_evaluation_query_format_invalid")
    texts = [row["text"] for row in corpus["documents"]] + [
        prefix + row["text"] for row in corpus["queries"]
    ]
    request = SimpleNamespace(
        job_id=uuid4(),
        model_fingerprint=plan["model_fingerprint"],
        points=tuple(SimpleNamespace(text=text) for text in texts),
    )
    started = time.perf_counter()
    counts = await file_io(preflight_plan, request)
    preflight_seconds = time.perf_counter() - started
    started = time.perf_counter()
    batch = await encoder.encode(request)
    encoding_seconds = time.perf_counter() - started
    if batch.counts != counts:
        raise ValueError("retrieval_evaluation_encoding_invalid")
    logger.info("retrieval_evaluation_real_batch_complete inputs=%d", len(texts))
    return (
        RecordedEmbeddings(plan["model_fingerprint"], texts, batch),
        prefix,
        dict(
            actual_inputs=len(texts),
            actual_dimension=1024,
            full_token_counts=list(counts),
            tokenizer_batch_seconds=preflight_seconds,
            encoder_batch_wall_seconds=encoding_seconds,
            peak_child_rss_mib=None,
            peak_vram_mib=None,
            resource_note="Parent wall measurements only; child RSS/VRAM not instrumented in this replay baseline.",
        ),
    )


async def upload_source(files, owner, data, key):
    """Upload a real immutable synthetic source with exact size/hash through accepted FileService."""

    async def body():
        """Yield only the complete owned synthetic UTF-8 bytes to the existing upload protocol."""
        yield data

    row = await files.reserve(
        owner,
        filename="evaluation.txt",
        size_bytes=len(data),
        sha256=hashlib.sha256(data).hexdigest(),
        request_key=key,
    )
    await files.upload(owner, row["id"], body())
    return row["id"]


async def measure_baseline(worker, owners, corpus, plan, recorded, prefix, encoding):
    """Run actual source/journal/vector/retrieval paths twice with explicit real-vector replay and ACL canary."""
    if worker.encoder is not recorded or worker.model != plan["model_fingerprint"]:
        raise ValueError("retrieval_evaluation_worker_invalid")
    owner, foreign = owners
    sources, bindings = {}, []
    for document in corpus["documents"]:
        file_id = await upload_source(
            worker.files, owner, document["text"].encode(), document["id"]
        )
        job = await worker.admit(owner, file_id, max_bytes=plan["chunk_bytes"])
        ready = await worker.process(owner, job["id"])
        if ready["state"] != "ready" or len(ready["point_ids"]) != 1:
            raise ValueError("retrieval_evaluation_source_invalid")
        sources[str(file_id)] = document["id"]
        bindings.append(
            dict(
                document_id=document["id"],
                file_id=str(file_id),
                source_sha256=ready["source_sha256"],
                point_id=str(ready["point_ids"][0]),
                generation=ready["generation"],
            )
        )
    canary = await upload_source(
        worker.files, foreign, corpus["documents"][0]["text"].encode(), "foreign-canary"
    )
    job = await worker.admit(foreign, canary)
    if (await worker.process(foreign, job["id"]))["state"] != "ready":
        raise ValueError("retrieval_evaluation_canary_invalid")
    retrieval = RetrievalService(worker, encoder=RecordedQueries(recorded, prefix))
    rounds, latencies = [], []
    try:
        for repeat in range(plan["replay_rounds"]):
            observations = []
            for query in corpus["queries"]:
                started = time.perf_counter()
                async with retrieval.operation(
                    owner, query["text"], top_k=plan["top_k"]
                ) as (payload, retained):
                    await retrieval.validate(owner, retained)
                    ranking = []
                    for hit in payload["hits"]:
                        if hit["file_id"] not in sources or hit["provenance"][
                            "owner_id"
                        ] != str(owner):
                            raise ValueError("retrieval_evaluation_acl_leak")
                        ranking.append(
                            dict(
                                document_id=sources[hit["file_id"]],
                                score=hit["score"],
                                point_id=hit["point_id"],
                                source_sha256=hit["source_sha256"],
                            )
                        )
                latencies.append((time.perf_counter() - started) * 1000)
                observations.append(dict(query_id=query["id"], ranking=ranking))
            rounds.append(observations)
            logger.info("retrieval_evaluation_round_complete round=%d", repeat + 1)
        async with retrieval.operation(
            foreign, corpus["queries"][0]["text"], top_k=10
        ) as (payload, _):
            foreign_isolated = len(payload["hits"]) == 1 and payload["hits"][0][
                "file_id"
            ] == str(canary)
        stable = all(row == rounds[0] for row in rounds)
        scored = score_rankings(corpus, rounds[0])
        gates = plan["diagnostic_quality_gates"]
        quality = (
            scored["metrics"]["recall_at_3"] >= gates["recall_at_3"]
            and scored["metrics"]["mrr_at_10"] >= gates["mrr_at_10"]
            and all(
                values["recall_at_3"] >= gates["group_recall_at_3"]
                for values in scored["groups"].values()
            )
        )
        return dict(
            description="D27-T01 actual approved CPU embeddings and real D26 source/SQL/Qdrant baseline with evaluation-only cached vector replay; synthetic diagnostic, no reranker.",
            version="d27-baseline-v1",
            complete=True,
            protocol_passed=stable and foreign_isolated,
            plan_sha256=PLAN_SHA256,
            corpus_sha256=plan["corpus_sha256"],
            model_fingerprint=worker.model,
            document_count=len(sources),
            query_count=len(corpus["queries"]),
            replay_rounds=len(rounds),
            replay_rankings=rounds,
            rankings_stable=stable,
            foreign_identical_source_excluded=foreign_isolated,
            diagnostic_quality_gates_met=quality,
            quality_thresholds_frozen=gates,
            source_bindings=bindings,
            encoding=encoding,
            cached_retrieval_latency_ms=dict(
                p50=float(np.percentile(latencies, 50)),
                p95=float(np.percentile(latencies, 95)),
                samples=len(latencies),
                observed_ms=latencies,
                definition="Cached real query vectors; actual D26 Qdrant/SQL/source reconstruction, final fences and context cleanup; excludes per-request token/model startup and HTTP.",
            ),
            descriptive_query_bootstrap95=confidence_intervals(
                scored["queries"], plan["bootstrap"]
            ),
            bootstrap_limit="Queries share12 authored intents; not independent human/production sampling.",
            reranker_status="NOT_PROVISIONED_NOT_EVALUATED",
            candidate_adoption_authorized=False,
            model_or_production_configuration_changed=False,
            **scored,
        )
    finally:
        await retrieval.shutdown()
