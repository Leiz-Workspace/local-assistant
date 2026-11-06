"""Write and verify only explicitly owned Qwen vector generations without database publication or collection deletion."""

import hashlib
import json
import logging
import re
from urllib.parse import quote
from uuid import UUID, uuid5

import httpx
import numpy as np

from src.application.services.file_storage_policy import StoragePolicyError
from src.infrastructure.qwen_embedding import validate_encoding

logger = logging.getLogger(__name__)
FIELDS = (
    "owner_id",
    "namespace_id",
    "file_id",
    "source_sha256",
    "chunk_id",
    "chunker_version",
    "processor",
    "model_fingerprint",
    "index_generation",
    "visibility",
    "content_trust",
)


def vector_payload(point, state="pending"):
    """Allowlist scope and content/provenance digests without copying structured source rows into payload."""
    source = json.loads(point.payload_json)
    result = {name: source[name] for name in FIELDS}
    result.update(
        state=state,
        chunk_content_sha256=hashlib.sha256(point.text.encode()).hexdigest(),
        provenance_sha256=hashlib.sha256(point.payload_json.encode()).hexdigest(),
        quality_present=bool(source["quality"]),
    )
    return result


def generation_scope(plan):
    """Build an exact trusted generation filter that cannot target another owner/root/source/model."""
    return dict(
        must=[
            dict(key=key, match=dict(value=value))
            for key, value in dict(
                owner_id=str(plan.owner_id),
                namespace_id=str(plan.namespace_id),
                file_id=str(plan.file_id),
                source_sha256=plan.source_sha256,
                model_fingerprint=plan.model_fingerprint,
                index_generation=plan.generation,
            ).items()
        ]
    )


class QdrantIngestion:
    """Require explicit installation ownership before every scoped schema/vector mutation."""

    def __init__(
        self, selection, owner_id, api_key=None, *, client=None, physical_name=None
    ):
        """Bind approved schema and a loopback client, allowing only named isolated acceptance probes."""
        if not isinstance(owner_id, UUID):
            raise ValueError("qdrant_owner_required")
        self.config = selection["collection"]
        self.model = self.config["model_fingerprint"]
        self.logical_name = self.config["collection_name"]
        if (
            not re.fullmatch(r"[0-9a-f]{64}", self.model)
            or self.logical_name != f"la_chunks_{self.model}_v1"
        ):
            raise ValueError("qdrant_model_contract")
        self.name = physical_name or self.logical_name
        if self.name != self.logical_name and not re.fullmatch(
            r"la_d25_probe_[0-9a-f]{32}", self.name
        ):
            raise ValueError("qdrant_collection_scope")
        self.path = "/collections/" + quote(self.name, safe="")
        self.metadata = dict(
            application="local-assistant-ingestion-v1",
            owner_id=str(owner_id),
            model_fingerprint=self.model,
        )
        if client is None and (not isinstance(api_key, str) or not api_key.strip()):
            raise ValueError("qdrant_credential_required")
        self._owned_client = client is None
        self.client = client or httpx.AsyncClient(
            base_url="http://127.0.0.1:6333",
            headers={"api-key": api_key} if api_key else {},
            trust_env=False,
            follow_redirects=False,
            timeout=httpx.Timeout(15, connect=3),
        )

    async def close(self):
        """Release only the HTTP client owned by this adapter, never a collection or generation."""
        if self._owned_client:
            await self.client.aclose()
        logger.info("ingestion_vector_client_closed")

    async def request(self, method, path, payload=None, *, missing=False):
        """Read bounded successful API data while sanitizing secret-bearing transport/server diagnostics."""
        try:
            async with self.client.stream(method, path, json=payload) as response:
                if response.status_code == 404 and missing:
                    return None
                data = bytearray()
                async for block in response.aiter_bytes():
                    data.extend(block)
                    if len(data) > 2 * 1024**2:
                        raise ValueError("vector_reply_limit")
                if not 200 <= response.status_code < 300:
                    raise ValueError("vector_request")
            result = json.loads(data)
            if not isinstance(result, dict) or "result" not in result:
                raise ValueError("vector_reply_invalid")
            return result
        except (httpx.HTTPError, ValueError):
            logger.warning("ingestion_vector_request_failed")
            raise StoragePolicyError("ingestion_vector_unavailable", 503) from None

    async def owned(self):
        """Refuse foreign metadata or incompatible schema before vector/index operations."""
        reply = await self.request("GET", self.path, missing=True)
        if reply is None:
            return None
        try:
            result = reply["result"]
            config = result["config"]
            vectors = config["params"]["vectors"]
            if (
                set(vectors) != {"dense"}
                or config.get("metadata") != self.metadata
                or any(
                    vectors["dense"].get(key) != value
                    for key, value in self.config["create"]["vectors"]["dense"].items()
                )
            ):
                raise ValueError("collection_identity")
        except (ValueError, KeyError, TypeError, AttributeError):
            raise StoragePolicyError("ingestion_collection_not_owned", 409) from None
        return result

    async def ensure(self):
        """Create or reconcile only a matching owned collection and verify required payload indexes."""
        if await self.owned() is None:
            await self.request(
                "PUT", self.path, dict(self.config["create"], metadata=self.metadata)
            )
        result = await self.owned()
        if result is None:
            raise StoragePolicyError("ingestion_collection_missing", 503)
        for field, schema in self.config["payload_indexes"].items():
            await self.request(
                "PUT",
                self.path + "/index?wait=true",
                dict(field_name=field, field_schema=schema),
            )
        result = await self.owned()
        for field, schema in self.config["payload_indexes"].items():
            actual = result["payload_schema"].get(field, {})
            expected = schema if isinstance(schema, str) else schema["type"]
            if (
                actual.get("data_type") != expected
                or isinstance(schema, dict)
                and actual.get("params", {}).get("is_tenant") is not True
            ):
                raise StoragePolicyError("ingestion_vector_schema_invalid", 503)
        logger.info("ingestion_vector_schema_ready")

    def check_plan(self, plan):
        """Require model/collection identity and source-bound deterministic point payloads before mutation."""
        if (
            plan.model_fingerprint != self.model
            or plan.collection_name != self.logical_name
        ):
            raise StoragePolicyError("ingestion_vector_scope_invalid", 409)
        for point in plan.points:
            payload = vector_payload(point)
            values = {
                entry["key"]: entry["match"]["value"]
                for entry in generation_scope(plan)["must"]
            }
            if (
                any(payload[name] != value for name, value in values.items())
                or payload["chunk_id"] != point.chunk_id
                or point.point_id != uuid5(plan.job_id, point.chunk_id)
            ):
                raise StoragePolicyError("ingestion_vector_scope_invalid", 409)

    async def verify(self, plan, batch, *, state="pending"):
        """Sanitize malformed server records while requiring exact complete scoped vector verification."""
        try:
            return await self._verify(plan, batch, state=state)
        except (KeyError, TypeError, ValueError, AttributeError, OverflowError):
            logger.warning("ingestion_vector_verification_failed")
            raise StoragePolicyError(
                "ingestion_vector_verification_failed", 503
            ) from None

    async def _verify(self, plan, batch, *, state="pending"):
        """Compare every expected ID/payload/vector and bound pagination independently of write acknowledgements."""
        self.check_plan(plan)
        batch = validate_encoding(
            plan,
            dict(
                model_fingerprint=batch.model_fingerprint,
                counts=list(batch.counts),
                vectors=[list(row) for row in batch.vectors],
            ),
        )
        if await self.owned() is None:
            raise StoragePolicyError("ingestion_collection_missing", 503)
        expected = {
            str(point.point_id): (vector_payload(point, state), vector)
            for point, vector in zip(plan.points, batch.vectors, strict=True)
        }
        seen, offset, pages = set(), None, 0
        while True:
            pages += 1
            if pages > len(expected) // 8 + 2:
                raise StoragePolicyError("ingestion_vector_verification_failed", 503)
            body = dict(
                filter=generation_scope(plan),
                limit=8,
                with_payload=True,
                with_vector=True,
            )
            if offset is not None:
                body["offset"] = offset
            result = (await self.request("POST", self.path + "/points/scroll", body))[
                "result"
            ]
            for item in result["points"]:
                identifier = str(item["id"])
                if identifier in seen or identifier not in expected:
                    raise StoragePolicyError(
                        "ingestion_vector_verification_failed", 503
                    )
                payload, vector = expected[identifier]
                actual = np.asarray(item["vector"]["dense"], dtype=np.float32)
                if (
                    item["payload"] != payload
                    or actual.shape != (1024,)
                    or not np.isfinite(actual).all()
                    or not np.allclose(actual, vector, atol=2e-5, rtol=2e-5)
                ):
                    raise StoragePolicyError(
                        "ingestion_vector_verification_failed", 503
                    )
                seen.add(identifier)
            following = result.get("next_page_offset")
            if following is None:
                break
            if (
                not isinstance(following, (str, int))
                or following == offset
                or len(seen) >= len(expected)
            ):
                raise StoragePolicyError("ingestion_vector_verification_failed", 503)
            offset = following
        if seen != set(expected):
            raise StoragePolicyError("ingestion_vector_verification_failed", 503)
        logger.info(
            "ingestion_vector_generation_verified job_id=%s points=%d",
            plan.job_id,
            len(seen),
        )
        return [point.point_id for point in plan.points]

    async def upsert(self, plan, batch):
        """Repeat deterministic bounded writes and return acknowledgements only after complete verification."""
        self.check_plan(plan)
        batch = validate_encoding(
            plan,
            dict(
                model_fingerprint=batch.model_fingerprint,
                counts=list(batch.counts),
                vectors=[list(row) for row in batch.vectors],
            ),
        )
        if await self.owned() is None:
            raise StoragePolicyError("ingestion_collection_missing", 503)
        for start in range(0, len(plan.points), 4):
            points = [
                dict(
                    id=str(point.point_id),
                    vector=dict(dense=list(vector)),
                    payload=vector_payload(point),
                )
                for point, vector in zip(
                    plan.points[start : start + 4],
                    batch.vectors[start : start + 4],
                    strict=True,
                )
            ]
            reply = await self.request(
                "PUT",
                self.path + "/points?wait=true&ordering=strong",
                dict(points=points),
            )
            if (
                not isinstance(reply["result"], dict)
                or reply["result"].get("status") != "completed"
            ):
                raise StoragePolicyError("ingestion_vector_acknowledgement_failed", 503)
        return await self.verify(plan, batch)

    async def delete(self, plan):
        """Delete and verify only the complete trusted generation scope, preserving every other point."""
        self.check_plan(plan)
        if await self.owned() is None:
            raise StoragePolicyError("ingestion_collection_missing", 503)
        reply = await self.request(
            "POST",
            self.path + "/points/delete?wait=true&ordering=strong",
            dict(filter=generation_scope(plan)),
        )
        if (
            not isinstance(reply["result"], dict)
            or reply["result"].get("status") != "completed"
        ):
            raise StoragePolicyError("ingestion_vector_acknowledgement_failed", 503)
        count = (
            await self.request(
                "POST",
                self.path + "/points/count",
                dict(filter=generation_scope(plan), exact=True),
            )
        )["result"]["count"]
        if type(count) is not int or count != 0:
            raise StoragePolicyError("ingestion_vector_delete_incomplete", 503)
        logger.info("ingestion_vector_generation_deleted job_id=%s", plan.job_id)

    async def activate(self, plan, batch):
        """Mark a fully verified staged generation active before the separate final SQL publication fence."""
        await self.verify(plan, batch)
        reply = await self.request(
            "POST",
            self.path + "/points/payload?wait=true&ordering=strong",
            dict(payload=dict(state="active"), filter=generation_scope(plan)),
        )
        if (
            not isinstance(reply["result"], dict)
            or reply["result"].get("status") != "completed"
        ):
            raise StoragePolicyError("ingestion_vector_acknowledgement_failed", 503)
        return await self.verify(plan, batch, state="active")
