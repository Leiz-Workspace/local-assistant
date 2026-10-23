"""Verify guarded stateless inference and immediate credential revocation over actual disposable loopback Uvicorn/TCP."""

import json

import httpx
from test_reranker_tcp_trial import localhost_server
from test_stateless_security import PAYLOAD
from test_stateless_security import secured_chat as secured_chat


def test_native_stateless_auth_origin_and_reloaded_revocation(secured_chat):
    """Use actual TCP routing with a fixture gateway and prove authorization denial precedes backend work."""
    client, gateway, auth = secured_chat
    with (
        localhost_server(client) as base,
        httpx.Client(
            base_url=base, trust_env=False, follow_redirects=False, timeout=10
        ) as wire,
    ):
        assert wire.post("/api/v1/chat/completions", json=PAYLOAD).status_code == 401
        assert (
            wire.post(
                "/api/v1/chat/completions",
                json=PAYLOAD,
                headers={**auth["headers"][0], "Origin": "https://attacker.example"},
            ).status_code
            == 403
        )
        accepted = wire.post(
            "/api/v1/chat/completions", json=PAYLOAD, headers=auth["headers"][0]
        )
        assert (
            accepted.status_code == 200
            and accepted.headers["cache-control"] == "private, no-store"
        )
        assert gateway.complete.await_count == 1
        principals = json.loads(auth["path"].read_text())
        principals["principals"] = principals["principals"][1:]
        auth["path"].write_text(json.dumps(principals))
        assert (
            wire.post(
                "/api/v1/chat/completions", json=PAYLOAD, headers=auth["headers"][0]
            ).status_code
            == 401
        )
        assert gateway.complete.await_count == 1
