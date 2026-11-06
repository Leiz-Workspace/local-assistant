"""Exercise real authenticated source/Qwen/Qdrant retrieval through default-off runtime lifecycle wiring."""

import json

import pytest
from test_ingestion_http import ingest_client, upload, wait_job

from src.infrastructure.qwen_query import ROOT


@pytest.fixture
def retrieval_client(auth_settings, tmp_path, monkeypatch):
    """Enable retrieval before actual lifespan and reuse the owned removable ingestion probe fixture."""
    monkeypatch.setenv("ASSISTANT_RETRIEVAL_ENABLED", "1")
    yield from ingest_client.__wrapped__(auth_settings, tmp_path, monkeypatch)


def search(client, headers, query, **options):
    """Submit only an actual strict authenticated query without bypassing model or vector resources."""
    response = client.post(
        "/api/v1/retrieval/search", headers=headers, json=dict(query=query, **options)
    )
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "private, no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    return response.json()


def test_actual_qwen_http_owner_provenance_replacement_and_delete(retrieval_client):
    """Return rehydrated private text only to its principal and hide deleted old sources immediately."""
    client, auth = retrieval_client
    first, second = auth["headers"]
    selected_before = (ROOT / "configs/embedding-selected.json").read_bytes()
    source = upload(
        client,
        first,
        "Tài liệu riêng: kho lưu trữ dùng Qdrant.".encode(),
        "retrieval-one",
    )
    foreign = upload(client, second, b"foreign-secret-marker", "retrieval-foreign")
    for headers, identifier in [(first, source), (second, foreign)]:
        response = client.post(f"/api/v1/files/{identifier}/index", headers=headers)
        assert response.status_code == 202
        assert wait_job(client, headers, response.json()["id"])["active"]
    data = search(client, first, "Kho lưu trữ dùng gì?", top_k=3)
    assert len(data["hits"]) == 1
    hit = data["hits"][0]
    assert hit["file_id"] == source and "Qdrant" in hit["text"]
    assert hit["provenance"]["owner_id"] == str(auth["principals"][0])
    assert "foreign-secret-marker" not in json.dumps(data)
    other = search(client, second, "Kho lưu trữ dùng gì?")
    assert {hit["file_id"] for hit in other["hits"]} == {foreign}
    assert search(client, first, "Qdrant", file_ids=[foreign])["hits"] == []
    replacement = upload(
        client,
        first,
        "Nguồn mới: lưu trữ vector vẫn dùng Qdrant.".encode(),
        "retrieval-new",
    )
    admitted = client.post(f"/api/v1/files/{replacement}/index", headers=first)
    assert wait_job(client, first, admitted.json()["id"])["active"]
    assert client.delete("/api/v1/files/" + source, headers=first).status_code in {
        202,
        204,
    }
    data = search(client, first, "Lưu trữ vector dùng gì?")
    assert {hit["file_id"] for hit in data["hits"]} == {replacement}
    assert (ROOT / "configs/embedding-selected.json").read_bytes() == selected_before


def test_actual_query_overflow_and_strict_body(retrieval_client):
    """Reject overlong instructed input without truncation and refuse caller ACL/filter injection."""
    client, auth = retrieval_client
    headers = auth["headers"][0]
    response = client.post(
        "/api/v1/retrieval/search", headers=headers, json=dict(query=" x" * 512)
    )
    assert (
        response.status_code == 422
        and response.json()["detail"]["code"] == "ingestion_token_limit"
    )
    for extra in [
        dict(owner_id=str(auth["principals"][1])),
        dict(filter=dict(must=[])),
        dict(model="replacement"),
    ]:
        assert (
            client.post(
                "/api/v1/retrieval/search",
                headers=headers,
                json=dict(query="private", **extra),
            ).status_code
            == 422
        )
