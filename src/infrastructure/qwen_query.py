"""Encode approved instructed queries through existing bounded credential-free CPU admission."""

import json
import logging
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from apps.api.services.files import file_io
from src.application.services.file_storage_policy import StoragePolicyError
from src.infrastructure.qdrant_retrieval import search_options
from src.infrastructure.qwen_token_preflight import preflight_plan

logger = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parents[2]


class QwenQueryEmbedding:
    """Share the existing encoder slot while applying the exact approved model's query instruction."""

    def __init__(self, encoder, model):
        """Bind an already approved model fingerprint and local immutable query formatting profile."""
        self.encoder = encoder
        self.model = model
        profile = json.loads(
            (ROOT / "configs/embedding-qwen-evaluation.json").read_text()
        )
        if profile["passage_prefix"] != "" or not profile["query_prefix"]:
            raise ValueError("retrieval_query_format_invalid")
        self.prefix = profile["query_prefix"]

    async def encode(self, query):
        """Count complete instructed input and encode exactly those bytes without silent truncation."""
        search_options(query, 1)
        plan = SimpleNamespace(
            job_id=uuid4(),
            model_fingerprint=self.model,
            points=(SimpleNamespace(text=self.prefix + query),),
        )
        counts = await file_io(preflight_plan, plan)
        batch = await self.encoder.encode(plan)
        if (
            batch.model_fingerprint != self.model
            or batch.counts != counts
            or len(batch.vectors) != 1
        ):
            raise StoragePolicyError("retrieval_encoding_invalid", 503)
        logger.info("retrieval_query_encoded tokens=%d", counts[0])
        return batch.vectors[0]
