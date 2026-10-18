"""Validate the D24 vector schema on one owned empty probe while preserving shared collections."""

import hashlib
import json
import logging
from urllib.parse import quote
from uuid import uuid4

import httpx

from scripts.embedding_runtime import fingerprint

logger = logging.getLogger(__name__)


def collection_plan(profile):
    """Describe a versioned dense vector/tenant-index contract without creating a user collection."""
    model = fingerprint(profile)
    indexes = dict(
        owner_id=dict(type="uuid", is_tenant=True),
        namespace_id="uuid",
        file_id="uuid",
        source_sha256="keyword",
        chunk_id="keyword",
        chunker_version="keyword",
        processor="keyword",
        model_fingerprint="keyword",
        index_generation="keyword",
        state="keyword",
    )
    return dict(
        description="D24 proposed private vector collection; production ingestion/search remain D25/D26.",
        collection_name="la_chunks_" + model + "_v1",
        model_fingerprint=model,
        create=dict(
            vectors=dict(
                dense=dict(size=profile["dimension"], distance="Cosine", on_disk=True)
            ),
            shard_number=1,
            replication_factor=1,
        ),
        payload_indexes=indexes,
        required_scope=[
            "owner_id",
            "namespace_id",
            "model_fingerprint",
            "index_generation",
            "state",
        ],
        required_source=[
            "file_id",
            "source_sha256",
            "chunk_id",
            "chunker_version",
            "processor",
        ],
        content_trust="untrusted",
        visibility="private",
        source_text_in_payload=False,
    )


def request(client, method, path, payload=None):
    """Return bounded successful JSON without exposing Qdrant credentials or error response bodies."""
    try:
        with client.stream(method, path, json=payload) as response:
            data = bytearray()
            for chunk in response.iter_bytes():
                data.extend(chunk)
                if len(data) > 1024 * 1024:
                    raise ValueError("qdrant_design_reply_limit")
            if not 200 <= response.status_code < 300:
                raise ValueError("qdrant_design_request_failed")
        return json.loads(data)
    except (httpx.HTTPError, ValueError):
        raise ValueError("qdrant_design_request_failed") from None


def inventory(client):
    """Fingerprint existing collection configurations/counts without exposing names or document payloads."""
    collections = request(client, "GET", "/collections")["result"]["collections"]
    snapshot = {}
    for item in collections:
        name = item["name"]
        encoded = quote(name, safe="")
        result = request(client, "GET", "/collections/" + encoded)["result"]
        snapshot[name] = dict(
            config=result["config"], points_count=result.get("points_count")
        )
    return snapshot


def snapshot_digest(snapshot):
    """Retain only a digest of shared collection inventory, not private collection identifiers."""
    return hashlib.sha256(
        json.dumps(snapshot, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def probe_design(api_key, profile, *, client=None):
    """Create/index/delete exactly one fresh empty owned probe and verify shared inventory invariance."""
    if client is None:
        with httpx.Client(
            base_url="http://127.0.0.1:6333",
            headers={"api-key": api_key},
            trust_env=False,
            follow_redirects=False,
            timeout=15,
        ) as owned:
            return probe_design(api_key, profile, client=owned)
    plan = collection_plan(profile)
    server_version = request(client, "GET", "/")["version"]
    before = inventory(client)
    name = "la_d24_probe_" + uuid4().hex
    if name in before:
        raise ValueError("qdrant_probe_collision")
    created = False
    cleanup = False
    try:
        request(client, "PUT", "/collections/" + name, plan["create"])
        created = True
        for field, schema in plan["payload_indexes"].items():
            request(
                client,
                "PUT",
                f"/collections/{name}/index?wait=true",
                dict(field_name=field, field_schema=schema),
            )
        result = request(client, "GET", "/collections/" + name)["result"]
        vector = result["config"]["params"]["vectors"]["dense"]
        schema = result["payload_schema"]
        valid = (
            vector["size"] == profile["dimension"]
            and vector["distance"] == "Cosine"
            and vector["on_disk"] is True
            and result["points_count"] == 0
        )
        for field, expected in plan["payload_indexes"].items():
            valid &= schema.get(field, {}).get("data_type") == (
                expected["type"] if isinstance(expected, dict) else expected
            )
        valid &= schema.get("owner_id", {}).get("params", {}).get("is_tenant") is True
        if not valid:
            raise ValueError("qdrant_probe_schema_mismatch")
    finally:
        if created:
            request(client, "DELETE", "/collections/" + name)
            cleanup = True
            logger.info("qdrant_design_probe_removed")
    after = inventory(client)
    if after != before:
        raise ValueError("qdrant_shared_inventory_changed")
    logger.info("qdrant_design_probe_verified indexes=%d", len(plan["payload_indexes"]))
    return dict(
        description="D24 owned empty schema/index probe on existing shared Qdrant; no production vectors or collection created.",
        passed=True,
        server_version=server_version,
        dimension=profile["dimension"],
        distance="Cosine",
        indexes_verified=len(plan["payload_indexes"]),
        owner_uuid_tenant_index=True,
        probe_removed=cleanup,
        existing_collection_count=len(before),
        before_sha256=snapshot_digest(before),
        after_sha256=snapshot_digest(after),
        model_fingerprint=plan["model_fingerprint"],
    )
