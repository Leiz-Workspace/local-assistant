"""Encode the pinned official Qwen embedding candidate and independently score a non-mutating comparison."""

import hashlib
import json
import logging
from importlib.metadata import version

import numpy as np

from scripts.embedding_runtime import ROOT, artifact_path, verify_artifacts

logger = logging.getLogger(__name__)
QWEN_CONFIG = ROOT / "configs/embedding-qwen-evaluation.json"


def qwen_profile():
    """Read the separately authorized candidate without changing the selected E5 registry."""
    return json.loads(QWEN_CONFIG.read_text())


def input_text(profile, text, kind):
    """Apply official query instruction and leave exact document text unprefixed."""
    if (
        kind not in {"query", "passage"}
        or not isinstance(text, str)
        or not text.strip()
        or len(text.encode()) > 32768
    ):
        raise ValueError("embedding_input_invalid")
    return profile[kind + "_prefix"] + text


def last_token_normalize(hidden, mask, dimension):
    """Select each last attended token for left/right padding and normalize float32 vectors."""
    if (
        hidden.ndim != 3
        or hidden.shape[:2] != mask.shape
        or hidden.shape[-1] != dimension
        or not np.isfinite(hidden).all()
        or not np.isin(mask, [0, 1]).all()
        or np.any(mask.sum(axis=1) <= 0)
    ):
        raise ValueError("embedding_output_invalid")
    positions = np.where(mask == 1, np.arange(mask.shape[1]), -1).max(axis=1)
    vectors = hidden[np.arange(len(hidden)), positions].astype(np.float32)
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    if not np.isfinite(norms).all() or np.any(norms < 1e-12):
        raise ValueError("embedding_output_invalid")
    return vectors / norms


def retrieval_metrics(scores, documents, queries):
    """Score all relevant ranks and Recall@3/5/10/MRR@10 with per-group metrics and stable ties."""
    ids = [d["id"] for d in documents]
    if (
        scores.shape != (len(queries), len(ids))
        or not np.isfinite(scores).all()
        or len(ids) != len(set(ids))
        or not queries
    ):
        raise ValueError("comparison_scores_invalid")
    rows = []
    for row, query in zip(scores, queries, strict=True):
        relevant = set(query["relevant"])
        if not relevant or not relevant.issubset(ids):
            raise ValueError("comparison_relevance_invalid")
        order = sorted(
            range(len(ids)), key=lambda index: (-float(row[index]), ids[index])
        )
        ranks = [rank for rank, index in enumerate(order, 1) if ids[index] in relevant]
        metrics = {
            f"recall_at_{k}": sum(rank <= k for rank in ranks) / len(relevant)
            for k in (3, 5, 10)
        }
        metrics["mrr_at_10"] = 1 / min(ranks) if min(ranks) <= 10 else 0
        rows.append(
            dict(
                query_id=query["id"],
                group=query["group"],
                first_relevant_rank=min(ranks),
                relevant_ranks=ranks,
                top10=[ids[i] for i in order[:10]],
                **metrics,
            )
        )
    keys = ("recall_at_3", "recall_at_5", "recall_at_10", "mrr_at_10")
    overall = {key: float(np.mean([r[key] for r in rows])) for key in keys}
    groups = {
        group: {
            key: float(np.mean([r[key] for r in rows if r["group"] == group]))
            for key in keys
        }
        for group in sorted({r["group"] for r in rows})
    }
    return dict(**overall, groups=groups, queries=rows)


def qwen_fingerprint(profile):
    """Bind the candidate to pinned assets, pooling, precision and isolated CPU package versions."""
    contract = dict(
        profile=profile,
        format="official-safetensors-bf16-cpu",
        pooling="last_attended_token_float32",
        normalization="l2",
        attention="sdpa",
        use_cache=False,
        runtime={
            name: version(name)
            for name in ("torch", "transformers", "numpy", "tokenizers", "safetensors")
        },
    )
    return hashlib.sha256(
        json.dumps(contract, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


class QwenCpu:
    """Own an offline official CPU BF16 Qwen session for evaluation only, with no deployment side effects."""

    def __init__(self, profile):
        """Verify local artifacts and disable remote code/network/GPU/cache before loading weights."""
        import torch
        from transformers import AutoModel, AutoTokenizer

        verify_artifacts(profile)
        if torch.version.cuda is not None:
            raise ValueError("comparison_cpu_runtime_required")
        torch.set_num_threads(2)
        torch.set_num_interop_threads(1)
        self.profile = profile
        self.torch = torch
        directory = artifact_path(profile, profile["artifacts"][0]).parent
        self.tokenizer = AutoTokenizer.from_pretrained(
            directory,
            local_files_only=True,
            trust_remote_code=False,
            padding_side="left",
        )
        self.model = (
            AutoModel.from_pretrained(
                directory,
                local_files_only=True,
                trust_remote_code=False,
                torch_dtype=torch.bfloat16,
                attn_implementation="sdpa",
            )
            .to("cpu")
            .eval()
        )
        if (
            self.model.config.hidden_size != profile["dimension"]
            or self.model.config.max_position_embeddings
            != profile["model_context_tokens"]
            or any(
                p.device.type != "cpu" or p.dtype != torch.bfloat16
                for p in self.model.parameters()
            )
        ):
            raise ValueError("comparison_qwen_model_contract")
        logger.info("qwen_comparison_cpu_loaded dimension=%d", profile["dimension"])

    def tokens(self, text, kind):
        """Count complete official-format input tokens and refuse overflow without truncation."""
        ids = self.tokenizer.encode(
            input_text(self.profile, text, kind),
            add_special_tokens=True,
            truncation=False,
        )
        if len(ids) > self.profile["comparison_max_tokens"]:
            raise ValueError("embedding_token_limit")
        return ids

    def encode(self, texts, kind):
        """Encode fixed batches with left padding, no KV cache and last-token unit vectors."""
        if not texts or len(texts) > 256:
            raise ValueError("embedding_input_invalid")
        outputs = []
        for offset in range(0, len(texts), 4):
            ids = [self.tokens(text, kind) for text in texts[offset : offset + 4]]
            length = max(map(len, ids))
            batch = np.full(
                (len(ids), length), self.tokenizer.pad_token_id, dtype=np.int64
            )
            mask = np.zeros_like(batch)
            for row, tokens in enumerate(ids):
                batch[row, -len(tokens) :] = tokens
                mask[row, -len(tokens) :] = 1
            with self.torch.inference_mode():
                hidden = (
                    self.model(
                        input_ids=self.torch.from_numpy(batch),
                        attention_mask=self.torch.from_numpy(mask),
                        use_cache=False,
                    )
                    .last_hidden_state.float()
                    .numpy()
                )
            outputs.append(
                last_token_normalize(hidden, mask, self.profile["dimension"])
            )
        result = np.concatenate(outputs)
        logger.info("qwen_comparison_encoded kind=%s count=%d", kind, len(texts))
        return result
