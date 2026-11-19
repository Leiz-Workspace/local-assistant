"""Plan source-bound private ingestion identities without database, embedding or vector mutations."""

import hashlib
import logging
import re
from dataclasses import dataclass
from uuid import NAMESPACE_URL, UUID, uuid5

from src.application.services.document_chunks import (
    CHUNK_VERSION,
    MAX_CHUNKS,
    MAX_REPLY_BYTES,
    MAX_SOURCE_BYTES,
    ChunkSource,
    canonical,
)
from src.application.services.file_storage_policy import StoragePolicyError

logger = logging.getLogger(__name__)
HEX64 = re.compile(r"[0-9a-f]{64}")
CONTRACT_FAULTS = (
    KeyError,
    TypeError,
    ValueError,
    AttributeError,
    OverflowError,
    RecursionError,
)


@dataclass(frozen=True)
class IngestionPoint:
    """Keep exact text and canonical private provenance separate from deterministic point identity."""

    point_id: UUID
    chunk_id: str
    text: str
    payload_json: str


@dataclass(frozen=True)
class IngestionPlan:
    """Hold an immutable retryable source/model generation awaiting durable admission and token checks."""

    job_id: UUID
    owner_id: UUID
    namespace_id: UUID
    file_id: UUID
    source_sha256: str
    model_fingerprint: str
    collection_name: str
    generation: str
    manifest_json: str
    points: tuple[IngestionPoint, ...]


def digest(value):
    """Hash canonical UTF-8 JSON without altering source text or metadata."""
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def validate_model_contract(selection):
    """Require the approved selection to match the pinned D22 model contract and report drift as a server fault."""
    try:
        return _model_contract(selection)
    except CONTRACT_FAULTS:
        logger.error("ingestion_model_contract_mismatch")
        raise StoragePolicyError("ingestion_model_contract_mismatch", 503) from None


def _model_contract(selection):
    """Compare every selected model/runtime/collection field with the deliberate ADR-033 pin and return its fingerprint."""
    runtime, collection = selection["runtime"], selection["collection"]
    model = collection["model_fingerprint"]
    if not HEX64.fullmatch(model) or runtime["fingerprint"] != model:
        raise ValueError("model")
    if (
        selection["candidate"]["repository"] != "Qwen/Qwen3-Embedding-0.6B"
        or selection["candidate"]["dimension"] != 1024
    ):
        raise ValueError("selection")
    if (
        runtime["device"] != "cpu"
        or runtime["max_tokens"] != 512
        or runtime["passage_prefix"] != ""
        or runtime["distance"] != "Cosine"
        or runtime["pooling"] != "last_attended_token_float32"
        or runtime["normalization"] != "l2"
        or runtime["use_cache"] is not False
        or runtime["weight_dtype"] != "bfloat16"
        or runtime["intra_op_threads"] != 2
        or runtime["inter_op_threads"] != 1
        or runtime["batch_size"] != 4
        or runtime["query_prefix"] != selection["candidate"]["query_prefix"]
    ):
        raise ValueError("runtime")
    expected_model = digest(
        dict(
            profile=selection["candidate"],
            format="official-safetensors-bf16-cpu",
            pooling="last_attended_token_float32",
            normalization="l2",
            attention="sdpa",
            use_cache=False,
            runtime=runtime["packages"],
        )
    )
    if model != expected_model:
        raise ValueError("model_contract")
    if collection["create"]["vectors"]["dense"] != dict(
        size=1024, distance="Cosine", on_disk=True
    ):
        raise ValueError("vector_schema")
    if collection["collection_name"] != f"la_chunks_{model}_v1":
        raise ValueError("collection")
    return model


def plan_ingestion(row, owner_id, namespace_id, view, selection):
    """Recheck the server model contract, then trusted ready-source scope and exact D22 identity, before making a deterministic plan."""
    model = validate_model_contract(selection)
    try:
        return _plan_ingestion(
            row, owner_id, namespace_id, view, model, selection["collection"]
        )
    except CONTRACT_FAULTS:
        logger.warning("ingestion_plan_rejected")
        raise StoragePolicyError("ingestion_input_invalid", 422) from None


def _plan_ingestion(row, owner_id, namespace_id, view, model, collection):
    """Validate bounded source/chunk contracts against a validated model and construct content-addressed immutable records."""
    if not isinstance(owner_id, UUID) or not isinstance(namespace_id, UUID):
        raise ValueError("scope")
    if row["owner_id"] != owner_id or row["policy_snapshot"].get(
        "_storage_namespace"
    ) != str(namespace_id):
        raise StoragePolicyError("file_not_found", 404)
    if row["state"] != "ready" or row.get("deleted_at") is not None:
        raise StoragePolicyError("file_not_ready", 409)
    file_id = row["id"]
    sha = row["actual_sha256"]
    if not isinstance(file_id, UUID) or not HEX64.fullmatch(sha):
        raise ValueError("source")
    if view["file_id"] != str(file_id) or view["sha256"] != sha:
        raise StoragePolicyError("ingestion_source_changed", 409)
    encoded = canonical(view).encode()
    if len(encoded) > MAX_REPLY_BYTES:
        raise StoragePolicyError("ingestion_limits_exceeded", 413)
    source = ChunkSource(owner_id, namespace_id, file_id, sha, view["processor"])
    if (
        not isinstance(source.processor, str)
        or not 1 <= len(source.processor.encode()) <= 256
    ):
        raise ValueError("processor")
    expected_access = dict(
        visibility="private",
        principal_id=str(owner_id),
        scope=digest(source.identity()),
    )
    if (
        view["access"] != expected_access
        or view["content_trust"] != "untrusted"
        or view["span_unit"] != "unicode_code_points"
    ):
        raise ValueError("access")
    if (
        view["chunker"] != CHUNK_VERSION
        or type(view["max_bytes"]) is not int
        or not 256 <= view["max_bytes"] <= 8192
    ):
        raise ValueError("chunker")
    chunks, empty = view["chunks"], view["empty_sources"]
    if (
        not isinstance(chunks, list)
        or not isinstance(empty, list)
        or len(chunks) + len(empty) > MAX_CHUNKS
    ):
        raise ValueError("chunks")
    identity = dict(
        source.identity(),
        sha256=sha,
        processor=source.processor,
        chunker=CHUNK_VERSION,
        max_bytes=view["max_bytes"],
    )
    seen, total = set(), 0
    for chunk in chunks:
        content = dict(chunk)
        chunk_id = content.pop("id")
        if set(content) != {
            "kind",
            "locator",
            "text",
            "spans",
            "structure",
            "section_path",
            "quality",
        }:
            raise ValueError("chunk_fields")
        if not isinstance(chunk["text"], str) or not chunk["text"].strip():
            raise StoragePolicyError("ingestion_empty_chunk", 422)
        size = len(chunk["text"].encode())
        if size > view["max_bytes"]:
            raise ValueError("chunk_bytes")
        total += size
        if total > MAX_SOURCE_BYTES:
            raise StoragePolicyError("ingestion_limits_exceeded", 413)
        if chunk_id in seen or chunk_id != "chk_" + digest(
            dict(identity=identity, chunk=content)
        ):
            raise ValueError("chunk_identity")
        seen.add(chunk_id)
    manifest = dict(
        version="ingestion-plan-v1",
        source=identity,
        model_fingerprint=model,
        collection_name=collection["collection_name"],
        projection_sha256=digest(view),
    )
    generation = digest(manifest)
    job_id = uuid5(NAMESPACE_URL, "local-assistant:ingestion:" + generation)
    points = []
    for chunk in chunks:
        payload = dict(
            owner_id=str(owner_id),
            namespace_id=str(namespace_id),
            file_id=str(file_id),
            source_sha256=sha,
            chunk_id=chunk["id"],
            chunker_version=CHUNK_VERSION,
            processor=source.processor,
            model_fingerprint=model,
            index_generation=generation,
            state="pending",
            visibility="private",
            content_trust="untrusted",
            locator=chunk["locator"],
            spans=chunk["spans"],
            section_path=chunk["section_path"],
            quality=chunk["quality"],
            structure=chunk["structure"],
        )
        points.append(
            IngestionPoint(
                uuid5(job_id, chunk["id"]),
                chunk["id"],
                chunk["text"],
                canonical(payload),
            )
        )
    logger.info(
        "ingestion_plan_prepared file_id=%s generation=%s points=%d",
        file_id,
        generation,
        len(points),
    )
    return IngestionPlan(
        job_id,
        owner_id,
        namespace_id,
        file_id,
        sha,
        model,
        collection["collection_name"],
        generation,
        canonical(manifest),
        tuple(points),
    )


def validate_token_counts(plan, counts):
    """Require one complete nontruncated Qwen passage count per immutable planned point."""
    if (
        not isinstance(counts, list)
        or len(counts) != len(plan.points)
        or any(type(n) is not int or not 1 <= n <= 512 for n in counts)
    ):
        logger.warning("ingestion_token_preflight_rejected job_id=%s", plan.job_id)
        raise StoragePolicyError("ingestion_token_limit", 422)
    logger.info(
        "ingestion_token_preflight_passed job_id=%s points=%d", plan.job_id, len(counts)
    )
    return tuple(counts)


def validate_source_fence(plan, row):
    """Reject stale or foreign metadata before future admission/publication under a database lock."""
    if (
        row is None
        or row.get("id") != plan.file_id
        or row.get("owner_id") != plan.owner_id
        or row.get("policy_snapshot", {}).get("_storage_namespace")
        != str(plan.namespace_id)
    ):
        logger.warning("ingestion_source_scope_rejected job_id=%s", plan.job_id)
        raise StoragePolicyError("file_not_found", 404)
    if (
        row.get("state") != "ready"
        or row.get("deleted_at") is not None
        or row.get("actual_sha256") != plan.source_sha256
    ):
        logger.warning("ingestion_source_fence_rejected job_id=%s", plan.job_id)
        raise StoragePolicyError("ingestion_source_changed", 409)
    logger.info("ingestion_source_fence_passed job_id=%s", plan.job_id)
