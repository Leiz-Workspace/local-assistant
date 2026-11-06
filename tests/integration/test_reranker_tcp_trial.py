"""Verify actual localhost Uvicorn/TCP retrieval and isolated reranking without changing persistent application routing."""

import hashlib
import json
import logging
import socket
import time
from contextlib import contextmanager
from pathlib import Path

import httpx
import uvicorn
from test_ingestion_http import upload, wait_job
from test_reranker_http_trial import actual_trial_flag as actual_trial_flag
from test_reranker_http_trial import trial_client as trial_client
from test_retrieval_http import retrieval_client as retrieval_client

from scripts.qwen_reranker_trial_worker import ROOT, verify_freeze
from scripts.reranker_request_probe import load_query

logger = logging.getLogger(__name__)


@contextmanager
def localhost_server(client):
    """Serve on an ephemeral loopback socket in the existing fixture event loop and join shutdown on exit."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    sock.listen(32)
    port = sock.getsockname()[1]
    server = uvicorn.Server(
        uvicorn.Config(
            client.app,
            lifespan="off",
            access_log=False,
            log_level="error",
            proxy_headers=False,
            timeout_graceful_shutdown=5,
        )
    )

    async def serve():
        """Reuse the exact lifespan-owned database/model resources in their original event loop."""
        await server.serve(sockets=[sock])

    future = client.portal.start_task_soon(serve)
    try:
        deadline = time.monotonic() + 10
        while not server.started and not future.done() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert server.started
        logger.info("trial_loopback_tcp_server_started")
        yield "http://127.0.0.1:" + str(port)
    finally:
        server.should_exit = True
        try:
            future.result(timeout=15)
        finally:
            sock.close()
            logger.info("trial_loopback_tcp_server_joined")


def test_actual_localhost_tcp_authenticated_ranking_and_rollback(trial_client):
    """Measure actual TCP response completion and verify auth/origin/owner fences plus dense rollback."""
    verify_freeze()
    frozen = json.loads(
        (ROOT / "docs/evidence/d27-t03-tcp-trial-freeze.json").read_text()
    )
    assert (
        frozen["test_sha256"] == hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    )
    client, auth, dense, trial = trial_client
    query = load_query()
    headers, foreign = auth["headers"]
    files = []
    for document in query["documents"][:2]:
        identifier = upload(
            client, headers, document["text"].encode(), "tcp-" + document["id"]
        )
        admitted = client.post(f"/api/v1/files/{identifier}/index", headers=headers)
        assert (
            admitted.status_code == 202
            and wait_job(client, headers, admitted.json()["id"])["active"]
        )
        files.append(identifier)
    observations = []
    with (
        localhost_server(client) as base_url,
        httpx.Client(
            base_url=base_url, trust_env=False, timeout=90, follow_redirects=False
        ) as wire,
    ):
        body = dict(query=query["text"], top_k=10, file_ids=files)
        assert wire.post("/api/v1/retrieval/search", json=body).status_code == 401
        assert (
            wire.post(
                "/api/v1/retrieval/search",
                json=body,
                headers={**headers, "Origin": "http://example.invalid"},
            ).status_code
            == 403
        )
        try:
            for mode, service in [
                ("dense", dense),
                ("evaluation_only_reranker", trial),
                ("dense_after_disable", dense),
            ]:
                client.app.state.retrieval_service = service
                started = time.monotonic()
                response = wire.post(
                    "/api/v1/retrieval/search", json=body, headers=headers
                )
                seconds = time.monotonic() - started
                assert response.status_code == 200
                assert (
                    response.headers["cache-control"] == "private, no-store"
                    and response.headers["x-content-type-options"] == "nosniff"
                )
                data = response.json()
                assert {row["file_id"] for row in data["hits"]} == set(files)
                assert all(
                    row["provenance"]["owner_id"] == str(auth["principals"][0])
                    for row in data["hits"]
                )
                if mode == "evaluation_only_reranker":
                    assert data["ranking"] == "evaluation_only_qwen_batch4" and all(
                        "reranker_score" in row for row in data["hits"]
                    )
                else:
                    assert "ranking" not in data and all(
                        "reranker_score" not in row for row in data["hits"]
                    )
                observations.append(
                    dict(
                        mode=mode,
                        seconds=seconds,
                        response_bytes=len(response.content),
                        response_sha256=hashlib.sha256(response.content).hexdigest(),
                        points=[
                            dict(
                                point_id=row["point_id"],
                                file_id=row["file_id"],
                                source_sha256=row["source_sha256"],
                                generation=row["generation"],
                            )
                            for row in data["hits"]
                        ],
                    )
                )
            response = wire.post("/api/v1/retrieval/search", json=body, headers=foreign)
            assert response.status_code == 200 and response.json()["hits"] == []
        finally:
            client.app.state.retrieval_service = trial
    assert (
        {row["point_id"] for row in observations[0]["points"]}
        == {row["point_id"] for row in observations[1]["points"]}
        == {row["point_id"] for row in observations[2]["points"]}
    )
    report = dict(
        description="Actual ephemeral localhost Uvicorn/TCP authenticated dense/reranked/dense rollback responses using the same lifespan-owned test resources; no production config or separate-process/load certification.",
        transport="actual_loopback_Uvicorn_TCP_same_fixture_event_loop",
        observations=observations,
        unauthenticated_denied=True,
        origin_denied=True,
        foreign_owner_empty=True,
        source_point_identity_preserved=True,
        temporary_server_joined=True,
        persistent_routing_changed=False,
        adoption_approved=False,
    )
    output = Path("data/backups/d27-t03-latest-tcp-trial.json")
    output.touch(mode=0o600, exist_ok=True)
    output.chmod(0o600)
    output.write_text(json.dumps(report, indent=2) + "\n")
    logger.info("trial_tcp_auth_ranking_rollback_verified")
