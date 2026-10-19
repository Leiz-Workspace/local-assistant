"""Verify actual source deletion across SQL admission, scoped Qdrant vectors and private blob while preserving foreign fixtures."""

import asyncio
import json
import logging
from pathlib import Path
from uuid import UUID

from sqlalchemy import text
from test_ingestion_http import upload, wait_job
from test_retrieval_http import retrieval_client as retrieval_client
from test_retrieval_http import search

from apps.api.services.files import file_io

logger = logging.getLogger(__name__)


def test_actual_file_delete_removes_scoped_vectors_blob_and_source_access(
    retrieval_client,
):
    """Observe physical source/vector cleanup and inactive DB tombstone rather than infer erasure from HTTP success."""
    client, auth = retrieval_client
    headers, foreign = auth["headers"]
    marker = "PRIVATE_SOURCE_CEDAR_7443"
    identifier = upload(client, headers, marker.encode(), "d31-source")
    other = upload(client, foreign, b"FOREIGN_SOURCE_RETAINED", "d31-foreign")
    indexed = client.post("/api/v1/files/" + identifier + "/index", headers=headers)
    assert indexed.status_code == 202
    job = indexed.json()["id"]
    assert wait_job(client, headers, job)["active"]
    other_indexed = client.post("/api/v1/files/" + other + "/index", headers=foreign)
    assert (
        other_indexed.status_code == 202
        and wait_job(client, foreign, other_indexed.json()["id"])["active"]
    )
    ingestion = client.app.state.ingestion_service
    files = client.app.state.file_service
    scope = dict(
        must=[
            dict(key="owner_id", match=dict(value=str(auth["principals"][0]))),
            dict(key="file_id", match=dict(value=identifier)),
        ]
    )

    foreign_scope = dict(
        must=[
            dict(key="owner_id", match=dict(value=str(auth["principals"][1]))),
            dict(key="file_id", match=dict(value=other)),
        ]
    )

    async def before():
        """Verify owned source bytes/vector presence and text-free durable metadata before deletion."""
        row = await files.journal.get(auth["principals"][0], UUID(identifier))
        other_row = await files.journal.get(auth["principals"][1], UUID(other))
        count = await ingestion.vectors.request(
            "POST",
            ingestion.vectors.path + "/points/count",
            dict(exact=True, filter=scope),
        )
        foreign_count = await ingestion.vectors.request(
            "POST",
            ingestion.vectors.path + "/points/count",
            dict(exact=True, filter=foreign_scope),
        )
        assert foreign_count["result"]["count"] > 0
        payload = await ingestion.vectors.request(
            "POST",
            ingestion.vectors.path + "/points/scroll",
            dict(filter=scope, limit=10, with_payload=True, with_vector=False),
        )
        stored = await ingestion.journal.get(auth["principals"][0], UUID(job))
        inventory = await file_io(files.storage.inventory)
        assert (
            count["result"]["count"] > 0
            and row["storage_key"] in inventory
            and other_row["storage_key"] in inventory
        )
        assert (
            marker not in json.dumps(payload) and marker not in stored["manifest_json"]
        )
        return row["storage_key"], other_row["storage_key"]

    source_key, foreign_key = client.portal.call(before)
    assert (
        client.delete("/api/v1/files/" + identifier, headers=foreign).status_code == 404
    )
    assert client.delete(
        "/api/v1/files/" + identifier, headers=headers
    ).status_code in (202, 204)
    assert not search(client, headers, "Cedar port", file_ids=[identifier])["hits"]

    async def after():
        """Wait a bounded interval for actual durable vector cleanup acknowledgement and physical blob/quota completion."""
        deadline = asyncio.get_running_loop().time() + 30
        while asyncio.get_running_loop().time() < deadline:
            async with files.journal.sessions() as session:
                row = (
                    (
                        await session.execute(
                            text(
                                "SELECT state,quota_released_at FROM assistant.files WHERE id=:id AND owner_id=:owner"
                            ),
                            dict(id=UUID(identifier), owner=auth["principals"][0]),
                        )
                    )
                    .mappings()
                    .one()
                )
            stored = await ingestion.journal.get(auth["principals"][0], UUID(job))
            active = await ingestion.journal.active(
                auth["principals"][0], UUID(identifier), ingestion.model
            )
            inventory = await file_io(files.storage.inventory)
            count = (
                await ingestion.vectors.request(
                    "POST",
                    ingestion.vectors.path + "/points/count",
                    dict(exact=True, filter=scope),
                )
            )["result"]["count"]
            if (
                row["state"] == "deleted"
                and row["quota_released_at"] is not None
                and stored["state"] == "tombstone"
                and stored["cleanup_done_at"] is not None
                and count == 0
                and source_key not in inventory
            ):
                foreign_count = (
                    await ingestion.vectors.request(
                        "POST",
                        ingestion.vectors.path + "/points/count",
                        dict(exact=True, filter=foreign_scope),
                    )
                )["result"]["count"]
                assert active is None and foreign_key in inventory and foreign_count > 0
                assert marker not in stored["manifest_json"]
                async with files.journal.sessions() as session:
                    usage = (
                        await session.execute(
                            text(
                                "SELECT allocated_bytes,allocated_files,active_uploads FROM assistant.file_owner_usage WHERE owner_id=:owner"
                            ),
                            dict(owner=auth["principals"][0]),
                        )
                    ).one()
                assert tuple(usage) == (0, 0, 0)
                return dict(
                    source_state=row["state"],
                    generation_state=stored["state"],
                    vector_count=count,
                    source_blob_present=False,
                    foreign_blob_preserved=True,
                    foreign_vector_count=foreign_count,
                    quota_released=True,
                    journal_retained_as_text_free_tombstone=True,
                )
            await asyncio.sleep(0.05)
        raise AssertionError(
            "owned source privacy cleanup did not finish within30seconds"
        )

    result = client.portal.call(after)
    denied = client.get("/api/v1/files/" + identifier + "/content", headers=headers)
    assert denied.status_code in (404, 409) and marker not in denied.text
    assert (
        client.get("/api/v1/files/" + other + "/content", headers=foreign).content
        == b"FOREIGN_SOURCE_RETAINED"
    )
    path = Path("data/backups/d31-t02-file-vector-privacy.json")
    path.touch(mode=0o600, exist_ok=True)
    path.chmod(0o600)
    path.write_text(
        json.dumps(
            dict(
                description="Actual approved Qwen/source/SQL/Qdrant/blob deletion on an owned removable probe; foreign source/vector preserved, no production collection or secure-erasure claim.",
                **result,
            ),
            indent=2,
        )
        + "\n"
    )
    logger.info(
        "file_vector_blob_privacy_verified result=%s",
        json.dumps(result, sort_keys=True),
    )
