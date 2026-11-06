"""Provide pinned CPU-only E5 artifact provisioning and strict synthetic benchmark encoding."""

import hashlib
import json
import logging
import os
import tempfile
from importlib.metadata import version
from pathlib import Path

import httpx
import numpy as np

logger = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parents[1]
PROFILES = ROOT / "configs/embedding-candidates.json"
MAX_TOKENS = 512
BATCH_SIZE = 4


def profiles():
    """Load the repository-controlled fixed candidate inventory."""
    return json.loads(PROFILES.read_text())["candidates"]


def artifact_path(profile, artifact):
    """Locate one pinned artifact only inside the ignored embedding cache."""
    return ROOT / "models/embedding" / profile["id"] / artifact["local"]


def digest_file(path):
    """Hash a large model without reading its entire file into Python memory."""
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for data in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(data)
    return digest.hexdigest()


def verify_artifacts(profile):
    """Refuse absent or changed model/tokenizer bytes before loading executable graph data."""
    for artifact in profile["artifacts"]:
        path = artifact_path(profile, artifact)
        if (
            not path.is_file()
            or path.stat().st_size != artifact["bytes"]
            or digest_file(path) != artifact["sha256"]
        ):
            raise ValueError("embedding_artifact_mismatch")
    logger.info("embedding_artifacts_verified candidate=%s", profile["id"])


def provision(profile):
    """Explicitly download only pinned public artifacts with exact size/hash checks and atomic publish."""
    for artifact in profile["artifacts"]:
        path = artifact_path(profile, artifact)
        if (
            path.is_file()
            and path.stat().st_size == artifact["bytes"]
            and digest_file(path) == artifact["sha256"]
        ):
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as target:
                temporary = Path(target.name)
                digest, total = hashlib.sha256(), 0
                url = f"https://huggingface.co/{profile['repository']}/resolve/{profile['revision']}/{artifact['source']}?download=true"
                with (
                    httpx.Client(
                        trust_env=False, follow_redirects=True, timeout=120
                    ) as client,
                    client.stream("GET", url) as response,
                ):
                    response.raise_for_status()
                    for data in response.iter_bytes(1024 * 1024):
                        total += len(data)
                        if total > artifact["bytes"]:
                            raise ValueError("embedding_download_size_mismatch")
                        digest.update(data)
                        target.write(data)
                if (
                    total != artifact["bytes"]
                    or digest.hexdigest() != artifact["sha256"]
                ):
                    raise ValueError("embedding_download_hash_mismatch")
                target.flush()
                os.fsync(target.fileno())
            temporary.replace(path)
            logger.info(
                "embedding_artifact_provisioned candidate=%s bytes=%d",
                profile["id"],
                total,
            )
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
    verify_artifacts(profile)


def fingerprint(profile):
    """Bind vector identity to complete model/tokenizer/preprocessing runtime-format semantics."""
    contract = dict(
        profile=profile,
        format="onnx-qint8-avx512-vnni",
        max_tokens=MAX_TOKENS,
        query_prefix="query: ",
        passage_prefix="passage: ",
        pooling="attention_mask_mean",
        normalization="l2",
        version="e5-cpu-v1",
        runtime={
            name: version(name) for name in ("onnxruntime", "tokenizers", "numpy")
        },
    )
    return hashlib.sha256(
        json.dumps(contract, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def mean_normalize(hidden, mask, dimension):
    """Pool only attended tokens and reject invalid vectors before unit normalization."""
    if (
        hidden.ndim != 3
        or hidden.shape[:2] != mask.shape
        or hidden.shape[2] != dimension
        or not np.isfinite(hidden).all()
        or not np.isfinite(mask).all()
        or not np.isin(mask, [0, 1]).all()
        or np.any(mask.sum(axis=1) <= 0)
    ):
        raise ValueError("embedding_output_invalid")
    pooled = (hidden * mask[..., None]).sum(axis=1) / mask.sum(axis=1)[:, None]
    norms = np.linalg.norm(pooled, axis=1, keepdims=True)
    if not np.isfinite(norms).all() or np.any(norms < 1e-12):
        raise ValueError("embedding_output_invalid")
    return (pooled / norms).astype(np.float32)


class CpuE5:
    """Own one verified CPU ONNX session with bounded tokenization/batching and no truncation."""

    def __init__(self, profile):
        """Load trusted artifacts on CPU with two inference threads and one sequential inter-op lane."""
        import onnxruntime as ort
        from tokenizers import Tokenizer

        verify_artifacts(profile)
        self.profile = profile
        self.tokenizer = Tokenizer.from_file(
            str(artifact_path(profile, profile["artifacts"][1]))
        )
        self.tokenizer.no_truncation()
        self.tokenizer.no_padding()
        options = ort.SessionOptions()
        options.intra_op_num_threads = 2
        options.inter_op_num_threads = 1
        options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
        self.session = ort.InferenceSession(
            str(artifact_path(profile, profile["artifacts"][0])),
            options,
            providers=["CPUExecutionProvider"],
        )
        if self.session.get_providers() != ["CPUExecutionProvider"]:
            raise ValueError("embedding_provider_invalid")
        logger.info("embedding_cpu_session_loaded candidate=%s", profile["id"])

    def tokens(self, text, kind):
        """Count actual prefix/special tokens without silently truncating lexical content."""
        if (
            kind not in {"query", "passage"}
            or not isinstance(text, str)
            or not text.strip()
            or len(text.encode()) > 32768
        ):
            raise ValueError("embedding_input_invalid")
        encoded = self.tokenizer.encode(kind + ": " + text)
        if len(encoded.ids) > MAX_TOKENS:
            raise ValueError("embedding_token_limit")
        return encoded

    def encode(self, texts, kind):
        """Encode bounded batches using attention-mask mean pooling and unit vectors."""
        if not texts or len(texts) > 256:
            raise ValueError("embedding_input_invalid")
        outputs = []
        for offset in range(0, len(texts), BATCH_SIZE):
            encoded = [
                self.tokens(text, kind) for text in texts[offset : offset + BATCH_SIZE]
            ]
            length = max(len(item.ids) for item in encoded)
            ids = np.ones((len(encoded), length), dtype=np.int64)
            mask = np.zeros_like(ids)
            for index, item in enumerate(encoded):
                ids[index, : len(item.ids)] = item.ids
                mask[index, : len(item.ids)] = 1
            available = dict(
                input_ids=ids, attention_mask=mask, token_type_ids=np.zeros_like(ids)
            )
            feeds = {
                item.name: available[item.name] for item in self.session.get_inputs()
            }
            hidden = self.session.run(None, feeds)[0]
            outputs.append(mean_normalize(hidden, mask, self.profile["dimension"]))
        result = np.concatenate(outputs)
        logger.info(
            "embedding_batch_encoded candidate=%s kind=%s count=%d",
            self.profile["id"],
            kind,
            len(texts),
        )
        return result
