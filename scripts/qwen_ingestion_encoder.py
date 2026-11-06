"""Encode complete private passages with pinned CPU Qwen in a credential-free bounded worker process."""
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
import os
import resource
import select
import signal
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
logger = logging.getLogger(__name__)


def supervise_parent():
    """Watch the exact API parent through a pidfd even when uv is the immediate launcher."""
    parent = int(os.environ["QWEN_INGESTION_PARENT_PID"])
    expected = os.environ["QWEN_INGESTION_PARENT_START"]
    descriptor = os.pidfd_open(parent)
    try:
        actual = Path(f"/proc/{parent}/stat").read_text().rsplit(")", 1)[1].split()[19]
        if actual != expected:
            raise ValueError("encoder_parent_changed")
    except BaseException:
        os.close(descriptor)
        raise

    def watch():
        """Terminate only this encoder once the exact API parent exits."""
        poller = select.poll()
        poller.register(descriptor, select.POLLIN)
        poller.poll()
        os.kill(os.getpid(), signal.SIGKILL)

    threading.Thread(target=watch, daemon=True).start()
    logger.info("ingestion_encoder_parent_supervised")


def encode_request(request):
    """Validate full input and actual pinned identity before encoding fixed-size batches without truncation."""
    from scripts.qwen_embedding_evaluation import (
        QwenCpu,
        qwen_fingerprint,
        qwen_profile,
    )

    if not isinstance(request, dict) or set(request) != {"texts", "model_fingerprint"}:
        raise ValueError("encoding_request_invalid")
    texts = request["texts"]
    if (
        not isinstance(texts, list)
        or len(texts) > 1000
        or any(not isinstance(value, str) for value in texts)
    ):
        raise ValueError("encoding_request_invalid")
    if sum(len(value.encode()) for value in texts) > 1024**2:
        raise ValueError("encoding_request_invalid")
    profile = qwen_profile()
    identity = qwen_fingerprint(profile)
    if request["model_fingerprint"] != identity:
        raise ValueError("encoding_identity_invalid")
    encoder = QwenCpu(profile)
    counts = [len(encoder.tokens(value, "passage")) for value in texts]
    vectors = []
    for offset in range(0, len(texts), 4):
        vectors.extend(encoder.encode(texts[offset : offset + 4], "passage").tolist())
    logger.info("qwen_ingestion_encoded passages=%d", len(texts))
    return dict(model_fingerprint=identity, counts=counts, vectors=vectors)


def main():
    """Read one bounded stdin request and return only the complete encoding or a fixed safe error."""
    resource.setrlimit(resource.RLIMIT_AS, (8 * 1024**3, 8 * 1024**3))
    resource.setrlimit(resource.RLIMIT_CPU, (480, 481))
    try:
        supervise_parent()
        data = sys.stdin.buffer.read(8 * 1024**2 + 1)
        if len(data) > 8 * 1024**2:
            raise ValueError("encoding_request_invalid")
        reply = json.dumps(encode_request(json.loads(data)), allow_nan=False)
        if len(reply.encode()) > 32 * 1024**2:
            raise ValueError("encoding_reply_limit")
        print(reply)
        return 0
    except Exception:
        logger.warning("qwen_ingestion_encoding_failed")
        print(json.dumps(dict(error="ingestion_encoding_failed")))
        return 1


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    raise SystemExit(main())
