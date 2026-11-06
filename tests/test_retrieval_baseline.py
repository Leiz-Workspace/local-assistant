"""Verify frozen evaluation identities and independent binary ranking oracles without executing a model."""

import copy
import hashlib
import math
from types import SimpleNamespace
from uuid import uuid4

import pytest

from scripts.retrieval_baseline import (
    CORPUS,
    PLAN,
    RecordedEmbeddings,
    RecordedQueries,
    confidence_intervals,
    load_frozen,
    score_rankings,
)
from src.infrastructure.qwen_embedding import EncodedBatch


@pytest.fixture
def sample():
    """Supply independent tiny judgments with multiple relevant sources and a deliberately absent result."""
    corpus = dict(
        documents=[dict(id=name) for name in ["a", "b", "c"]],
        queries=[
            dict(id="first", group="vi", relevant=["a", "c"]),
            dict(id="second", group="en", relevant=["b"]),
        ],
    )
    observations = [
        dict(
            query_id="first",
            ranking=[
                dict(document_id="b", score=0.9),
                dict(document_id="a", score=0.8),
            ],
        ),
        dict(query_id="second", ranking=[]),
    ]
    return corpus, observations


def test_independent_binary_rank_and_missing_oracle(sample):
    """Check partial recall, rank2 reciprocal rank and independent ideal-DCG arithmetic including a miss."""
    corpus, observations = sample
    result = score_rankings(corpus, observations)
    assert result["metrics"]["recall_at_3"] == 0.25
    assert result["metrics"]["mrr_at_10"] == 0.25
    expected = (1 / math.log2(3)) / (1 + 1 / math.log2(3)) / 2
    assert result["metrics"]["ndcg_at_10"] == pytest.approx(expected)
    assert result["queries"][0]["relevant_ranks"] == dict(a=2, c=None)
    assert result["queries"][1]["first_relevant_rank"] is None
    assert result["groups"]["en"]["mrr_at_10"] == 0


@pytest.mark.parametrize(
    "case",
    [
        "missing",
        "extra",
        "duplicate_query",
        "unknown_query",
        "duplicate_doc",
        "foreign_doc",
        "nan",
        "infinity",
        "bool",
        "string",
        "unsorted",
        "too_many",
        "bad_judgment",
        "duplicate_judgment",
        "duplicate_source",
    ],
)
def test_invalid_rankings_are_not_silently_scored(sample, case):
    """Fail incomplete, duplicated, hostile or malformed candidate evidence instead of manufacturing metrics."""
    corpus, rows = copy.deepcopy(sample)
    if case == "missing":
        rows.pop()
    elif case == "extra":
        rows.append(copy.deepcopy(rows[0]))
    elif case == "duplicate_query":
        rows[1]["query_id"] = "first"
    elif case == "unknown_query":
        rows[1]["query_id"] = "unknown"
    elif case == "duplicate_doc":
        rows[0]["ranking"][1]["document_id"] = "b"
    elif case == "foreign_doc":
        rows[0]["ranking"][0]["document_id"] = "foreign"
    elif case in {"nan", "infinity", "bool", "string"}:
        rows[0]["ranking"][0]["score"] = {
            "nan": float("nan"),
            "infinity": float("inf"),
            "bool": True,
            "string": "0.8",
        }[case]
    elif case == "unsorted":
        rows[0]["ranking"][1]["score"] = 0.99
    elif case == "too_many":
        rows[0]["ranking"] *= 6
    elif case == "bad_judgment":
        corpus["queries"][0]["relevant"] = ["unknown"]
    elif case == "duplicate_judgment":
        corpus["queries"][0]["relevant"] = ["a", "a"]
    elif case == "duplicate_source":
        corpus["documents"].append(dict(id="a"))
    with pytest.raises(ValueError):
        score_rankings(corpus, rows)


def test_frozen_corpus_contract_and_group_balance():
    """Verify pre-inference hashes, exact source byte budgets and all36 unique frozen judgments."""
    corpus, plan = load_frozen()
    assert len(corpus["documents"]) == 24 and len(corpus["queries"]) == 36
    assert hashlib.sha256(CORPUS.read_bytes()).hexdigest() == plan["corpus_sha256"]
    assert {
        g: sum(q["group"] == g for q in corpus["queries"])
        for g in ["vi", "en", "cross_language"]
    } == dict(vi=12, en=12, cross_language=12)


@pytest.mark.parametrize("target", ["corpus", "plan"])
def test_modified_frozen_bytes_rejected(tmp_path, target):
    """Reject even whitespace drift in input identities instead of silently rebaselining after inference."""
    corpus, plan = tmp_path / "corpus.json", tmp_path / "plan.json"
    corpus.write_bytes(CORPUS.read_bytes())
    plan.write_bytes(PLAN.read_bytes())
    path = corpus if target == "corpus" else plan
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(ValueError):
        load_frozen(corpus, plan)


def test_bootstrap_reproducible_and_bounded(sample):
    """Keep descriptive query-bootstrap uncertainty deterministic and inside valid metric ranges."""
    rows = score_rankings(*sample)["queries"]
    settings = dict(seed=2701, resamples=2000, percentile=[2.5, 97.5])
    first = confidence_intervals(rows, settings)
    assert first == confidence_intervals(rows, settings)
    assert all(0 <= low <= high <= 1 for low, high in first.values())


@pytest.mark.asyncio
async def test_recorded_vectors_require_exact_input_and_model():
    """Replay exact declared real-encoding records only; unknown texts/models have no fallback."""
    vector = tuple([1.0] + [0.0] * 1023)
    model = "a" * 64
    record = RecordedEmbeddings(
        model,
        ["passage", "instruction query"],
        EncodedBatch(model, (2, 4), (vector, vector)),
    )
    plan = SimpleNamespace(
        job_id=uuid4(),
        model_fingerprint=model,
        points=(SimpleNamespace(text="passage"),),
    )
    assert (await record.encode(plan)).counts == (2,)
    assert await RecordedQueries(record, "instruction ").encode("query") == vector
    plan.model_fingerprint = "b" * 64
    with pytest.raises(ValueError):
        await record.encode(plan)
    with pytest.raises(KeyError):
        await RecordedQueries(record, "instruction ").encode("unknown")
    with pytest.raises(ValueError):
        RecordedEmbeddings(
            model, ["passage"], EncodedBatch(model, (2, 4), (vector, vector))
        )
