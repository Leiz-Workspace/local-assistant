"""Count exact Qwen passage tokens offline in an isolated locked process without loading embedding weights."""
# /// script
# requires-python = ">=3.12,<3.13"
# dependencies = ["torch==2.10.0+cpu", "transformers==4.57.6", "numpy==2.5.4", "httpx==0.28.1", "typing-extensions==4.15.0"]
# [tool.uv.sources]
# torch = { index = "pytorch-cpu" }
# [[tool.uv.index]]
# name = "pytorch-cpu"
# url = "https://download.pytorch.org/whl/cpu"
# explicit = true
# ///

import json
import logging
import resource
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
logger = logging.getLogger(__name__)


def count_passages(texts):
    """Verify pinned local assets and tokenize complete unprefixed passages without truncation."""
    from transformers import AutoTokenizer

    from scripts.embedding_runtime import artifact_path, verify_artifacts
    from scripts.qwen_embedding_evaluation import (
        input_text,
        qwen_fingerprint,
        qwen_profile,
    )
    from src.application.services.document_chunks import MAX_CHUNKS, MAX_SOURCE_BYTES

    if (
        not isinstance(texts, list)
        or len(texts) > MAX_CHUNKS
        or any(not isinstance(text, str) for text in texts)
    ):
        raise ValueError("preflight_input_invalid")
    if sum(len(text.encode()) for text in texts) > MAX_SOURCE_BYTES:
        raise ValueError("preflight_input_invalid")
    profile = qwen_profile()
    verify_artifacts(profile)
    tokenizer = AutoTokenizer.from_pretrained(
        artifact_path(profile, profile["artifacts"][0]).parent,
        local_files_only=True,
        trust_remote_code=False,
        padding_side="left",
    )
    counts = []
    for text in texts:
        tokens = tokenizer.encode(
            input_text(profile, text, "passage"),
            add_special_tokens=True,
            truncation=False,
        )
        if not 1 <= len(tokens) <= 512:
            raise ValueError("preflight_token_limit")
        counts.append(len(tokens))
    logger.info("qwen_ingestion_tokens_counted passages=%d", len(counts))
    return dict(
        model_fingerprint=qwen_fingerprint(profile), max_tokens=512, counts=counts
    )


def main():
    """Consume one bounded private JSON request and return only counts or a fixed safe error."""
    resource.setrlimit(resource.RLIMIT_AS, (4 * 1024**3, 4 * 1024**3))
    resource.setrlimit(resource.RLIMIT_CPU, (60, 61))
    try:
        data = sys.stdin.buffer.read(8 * 1024**2 + 1)
        if len(data) > 8 * 1024**2:
            raise ValueError("preflight_input_invalid")
        request = json.loads(data)
        if not isinstance(request, dict) or set(request) != {"texts"}:
            raise ValueError("preflight_input_invalid")
        result = count_passages(request["texts"])
        print(json.dumps(result))
        return 0
    except ValueError as error:
        if str(error) == "preflight_token_limit":
            logger.warning("qwen_ingestion_token_limit")
            print(json.dumps(dict(error="ingestion_token_limit")))
            return 2
        logger.warning("qwen_ingestion_preflight_failed")
        print(json.dumps(dict(error="ingestion_token_preflight_failed")))
        return 1
    except Exception:
        logger.warning("qwen_ingestion_preflight_failed")
        print(json.dumps(dict(error="ingestion_token_preflight_failed")))
        return 1


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    raise SystemExit(main())
