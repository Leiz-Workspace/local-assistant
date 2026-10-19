"""Verify actual localhost TCP grounded generation/citation delivery and joined request resources on the existing CORE path."""

import hashlib
import json
import logging
from pathlib import Path

import httpx
from test_grounded_http import grounded_client as grounded_client
from test_grounded_http import index_source
from test_ingestion_http import upload
from test_reranker_tcp_trial import localhost_server

logger = logging.getLogger(__name__)


def test_actual_grounded_core_tcp_citation_and_joined_delivery(grounded_client):
    """Deliver a real CORE answer over Uvicorn/TCP and verify exact source-field identity after handler cleanup."""
    client, auth = grounded_client
    headers = auth["headers"][0]
    text = "The grounded TCP fixture uses port 6123."
    identifier = upload(client, headers, text.encode(), "grounded-tcp")
    index_source(client, headers, identifier)
    with (
        localhost_server(client) as base_url,
        httpx.Client(
            base_url=base_url, trust_env=False, timeout=90, follow_redirects=False
        ) as wire,
    ):
        response = wire.post(
            "/api/v1/grounded/answer",
            headers=headers,
            json=dict(
                query="What port does the grounded TCP fixture use?",
                file_ids=[identifier],
            ),
        )
        assert response.status_code == 200
        assert response.headers["cache-control"] == "private, no-store"
        assert response.headers["x-content-type-options"] == "nosniff"
        data = response.json()
        assert data["status"] == "answered" and "6123" in data["answer"]
        for cite in data["citations"]:
            assert (
                cite["file_id"] == identifier
                and cite["source_sha256"] == hashlib.sha256(text.encode()).hexdigest()
            )
            span = cite["source_span"]
            assert (
                span["locator"] == "file:" + identifier + "#text"
                and span["field"] == "text"
            )
            assert text[span["start"] : span["end"]] == cite["quote"]
            assert cite["provenance"]["owner_id"] == str(auth["principals"][0])
    service = client.app.state.grounded_service
    assert not service.operations and not service.admission.locked()
    assert (
        not service.retrieval.admission.locked() and not service.retrieval.files.active
    )
    report = dict(
        description="Actual existing CORE/approved embedding/source authorization and exact native citation delivered over ephemeral localhost Uvicorn/TCP; original fixture event loop, no production flag/config/model change.",
        actual_tcp=True,
        result=data,
        request_handlers_joined=True,
        source_and_model_admission_released=True,
        temporary_server_joined=True,
        source_sha256=hashlib.sha256(text.encode()).hexdigest(),
    )
    path = Path("data/backups/d28-latest-grounded-tcp.json")
    path.touch(mode=0o600, exist_ok=True)
    path.chmod(0o600)
    path.write_text(json.dumps(report, indent=2) + "\n")
    logger.info("grounded_actual_tcp_citation_and_cleanup_verified")
