"""Rehydrate ACL-filtered vector candidates from current immutable sources and retain delivery authorization."""

import asyncio
import json
import logging
from contextlib import AsyncExitStack, asynccontextmanager
from uuid import UUID

from sqlalchemy import text

from apps.api.services.chunks import chunk_operation
from apps.api.services.files import file_io, finish_task
from src.application.services.file_storage_policy import StoragePolicyError
from src.application.services.ingestion_contract import (
    plan_ingestion,
    validate_source_fence,
)
from src.infrastructure.qdrant_ingestion import vector_payload
from src.infrastructure.qdrant_retrieval import QdrantRetrieval, search_options
from src.infrastructure.qwen_query import QwenQueryEmbedding

logger = logging.getLogger(__name__)


class RetrievalService:
    """Own one nonqueued response-lifetime search with trusted source/generation revalidation."""

    def __init__(self, ingestion, *, encoder=None):
        """Reuse approved ingestion resources and share its encoder admission without new service writes."""
        self.ingestion = ingestion
        self.files = ingestion.files
        self.journal = ingestion.journal
        self.vectors = QdrantRetrieval(ingestion.vectors)
        self.encoder = encoder or QwenQueryEmbedding(ingestion.encoder, ingestion.model)
        self.admission = asyncio.Lock()
        self.operations = set()
        self.closing = False

    async def validate(self, owner, retained):
        """Authorize current SQL active generations and independently verified retained source bytes before headers."""
        for plan, reader in retained:
            active = await self.journal.active(
                owner, plan.file_id, plan.model_fingerprint
            )
            if active is None or active["id"] != plan.job_id:
                raise StoragePolicyError("retrieval_source_changed", 409)
            row = await self.files.journal.get(owner, plan.file_id)
            validate_source_fence(plan, row)
            await file_io(
                reader.verify_integrity, row["actual_size_bytes"], row["actual_sha256"]
            )
        if retained:
            expected = {plan.job_id for plan, _ in retained}
            async with self.journal.sessions() as session:
                visible = set(
                    (
                        await session.execute(
                            text(
                                "SELECT j.id FROM assistant.ingestion_heads h "
                                "JOIN assistant.ingestion_jobs j ON j.id=h.active_job_id "
                                "JOIN assistant.files f ON f.id=h.file_id AND f.owner_id=h.owner_id "
                                "WHERE h.owner_id=:owner AND h.namespace_id=:namespace "
                                "AND h.model_fingerprint=:model AND j.id=ANY(CAST(:jobs AS uuid[])) "
                                "AND j.state='ready' AND f.state='ready' AND f.deleted_at IS NULL "
                                "AND f.actual_sha256=j.source_sha256 "
                                "AND f.policy_snapshot->>'_storage_namespace'=:namespace_text"
                            ),
                            dict(
                                owner=owner,
                                namespace=self.files.storage.namespace_id,
                                namespace_text=str(self.files.storage.namespace_id),
                                model=self.ingestion.model,
                                jobs=list(expected),
                            ),
                        )
                    ).scalars()
                )
            if visible != expected:
                raise StoragePolicyError("retrieval_source_changed", 409)
        logger.info("retrieval_delivery_authorized sources=%d", len(retained))

    @asynccontextmanager
    async def operation(self, owner, query, *, top_k=5, file_ids=None):
        """Hold search admission and source readers through reconstruction, final fences and delivery."""
        limit = search_options(query, top_k, file_ids)
        if self.closing or self.ingestion.closing or self.files.closing:
            raise StoragePolicyError("retrieval_unavailable", 503)
        if self.admission.locked():
            raise StoragePolicyError("retrieval_busy", 429)
        await self.admission.acquire()
        task = asyncio.current_task()
        self.operations.add(task)
        file_task = None
        try:
            file_task = self.files.track()
            if self.closing:
                raise StoragePolicyError("retrieval_unavailable", 503)
            async with AsyncExitStack() as stack:
                vector = await self.encoder.encode(query)
                candidates = await self.vectors.search(
                    owner,
                    self.files.storage.namespace_id,
                    vector,
                    top_k=top_k,
                    file_ids=file_ids,
                )
                cached, retained, hits = {}, [], []
                for candidate in candidates:
                    payload = candidate["payload"]
                    file_id = UUID(payload["file_id"])
                    active = await self.journal.active(
                        owner, file_id, self.ingestion.model
                    )
                    if (
                        active is None
                        or active["generation"] != payload.get("index_generation")
                        or UUID(candidate["id"]) not in active["point_ids"]
                    ):
                        continue
                    if file_id not in cached:
                        options = json.loads(active["manifest_json"])["source"]
                        async with chunk_operation(
                            self.files, owner, file_id, max_bytes=options["max_bytes"]
                        ) as (row, view):
                            plan = plan_ingestion(
                                row,
                                owner,
                                self.files.storage.namespace_id,
                                view,
                                self.ingestion.selection,
                            )
                            if (
                                plan.job_id != active["id"]
                                or plan.manifest_json != active["manifest_json"]
                            ):
                                raise StoragePolicyError(
                                    "retrieval_projection_changed", 409
                                )
                            _, reader = await self.files.open_download(owner, file_id)
                            stack.push_async_callback(file_io, reader.close)
                            retained.append((plan, reader))
                            cached[file_id] = (
                                plan,
                                {str(point.point_id): point for point in plan.points},
                            )
                    plan, points = cached[file_id]
                    if plan.job_id != active["id"]:
                        raise StoragePolicyError("retrieval_source_changed", 409)
                    point = points.get(candidate["id"])
                    if point is None or payload != vector_payload(point, "active"):
                        raise StoragePolicyError("retrieval_payload_invalid", 503)
                    hits.append(
                        dict(
                            point_id=str(point.point_id),
                            file_id=str(file_id),
                            chunk_id=point.chunk_id,
                            source_sha256=plan.source_sha256,
                            generation=plan.generation,
                            score=candidate["score"],
                            text=point.text,
                            provenance=json.loads(point.payload_json),
                            content_trust="untrusted",
                        )
                    )
                    if len(hits) == top_k:
                        break
                await self.validate(owner, retained)
                logger.info("retrieval_sources_prepared hits=%d", len(hits))
                yield (
                    dict(
                        hits=hits,
                        candidate_limit=limit,
                        top_k=top_k,
                        content_trust="untrusted",
                    ),
                    retained,
                )
        finally:
            if file_task is not None:
                self.files.untrack(file_task)
            self.operations.discard(task)
            self.admission.release()
            logger.info("retrieval_operation_closed")

    async def shutdown(self):
        """Stop new searches and cancel/join resource owners before ingestion or file shutdown."""
        self.closing = True
        tasks = list(self.operations)
        for task in tasks:
            task.cancel()
        for task in tasks:
            try:
                await finish_task(task)
            except BaseException:
                logger.warning("retrieval_owned_operation_joined")
        logger.info("retrieval_shutdown_complete")
