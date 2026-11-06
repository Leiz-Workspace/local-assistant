"""Verify independent retrieval scoring, strict pooling/token guards, pinned provisioning and choice rules."""

import copy
import hashlib
import json
from types import SimpleNamespace

import httpx
import numpy as np
import pytest

from scripts import embedding_runtime as runtime
from scripts.embedding_acceptance import candidate_gate, rank_metrics, select_candidate


def test_rank_oracle_multiple_relevance_and_tie_breaking():
    """Score known exact ranks, fractional recall and ID-based ties independently of an encoder."""
    docs = [dict(id="b"), dict(id="a"), dict(id="c"), dict(id="d")]
    queries = [
        dict(id="q1", group="en", relevant=["b"]),
        dict(id="q2", group="vi", relevant=["a", "d"]),
    ]
    result = rank_metrics(np.array([[1, 1, 0, -1], [0, 3, 2, 1]]), docs, queries)
    assert result["queries"][0]["first_relevant_rank"] == 2
    assert result["recall_at_3"] == 1
    assert result["mrr_at_10"] == 0.75
    assert result["group_recall_at_3"] == dict(en=1, vi=1)


@pytest.mark.parametrize("bad", ["nan", "shape", "unknown", "duplicate"])
def test_rank_oracle_refuses_invalid_scores_or_labels(bad):
    """Refuse malformed matrices/relevance rather than manufacturing a passing benchmark."""
    docs, queries = (
        [dict(id="a"), dict(id="b")],
        [dict(id="q", group="en", relevant=["a"])],
    )
    scores = np.array([[1.0, 0.0]])
    if bad == "nan":
        scores[0, 0] = np.nan
    elif bad == "shape":
        scores = scores[:, :1]
    elif bad == "unknown":
        queries[0]["relevant"] = ["foreign"]
    else:
        docs[1]["id"] = "a"
    with pytest.raises(ValueError):
        rank_metrics(scores, docs, queries)


def eligible(candidate="small", mrr=0.90, memory=500):
    """Construct a controlled numeric candidate for testing the documented selection policy."""
    return dict(
        candidate=candidate,
        eligible=True,
        recall_at_3=0.95,
        mrr_at_10=mrr,
        group_recall_at_3=dict(en=1, vi=0.9, cross=0.9),
        peak_rss_mib=memory,
        warm_query_p95_ms=20,
        overflow_rejected=True,
        repeat_max_absolute_delta=0,
    )


def test_selection_prefers_memory_only_inside_quality_tolerance():
    """Keep a substantially better larger model, then favor memory when accuracy is close."""
    assert select_candidate([eligible(), eligible("base", 0.97, 800)], 0.05) == "base"
    assert select_candidate([eligible(), eligible("base", 0.94, 800)], 0.05) == "small"
    rejected = eligible()
    rejected["eligible"] = False
    assert select_candidate([rejected], 0.05) is None


@pytest.mark.parametrize(
    "bad",
    ["recall", "mrr", "group", "memory", "latency", "overflow", "repeat", "error"],
)
def test_predeclared_gate_rejects_each_failed_requirement(bad):
    """Ensure aggregate accuracy cannot conceal language/resource/token or worker failures."""
    result = eligible()
    gates = dict(
        recall_at_3=0.9,
        mrr_at_10=0.8,
        group_recall_at_3=0.8,
        peak_rss_mib=2048,
        warm_query_p95_ms=500,
    )
    assert candidate_gate(result, gates)
    key, value = {
        "recall": ("recall_at_3", 0.89),
        "mrr": ("mrr_at_10", 0.79),
        "group": ("group_recall_at_3", dict(vi=0.79)),
        "memory": ("peak_rss_mib", 2049),
        "latency": ("warm_query_p95_ms", 501),
        "overflow": ("overflow_rejected", False),
        "repeat": ("repeat_max_absolute_delta", 0.01),
        "error": ("error", "safe_failure"),
    }[bad]
    result[key] = value
    assert not candidate_gate(result, gates)


def test_masked_pooling_matches_hand_calculated_unit_vector():
    """Exclude padded token values from the mean and normalize the known vector exactly."""
    hidden = np.array([[[3.0, 0.0], [0.0, 4.0], [1000.0, 1000.0]]])
    actual = runtime.mean_normalize(hidden, np.array([[1, 1, 0]]), 2)
    np.testing.assert_allclose(actual, [[0.6, 0.8]], atol=1e-7)


@pytest.mark.parametrize(
    "bad", ["nan", "zero", "empty_mask", "negative_mask", "dimension"]
)
def test_pooling_refuses_invalid_or_empty_outputs(bad):
    """Reject nonfinite/zero/wrong-size vectors and malformed attention masks before indexing."""
    hidden, mask, dimension = np.ones((1, 2, 2)), np.ones((1, 2)), 2
    if bad == "nan":
        hidden[0, 0, 0] = np.nan
    elif bad == "zero":
        hidden[:] = 0
    elif bad == "empty_mask":
        mask[:] = 0
    elif bad == "negative_mask":
        mask[0, 0] = -1
    else:
        dimension = 3
    with pytest.raises(ValueError, match="embedding_output_invalid"):
        runtime.mean_normalize(hidden, mask, dimension)


def test_prefix_token_limit_includes_special_tokens_without_truncation():
    """Reject513 actual tokens and retain the exact lexical input/prefix passed to the tokenizer."""
    seen = []

    def encode(text):
        """Emulate exact tokenizer counts while preserving the received full input."""
        seen.append(text)
        return SimpleNamespace(ids=list(range(513 if "over" in text else 512)))

    encoder = SimpleNamespace(tokenizer=SimpleNamespace(encode=encode))
    assert len(runtime.CpuE5.tokens(encoder, "full text", "query").ids) == 512
    with pytest.raises(ValueError, match="embedding_token_limit"):
        runtime.CpuE5.tokens(encoder, "over limit text", "passage")
    assert seen == ["query: full text", "passage: over limit text"]
    with pytest.raises(ValueError, match="embedding_input_invalid"):
        runtime.CpuE5.tokens(encoder, "   ", "query")


def test_fingerprint_binds_revision_tokenizer_and_runtime(monkeypatch):
    """Invalidate vector identity on changed artifact, model revision or package runtime."""
    original = runtime.profiles()[0]
    before = runtime.fingerprint(original)
    changed = copy.deepcopy(original)
    changed["artifacts"][1]["sha256"] = "a" * 64
    assert runtime.fingerprint(changed) != before
    changed = dict(original, revision="b" * 40)
    assert runtime.fingerprint(changed) != before
    monkeypatch.setattr(runtime, "version", lambda name: "different-runtime")
    assert runtime.fingerprint(original) != before


@pytest.mark.parametrize("case", ["valid", "oversize", "wrong_hash", "missing"])
def test_pinned_provisioning_exact_hash_size_and_cleanup(monkeypatch, tmp_path, case):
    """Publish only exact downloaded bytes and leave no partial cache after rejection."""
    data = b"pinned model data"
    artifact = dict(
        local="model.onnx",
        source="model.onnx",
        bytes=len(data),
        sha256=hashlib.sha256(data).hexdigest(),
    )
    profile = dict(
        id="synthetic",
        repository="public/test",
        revision="a" * 40,
        artifacts=[artifact],
    )
    monkeypatch.setattr(runtime, "ROOT", tmp_path)
    payload = (
        data + b"!"
        if case == "oversize"
        else b"x" * len(data)
        if case == "wrong_hash"
        else data
    )

    def transport(request):
        """Serve trusted synthetic model bytes without any external request or authentication."""
        assert "authorization" not in request.headers
        return httpx.Response(200, content=payload)

    original = httpx.Client

    def client(**kwargs):
        """Inject an isolated public download transport while preserving request safety options."""
        assert kwargs["trust_env"] is False
        return original(**kwargs, transport=httpx.MockTransport(transport))

    monkeypatch.setattr(runtime.httpx, "Client", client)
    if case == "missing":
        with pytest.raises(ValueError, match="embedding_artifact_mismatch"):
            runtime.verify_artifacts(profile)
    elif case == "valid":
        runtime.provision(profile)
        runtime.verify_artifacts(profile)
        assert runtime.artifact_path(profile, artifact).read_bytes() == data
    else:
        with pytest.raises(ValueError):
            runtime.provision(profile)
        assert not runtime.artifact_path(profile, artifact).exists()
        assert not list(runtime.artifact_path(profile, artifact).parent.iterdir())


def test_frozen_corpus_has_independent_bilingual_relevance():
    """Validate coverage/unique labels without generating relevance from model scores."""
    from scripts.embedding_acceptance import CORPUS

    corpus = json.loads(CORPUS.read_text())
    assert len(corpus["documents"]) == 20 and len(corpus["queries"]) == 40
    assert {q["group"] for q in corpus["queries"]} == {"en", "vi", "cross"}
    assert len({q["id"] for q in corpus["queries"]}) == 40
    assert all(q["relevant"] for q in corpus["queries"])
