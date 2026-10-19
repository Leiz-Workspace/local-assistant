"""Verify model-specific preprocessing, independent metrics, safe workers and preserved E5 comparison scope."""

import json
from types import SimpleNamespace

import numpy as np
import pytest

from scripts import qwen_embedding_comparison as runner
from scripts import qwen_embedding_evaluation as module


def test_official_query_instruction_and_unchanged_passage():
    """Apply Qwen's exact upstream query prompt without using E5 prefixes or changing source Unicode."""
    profile = module.qwen_profile()
    text = "Việt e\u0301\t\n"
    assert (
        module.input_text(profile, text, "query")
        == "Instruct: Given a web search query, retrieve relevant passages that answer the query\nQuery:"
        + text
    )
    assert module.input_text(profile, text, "passage") == text
    for value in ("", "  ", "x" * 32769):
        with pytest.raises(ValueError, match="embedding_input_invalid"):
            module.input_text(profile, value, "query")


def test_last_attended_token_handles_both_padding_sides():
    """Select the final real token rather than averaging tokens or reading padded values."""
    hidden = np.array(
        [[[999, 999], [4, 0], [0, 3]], [[0, 4], [3, 0], [999, 999]]], dtype=np.float32
    )
    masks = np.array([[0, 1, 1], [1, 1, 0]])
    actual = module.last_token_normalize(hidden, masks, 2)
    np.testing.assert_allclose(actual, [[0, 1], [1, 0]])


@pytest.mark.parametrize(
    "bad", ["nan", "zero", "empty_mask", "invalid_mask", "dimension", "shape"]
)
def test_pooling_refuses_malformed_vectors_and_masks(bad):
    """Reject invalid last-token data before any vector can reach an index."""
    hidden, mask, dimension = np.ones((1, 2, 2)), np.ones((1, 2)), 2
    if bad == "nan":
        hidden[0, 1, 0] = np.nan
    elif bad == "zero":
        hidden[0, 1] = 0
    elif bad == "empty_mask":
        mask[:] = 0
    elif bad == "invalid_mask":
        mask[0, 0] = 2
    elif bad == "dimension":
        dimension = 3
    else:
        mask = np.ones((1, 3))
    with pytest.raises(ValueError, match="embedding_output_invalid"):
        module.last_token_normalize(hidden, mask, dimension)


@pytest.mark.parametrize("count", [512, 513])
def test_real_format_preflight_uses_full_tokens_without_truncation(count):
    """Count instruction/special tokens and refuse overflow instead of shortening the input."""
    received = []

    def encode(text, **options):
        """Emulate a tokenizer count and inspect the exact untruncated call contract."""
        received.append((text, options))
        return list(range(count))

    encoder = SimpleNamespace(
        profile=module.qwen_profile(), tokenizer=SimpleNamespace(encode=encode)
    )
    if count == 512:
        assert len(module.QwenCpu.tokens(encoder, "full query", "query")) == 512
    else:
        with pytest.raises(ValueError, match="embedding_token_limit"):
            module.QwenCpu.tokens(encoder, "full query", "query")
    assert received[0][0].endswith("Query:full query")
    assert received[0][1] == dict(add_special_tokens=True, truncation=False)


def test_topk_metrics_known_ranks_groups_and_multiple_relevance():
    """Check Recall@3/5/10 and MRR@10 against handwritten rank oracles including rank11 misses."""
    documents = [dict(id=f"d{i:02}") for i in range(12)]
    queries = [
        dict(id="q1", group="en", relevant=["d00"]),
        dict(id="q2", group="vi", relevant=["d03", "d06"]),
        dict(id="q3", group="cross", relevant=["d10"]),
    ]
    scores = np.tile(np.arange(12, 0, -1, dtype=float), (3, 1))
    result = module.retrieval_metrics(scores, documents, queries)
    assert result["recall_at_3"] == pytest.approx(1 / 3)
    assert result["recall_at_5"] == pytest.approx(1 / 2)
    assert result["recall_at_10"] == pytest.approx(2 / 3)
    assert result["mrr_at_10"] == pytest.approx((1 + 0.25) / 3)
    assert result["groups"]["vi"]["recall_at_5"] == 0.5
    assert result["queries"][2]["first_relevant_rank"] == 11
    assert result["queries"][1]["relevant_ranks"] == [4, 7]


def test_equal_scores_use_source_id_not_input_order():
    """Make exact similarity ties reproducible across model configurations."""
    result = module.retrieval_metrics(
        np.ones((1, 3)),
        [dict(id=x) for x in ["z", "a", "m"]],
        [dict(id="q", group="vi", relevant=["a"])],
    )
    assert result["queries"][0]["top10"] == ["a", "m", "z"]
    assert result["mrr_at_10"] == 1


@pytest.mark.parametrize("bad", ["nan", "shape", "unknown", "duplicate", "no_queries"])
def test_metric_failures_are_not_reported_as_accuracy(bad):
    """Fail closed on malformed matrices/relevance instead of fabricating model results."""
    documents = [dict(id="a"), dict(id="b")]
    queries = [dict(id="q", group="en", relevant=["a"])]
    scores = np.array([[1.0, 0.0]])
    if bad == "nan":
        scores[0, 0] = np.nan
    elif bad == "shape":
        scores = scores[:, :1]
    elif bad == "unknown":
        queries[0]["relevant"] = ["foreign"]
    elif bad == "duplicate":
        documents[1]["id"] = "a"
    else:
        queries = []
        scores = np.zeros((0, 2))
    with pytest.raises(ValueError):
        module.retrieval_metrics(scores, documents, queries)


def synthetic_run(rank=1):
    """Provide a small controlled report for repetition/error aggregation tests."""
    return dict(
        queries=[dict(query_id="q", relevant_ranks=[rank], top10=["a", "b"])],
        recall_at_3=1,
        recall_at_5=1,
        recall_at_10=1,
        mrr_at_10=1 / rank,
        peak_rss_mib=100,
        warm_query_p95_ms=20,
        meets_d24_reference_gates=True,
    )


def test_repeated_reports_keep_rank_instability_and_worker_failure_visible():
    """Do not hide inconsistent outputs or incomplete repetitions behind a passing aggregate."""
    stable = runner.summarize_runs("qwen", [synthetic_run() for _ in range(3)])
    assert stable["complete"] and stable["rankings_stable"]
    changed = runner.summarize_runs("qwen", [synthetic_run(), synthetic_run(2)])
    assert changed["complete"] and not changed["rankings_stable"]
    failed = runner.summarize_runs(
        "qwen", [synthetic_run(), dict(error="safe_failure")]
    )
    assert not failed["complete"]
    assert failed["runs"][1]["error"] == "safe_failure"


@pytest.mark.parametrize("kind", ["qwen", "e5"])
def test_worker_uses_credential_free_bounded_environment(monkeypatch, kind):
    """Keep Vault/API/DB/Hub/proxy variables out of offline comparison children."""
    monkeypatch.setenv("VAULT_TOKEN", "private-marker")
    monkeypatch.setenv("DATABASE_URL", "private-marker")
    monkeypatch.setenv("HF_TOKEN", "private-marker")
    monkeypatch.setattr(
        runner, "comparison_command", lambda candidate: ["controlled-worker", candidate]
    )

    def execute(command, **options):
        """Inspect a synthetic worker launch without running models or connecting services."""
        env = options["env"]
        assert not any(
            key in env
            for key in [
                "VAULT_TOKEN",
                "DATABASE_URL",
                "HF_TOKEN",
                "HTTP_PROXY",
                "LOCAL_ASSISTANT_QDRANT_PROBE_KEY",
            ]
        )
        assert env["HF_HUB_OFFLINE"] == "1" and env["CUDA_VISIBLE_DEVICES"] == ""
        assert options["timeout"] == 600 and command[-1] == kind
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps(
                dict(
                    candidate=kind,
                    corpus_sha256=runner.hashlib.sha256(
                        runner.CORPUS.read_bytes()
                    ).hexdigest(),
                )
            ),
        )

    monkeypatch.setattr(runner.subprocess, "run", execute)
    assert runner.run_one(kind)["candidate"] == kind


def test_failed_child_does_not_leak_exception_or_stdout(monkeypatch):
    """Retain only a fixed error category from failed worker diagnostics."""
    monkeypatch.setattr(
        runner, "comparison_command", lambda candidate: ["controlled-worker"]
    )

    def execute(*args, **kwargs):
        """Return a controlled failure containing private diagnostics that must never be retained."""
        return SimpleNamespace(returncode=1, stdout="private-marker")

    monkeypatch.setattr(runner.subprocess, "run", execute)
    result = runner.run_one("qwen")
    assert result == dict(candidate="qwen", error="comparison_worker_failed")
    assert "private-marker" not in json.dumps(result)


def test_qwen_command_is_locked_offline_uv_and_e5_uses_existing_runtime(monkeypatch):
    """Preserve project packages while selecting the separately locked Qwen evaluation environment."""
    monkeypatch.setattr(runner.shutil, "which", lambda value: "/trusted/uv")
    assert runner.comparison_command("qwen")[:4] == [
        "/trusted/uv",
        "run",
        "--offline",
        "--frozen",
    ]
    assert runner.comparison_command("e5")[0] == runner.sys.executable
    with pytest.raises(ValueError, match="comparison_candidate_invalid"):
        runner.comparison_command("wrong")


def test_retained_measurements_are_recomputable_and_bound_to_inputs():
    """Recompute retained quality from ranks and verify the frozen corpus and runtime lock."""
    report = json.loads(
        (
            runner.ROOT / "docs/evidence/model-eval-001-qwen-e5-comparison.json"
        ).read_text()
    )
    assert report["complete"] and report["same_inputs"]
    assert (
        report["corpus_sha256"]
        == runner.hashlib.sha256(runner.CORPUS.read_bytes()).hexdigest()
    )
    assert (
        report["script_lock_sha256"]
        == runner.hashlib.sha256(
            (runner.ROOT / "scripts/qwen_embedding_worker.py.lock").read_bytes()
        ).hexdigest()
    )
    for candidate in report["candidates"]:
        assert len(candidate["runs"]) == 3 and candidate["rankings_stable"]
        for run in candidate["runs"]:
            queries = run["queries"]
            for cutoff in (3, 5, 10):
                expected = sum(
                    sum(rank <= cutoff for rank in query["relevant_ranks"])
                    / len(query["relevant_ranks"])
                    for query in queries
                ) / len(queries)
                assert run[f"recall_at_{cutoff}"] == pytest.approx(expected)
            expected_mrr = sum(
                1 / query["first_relevant_rank"]
                if query["first_relevant_rank"] <= 10
                else 0
                for query in queries
            ) / len(queries)
            assert run["mrr_at_10"] == pytest.approx(expected_mrr)
            assert run["qdrant_ingest_throughput"] is None
            assert run["qdrant_disk_index_bytes"] is None


def test_transition_proposal_preserves_original_e5_rollback():
    """Preserve the original review artifact and exact E5 rollback after approved selection."""
    proposal = json.loads(
        (
            runner.ROOT / "docs/evidence/model-eval-001-transition-proposal.json"
        ).read_text()
    )
    current = (runner.ROOT / "configs/embedding-e5-rollback.json").read_bytes()
    assert proposal["approval_status"] == "OWNER_APPROVAL_PENDING"
    assert proposal["approved_by"] is None
    assert (
        proposal["expected_current_configuration_sha256"]
        == runner.hashlib.sha256(current).hexdigest()
    )
    assert proposal["rollback_configuration"] == json.loads(current)
    assert proposal["proposed_configuration"] != json.loads(current)
    assert proposal["proposed_configuration"]["candidate"]["dimension"] == 1024


def test_selected_qwen_matches_approved_pins_runtime_and_isolated_space():
    """Verify approved selection identity, exact rollback and honest undeployed state."""
    selected_path = runner.ROOT / "configs/embedding-selected.json"
    selected = json.loads(selected_path.read_text())
    approval = json.loads((runner.ROOT / selected["approval_record"]).read_text())
    profile = module.qwen_profile()
    proposal = json.loads((runner.ROOT / approval["proposal"]).read_text())
    assert approval["approval_status"] == "OWNER_APPROVED_SELECTION_APPLIED"
    assert (
        approval["selected_configuration_sha256"]
        == runner.hashlib.sha256(selected_path.read_bytes()).hexdigest()
    )
    assert selected["status"] == "selected_not_deployed"
    assert selected["candidate"] == profile
    assert selected["candidate"] == proposal["proposed_configuration"]["candidate"]
    assert selected["runtime"]["device"] == "cpu"
    assert selected["runtime"]["max_tokens"] == 512
    assert selected["runtime"]["query_prefix"] == profile["query_prefix"]
    assert selected["runtime"]["passage_prefix"] == ""
    assert selected["runtime"]["distance"] == "Cosine"
    assert (
        selected["collection"]["model_fingerprint"]
        == selected["runtime"]["fingerprint"]
        == approval["model_fingerprint"]
    )
    assert selected["collection"]["create"]["vectors"]["dense"]["size"] == 1024
    old = json.loads(
        (runner.ROOT / approval["rollback_configuration_path"]).read_text()
    )
    assert old == proposal["rollback_configuration"]
    assert (
        selected["collection"]["collection_name"]
        != old["collection"]["collection_name"]
    )
    assert all(
        approval[key] is False
        for key in ("deployed", "collections_mutated", "data_migrated")
    )
