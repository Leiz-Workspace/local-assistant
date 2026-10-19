"""Verify complete official-pair token boundaries, independent logits and hostile candidate comparison replies."""

import asyncio
import copy
import hashlib
import json
import math

import pytest

from scripts import reranker_comparison as comparison
from scripts.qwen_reranker_runtime import (
    INSTRUCTION,
    PREFIX,
    SUFFIX,
    pair_text,
    pair_tokens,
    profile,
    yes_probability,
)


class CountingTokenizer:
    """Provide an independent exact token-length oracle without model/tokenizer execution."""

    def __init__(self, total):
        """Assign complete prefix/pair/suffix lengths to test the total-input policy."""
        self.total = total
        self.calls = []

    def encode(self, text, **options):
        """Require explicit no-truncation/no-special insertion and return the declared full token contribution."""
        self.calls.append((text, options))
        assert options == dict(add_special_tokens=False, truncation=False)
        return [1] * (
            10 if text == PREFIX else 12 if text == SUFFIX else self.total - 22
        )


@pytest.mark.parametrize("count", [23, 512, 513])
def test_full_pair_token_boundary(count):
    """Accept the entire512-token pair and refuse513 without dropping prefix/suffix or source bytes."""
    tokenizer = CountingTokenizer(count)
    if count == 513:
        with pytest.raises(ValueError):
            pair_tokens(tokenizer, "query", "document")
    else:
        assert len(pair_tokens(tokenizer, "query", "document")) == count
        assert (
            tokenizer.calls[1][0]
            == f"<Instruct>: {INSTRUCTION}\n<Query>: query\n<Document>: document"
        )


@pytest.mark.parametrize(
    "logits,expected",
    [([0, 0], 0.5), ([0, math.log(3)], 0.75), ([1000, 0], 0), ([0, 1000], 1)],
)
def test_independent_yes_no_softmax(logits, expected):
    """Check stable two-class probability against arithmetic oracles instead of embedding pooling."""
    assert yes_probability(logits) == pytest.approx(expected, abs=1e-7)


@pytest.mark.parametrize(
    "logits",
    [[], [1], [0, 0, 0], [True, 0], ["0", 1], [float("nan"), 0], [0, float("inf")]],
)
def test_nonfinite_or_malformed_logits_rejected(logits):
    """Reject invalid class replies without accepting coerced strings/bools or nonfinite probabilities."""
    with pytest.raises(ValueError):
        yes_probability(logits)


def good_reply(request):
    """Build explicit fault-test scores/contracts for protocol checks without claiming an actual model result."""
    configuration = profile()
    contract = dict(
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
        no_id=2152,
        yes_id=9693,
        runtime=dict(
            torch="2.10.0+cpu",
            transformers="4.57.6",
            numpy="2.5.4",
            tokenizers="0.22.2",
            safetensors="0.8.0",
        ),
    )
    rounds = [
        [
            dict(
                query_id=query["id"],
                wall_seconds=0.1,
                documents=[
                    dict(document_id=row["id"], score=0.5, tokens=100, logits=[0, 0])
                    for row in query["documents"]
                ],
            )
            for query in request["queries"]
        ]
        for _ in range(3)
    ]
    return dict(
        profile_sha256=request["profile_sha256"],
        model_fingerprint=hashlib.sha256(
            json.dumps(contract, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
        contract=contract,
        cold_load_seconds=1,
        last_logits_reference_parity=dict(
            exact=True, reference_logits=[0, 0], optimized_logits=[0, 0]
        ),
        peak_candidate_rss_mib=1500,
        candidate_gpu_allocation_bytes=0,
        gpu_measurement="explicit CPU fault fixture",
        rounds=rounds,
    )


@pytest.mark.parametrize(
    "case",
    [
        "profile",
        "parity",
        "model",
        "runtime",
        "class_ids",
        "rounds",
        "query",
        "document",
        "partial",
        "score_nan",
        "score_bool",
        "score_logit_drift",
        "tokens",
        "rss_nan",
        "device",
        "duplicate",
        "extra",
    ],
)
def test_tampered_or_incomplete_replies_rejected(case):
    """Refuse foreign identities, partial candidates, inconsistent logits or invalid resource evidence."""
    request = comparison.build_request()
    reply = good_reply(request)
    if case == "parity":
        reply["last_logits_reference_parity"]["optimized_logits"] = [1, 0]
    elif case == "profile":
        reply["profile_sha256"] = "private-marker"
    elif case == "model":
        reply["model_fingerprint"] = "0" * 64
    elif case == "runtime":
        reply["contract"]["runtime"]["torch"] = "other"
    elif case == "class_ids":
        reply["contract"]["yes_id"] = reply["contract"]["no_id"]
    elif case == "rounds":
        reply["rounds"].pop()
    elif case == "query":
        reply["rounds"][0][0]["query_id"] = "foreign"
    elif case == "document":
        reply["rounds"][0][0]["documents"][0]["document_id"] = "foreign"
    elif case == "partial":
        reply["rounds"][0][0]["documents"].pop()
    elif case == "score_nan":
        reply["rounds"][0][0]["documents"][0]["score"] = float("nan")
    elif case == "score_bool":
        reply["rounds"][0][0]["documents"][0]["score"] = True
    elif case == "score_logit_drift":
        reply["rounds"][0][0]["documents"][0]["score"] = 0.8
    elif case == "tokens":
        reply["rounds"][0][0]["documents"][0]["tokens"] = 513
    elif case == "rss_nan":
        reply["peak_candidate_rss_mib"] = float("nan")
    elif case == "device":
        reply["candidate_gpu_allocation_bytes"] = 1
    elif case == "duplicate":
        reply["rounds"][0][0]["documents"][1] = copy.deepcopy(
            reply["rounds"][0][0]["documents"][0]
        )
    elif case == "extra":
        reply["private_diagnostic"] = "private-marker"
    with pytest.raises(ValueError, match="reranker_evaluation_reply_invalid"):
        comparison.validate_reply(request, reply)


def test_fixed_source_candidates_and_failed_gates_are_retained():
    """Bind360 pairs to exact T01 source hashes and report losing model/resource gates without adoption."""
    request = comparison.build_request()
    assert len(request["queries"]) == 36 and all(
        len(row["documents"]) == 10 for row in request["queries"]
    )
    assert all(
        set(query) == {"id", "text", "documents"} for query in request["queries"]
    )
    reply = good_reply(request)
    reply["peak_candidate_rss_mib"] = 5000
    result = comparison.compare_reply(request, reply)
    assert result["complete"] and not result["all_resource_gates_met"]
    assert not result["adoption_authorized"]
    assert all(
        set(row["document_id"] for row in scored["queries"][0]["ranking"])
        == set(row["id"] for row in request["queries"][0]["documents"])
        for scored in result["runs"]
    )
    assert [
        row["document_id"] for row in result["runs"][0]["queries"][0]["ranking"]
    ] == sorted(row["id"] for row in request["queries"][0]["documents"])


@pytest.mark.asyncio
async def test_frozen_offline_stdin_and_secret_free_environment(monkeypatch):
    """Verify private input goes only to stdin and credentials/proxies never reach the candidate process."""
    request = comparison.build_request()
    reply = good_reply(request)
    captured = {}

    class Child:
        """Represent an already completed child for a controlled launch-protocol check."""

        pid = 123456789
        returncode = 0

        async def communicate(self, body=None):
            """Capture complete stdin and return only a valid controlled reply."""
            captured["body"] = body
            return json.dumps(reply).encode(), b"private diagnostics"

    async def launch(*args, **kwargs):
        """Record the exact immutable command/environment and avoid any real process launch."""
        captured["args"], captured["kwargs"] = args, kwargs
        return Child()

    monkeypatch.setenv("VAULT_TOKEN", "private-marker")
    monkeypatch.setenv("HTTPS_PROXY", "private-marker")
    monkeypatch.setattr(comparison.asyncio, "create_subprocess_exec", launch)
    result = await comparison.RerankerEvaluation().run(request)
    assert result == reply and json.loads(captured["body"]) == request
    assert "--offline" in captured["args"] and "--frozen" in captured["args"]
    assert captured["kwargs"]["start_new_session"]
    assert "private-marker" not in json.dumps(captured["kwargs"]["env"])
    assert "VAULT_TOKEN" not in captured["kwargs"]["env"]


@pytest.mark.asyncio
async def test_cancel_during_launch_joins_owned_group_before_release(monkeypatch):
    """Kill and join a launch completing after cancellation before reopening the evaluation admission."""
    started = asyncio.Event()
    release = asyncio.Event()
    joined = asyncio.Event()
    killed = []

    class Child:
        """Represent only an owned fake process for the launch-cancellation race."""

        pid = 123456789
        returncode = None

        async def communicate(self, body=None):
            """Record pipe join after the parent kills the captured group."""
            self.returncode = -9
            joined.set()
            return b"", b""

    async def launch(*args, **kwargs):
        """Wait for cancellation before returning an owned handle, reproducing the launch gap."""
        started.set()
        await release.wait()
        return Child()

    monkeypatch.setattr(comparison.asyncio, "create_subprocess_exec", launch)
    monkeypatch.setattr(comparison.os, "killpg", lambda pid, sig: killed.append(pid))
    adapter = comparison.RerankerEvaluation()
    work = asyncio.create_task(adapter.run(comparison.build_request()))
    await started.wait()
    work.cancel()
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await work
    assert killed == [123456789] and joined.is_set() and not adapter.admission.locked()


@pytest.mark.parametrize("case", ["source", "scope"])
def test_execution_manifest_refuses_drift(monkeypatch, tmp_path, case):
    """Reject changed source hashes or unauthorized adoption scope before any process launch."""
    manifest = json.loads(comparison.EXECUTION.read_text())
    if case == "scope":
        manifest["scope"] = "DEPLOY"
    else:
        manifest["sha256"]["scripts/qwen_reranker_runtime.py"] = "0" * 64
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest))
    monkeypatch.setattr(comparison, "EXECUTION", path)
    with pytest.raises(ValueError, match="reranker_execution_manifest_invalid"):
        comparison.verify_execution()


def test_left_padded_batch_preserves_token_order_masks_and_source_alignment():
    """Compare batched input/mask/row outputs against independent golden arrays without loading model weights."""
    from contextlib import nullcontext
    from types import SimpleNamespace

    import numpy as np

    from scripts.qwen_reranker_runtime import QwenRerankerCpu

    class Tokenizer:
        """Expose independent short/long pair token sequences for a padding oracle."""

        pad_token_id = 0

        def encode(self, text, **options):
            """Return explicit prefix/suffix/body IDs without silently padding or truncating."""
            if text == PREFIX:
                return [10]
            if text == SUFFIX:
                return [20]
            return [21, 22] if text.endswith("short") else [31, 32, 33]

    class Tensor:
        """Model only indexing/float/numpy tensor operations needed by the batch protocol test."""

        def __init__(self, data):
            """Retain an independent finite array with no Torch dependency."""
            self.data = data

        def __getitem__(self, key):
            """Return an independent view preserving the model's output dimensions."""
            return Tensor(self.data[key])

        def float(self):
            """Keep this test array already represented as floating-point values."""
            return self

        def numpy(self):
            """Expose the controlled logits only after the batch input assertions have passed."""
            return self.data

    def model(**arguments):
        """Require exact golden left padding and attention masks before returning declared class logits."""
        assert arguments["input_ids"].tolist() == [
            [0, 10, 21, 22, 20],
            [10, 31, 32, 33, 20],
        ]
        assert arguments["attention_mask"].tolist() == [
            [0, 1, 1, 1, 1],
            [1, 1, 1, 1, 1],
        ]
        assert arguments["logits_to_keep"] == 1 and arguments["use_cache"] is False
        return SimpleNamespace(
            logits=Tensor(
                np.array([[[0, math.log(3)]], [[math.log(3), 0]]], dtype=np.float32)
            )
        )

    instance = QwenRerankerCpu.__new__(QwenRerankerCpu)
    instance.profile = dict(batch_size=4, max_pair_tokens=512)
    instance.tokenizer = Tokenizer()
    instance.no_id = 0
    instance.yes_id = 1
    instance.torch = SimpleNamespace(
        inference_mode=nullcontext, from_numpy=lambda data: data
    )
    instance.model = model
    result = instance.score_batch("query", ["short", "long"])
    assert [row[1] for row in result] == [4, 5]
    assert [row[0] for row in result] == pytest.approx([0.75, 0.25], abs=1e-7)
    with pytest.raises(ValueError):
        instance.score_batch("query", ["short"] * 5)
