"""Score pinned evaluation-only Qwen query/document pairs with complete tokens and finite yes/no probabilities."""

import hashlib
import json
import logging
from importlib.metadata import version

import numpy as np

from scripts.embedding_runtime import ROOT, artifact_path, verify_artifacts

logger = logging.getLogger(__name__)
PROFILE = ROOT / "configs/reranker-qwen-batch4-evaluation.json"
INSTRUCTION = (
    "Given a web search query, retrieve relevant passages that answer the query"
)
PREFIX = '<|im_start|>system\nJudge whether the Document meets the requirements based on the Query and the Instruct provided. Note that the answer can only be "yes" or "no".<|im_end|>\n<|im_start|>user\n'
SUFFIX = "<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\n"


def profile():
    """Read only the pinned evaluation profile without changing selected embedding or deployment settings."""
    return json.loads(PROFILE.read_text())


def pair_text(query, document):
    """Preserve complete nonblank bounded source/query bytes in the pinned official pair instruction."""
    if any(
        not isinstance(text, str) or not text.strip() or len(text.encode()) > 4096
        for text in (query, document)
    ):
        raise ValueError("reranker_pair_invalid")
    return f"<Instruct>: {INSTRUCTION}\n<Query>: {query}\n<Document>: {document}"


def pair_tokens(tokenizer, query, document, max_tokens=512):
    """Count the complete official prefix/pair/suffix without truncation or hidden special-token changes."""
    ids = []
    for text in (PREFIX, pair_text(query, document), SUFFIX):
        ids.extend(tokenizer.encode(text, add_special_tokens=False, truncation=False))
    if not 1 <= len(ids) <= max_tokens:
        raise ValueError("reranker_pair_token_limit")
    return ids


def yes_probability(logits):
    """Normalize exactly two finite float32 no/yes logits using a stable independently testable softmax."""
    if not isinstance(logits, (list, tuple, np.ndarray)) or len(logits) != 2:
        raise ValueError("reranker_logits_invalid")
    if any(isinstance(value, (bool, str)) for value in logits):
        raise ValueError("reranker_logits_invalid")
    values = np.asarray(logits, dtype=np.float32)
    if values.shape != (2,) or not np.isfinite(values).all():
        raise ValueError("reranker_logits_invalid")
    exponential = np.exp(values - np.max(values))
    return float(exponential[1] / exponential.sum())


class QwenRerankerCpu:
    """Own one verified offline CPU BF16 causal-LM session for isolated candidate comparison only."""

    def __init__(self, configuration):
        """Verify immutable assets and CPU/runtime/token identities before loading or scoring any pair."""
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer

        verify_artifacts(configuration)
        if torch.version.cuda is not None:
            raise ValueError("reranker_cpu_runtime_required")
        torch.set_num_threads(2)
        torch.set_num_interop_threads(1)
        self.torch, self.profile = torch, configuration
        directory = artifact_path(configuration, configuration["artifacts"][0]).parent
        self.tokenizer = AutoTokenizer.from_pretrained(
            directory,
            local_files_only=True,
            trust_remote_code=False,
            padding_side="left",
        )
        self.no_id = self.tokenizer.convert_tokens_to_ids("no")
        self.yes_id = self.tokenizer.convert_tokens_to_ids("yes")
        if configuration["class_token_ids"] != {"no": self.no_id, "yes": self.yes_id}:
            raise ValueError("reranker_class_tokens_invalid")
        if self.no_id == self.yes_id or any(
            self.tokenizer.encode(word, add_special_tokens=False) != [identifier]
            for word, identifier in (("no", self.no_id), ("yes", self.yes_id))
        ):
            raise ValueError("reranker_class_tokens_invalid")
        self.model = (
            AutoModelForCausalLM.from_pretrained(
                directory,
                local_files_only=True,
                trust_remote_code=False,
                torch_dtype=torch.bfloat16,
                attn_implementation="sdpa",
            )
            .to("cpu")
            .eval()
        )
        if self.model.config.max_position_embeddings != 40960 or any(
            p.device.type != "cpu" or p.dtype != torch.bfloat16
            for p in self.model.parameters()
        ):
            raise ValueError("reranker_model_contract_invalid")
        self.contract = dict(
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
            no_id=self.no_id,
            yes_id=self.yes_id,
            runtime={
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
        self.fingerprint = hashlib.sha256(
            json.dumps(self.contract, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        logger.info("reranker_evaluation_cpu_loaded")

    def class_logits(self, ids, *, last_only):
        """Compute the same final no/yes logits while optionally avoiding unused vocabulary heads at earlier positions."""
        with self.torch.inference_mode():
            return (
                self.model(
                    input_ids=self.torch.tensor([ids], dtype=self.torch.long),
                    attention_mask=self.torch.ones(
                        (1, len(ids)), dtype=self.torch.long
                    ),
                    use_cache=False,
                    logits_to_keep=1 if last_only else 0,
                )
                .logits[0, -1, [self.no_id, self.yes_id]]
                .float()
                .numpy()
            )

    def reference_parity(self, query, document):
        """Require exact actual final-class logits against the original all-position head on a frozen probe."""
        ids = pair_tokens(
            self.tokenizer, query, document, self.profile["max_pair_tokens"]
        )
        reference = self.class_logits(ids, last_only=False)
        optimized = self.class_logits(ids, last_only=True)
        if not np.array_equal(reference, optimized):
            raise ValueError("reranker_last_logits_reference_mismatch")
        logger.info("reranker_last_logits_reference_exact")
        return dict(
            exact=True,
            reference_logits=reference.tolist(),
            optimized_logits=optimized.tolist(),
        )

    def score(self, query, document):
        """Score complete input with only the required final vocabulary head and no truncation or KV cache."""
        ids = pair_tokens(
            self.tokenizer, query, document, self.profile["max_pair_tokens"]
        )
        logits = self.class_logits(ids, last_only=True)
        return (
            yes_probability(logits),
            len(ids),
            tuple(float(value) for value in logits),
        )

    def score_batch(self, query, documents):
        """Score complete left-padded pairs in the explicit evaluation batch without dropping or reordering sources."""
        if not 1 <= len(documents) <= self.profile["batch_size"]:
            raise ValueError("reranker_batch_invalid")
        encoded = [
            pair_tokens(self.tokenizer, query, text, self.profile["max_pair_tokens"])
            for text in documents
        ]
        width = max(map(len, encoded))
        ids = np.full(
            (len(encoded), width), self.tokenizer.pad_token_id, dtype=np.int64
        )
        mask = np.zeros_like(ids)
        for index, tokens in enumerate(encoded):
            ids[index, -len(tokens) :] = tokens
            mask[index, -len(tokens) :] = 1
        with self.torch.inference_mode():
            logits = (
                self.model(
                    input_ids=self.torch.from_numpy(ids),
                    attention_mask=self.torch.from_numpy(mask),
                    use_cache=False,
                    logits_to_keep=1,
                )
                .logits[:, -1, :][:, [self.no_id, self.yes_id]]
                .float()
                .numpy()
            )
        return [
            (yes_probability(row), len(tokens), tuple(float(value) for value in row))
            for row, tokens in zip(logits, encoded, strict=True)
        ]
