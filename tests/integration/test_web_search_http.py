"""Verify authenticated bounded search HTTP/TCP, private errors, quotas and response ownership using controlled ports."""

import asyncio
import json
import logging
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from test_reranker_tcp_trial import localhost_server
from test_search_pipeline import FixtureCore, FixtureSearch
from test_web_search_policy import FakeClock

from apps.api.main import app
from apps.api.routes.web_search import WebSearchResponse
from src.application.services.search_pipeline import SearchPipeline
from src.application.services.web_search_policy import WebSearchError, WebSearchQuota

logger = logging.getLogger(__name__)


@pytest.fixture
def search_client(auth_settings, monkeypatch):
    """Enable the real optional service on a two-principal fixture without database/provider/model network calls."""
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("ASSISTANT_WEB_SEARCH_ENABLED", "1")
    with TestClient(app, client=("127.0.0.1", 43000)) as client:
        current = app.state.web_search_service
        current.pipeline = SearchPipeline(
            provider_id="fixture", provider=FixtureSearch(), inference=FixtureCore()
        )
        current.quota = WebSearchQuota(clock=FakeClock())
        yield client, auth_settings, current
    assert (
        app.state.web_search_service is None
        and current.closing
        and not current.operations
    )


def post(client, auth, **body):
    """Send one fixture-owner query through the actual guarded POST route."""
    return client.post(
        "/api/v1/web/search",
        headers=auth["headers"][0],
        json=body or dict(query="atlas"),
    )


def assert_private(response):
    """Require private no-store and inert JSON content handling on successes and rejections."""
    assert response.headers["cache-control"] == "private, no-store"
    assert response.headers["x-content-type-options"] == "nosniff"


def test_disabled_api_returns_private_unavailable_without_dependency_calls(
    auth_settings, monkeypatch
):
    """Keep registered search unavailable by default without creating an optional provider or model client."""
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("ASSISTANT_WEB_SEARCH_ENABLED", raising=False)
    with TestClient(app, client=("127.0.0.1", 43000)) as client:
        assert app.state.web_search_service is None
        response = post(client, auth_settings)
    assert response.status_code == 503
    assert response.json() == dict(detail=dict(code="web_search_unavailable"))
    assert_private(response)


def test_serialization_failure_closes_context_and_retains_charge(
    search_client, monkeypatch
):
    """Release the owned operation when response construction fails before ASGI delivery."""
    client, auth, current = search_client

    def fail_render(self, content):
        """Inject a private serialization failure without changing the pipeline or response cleanup."""
        raise ValueError("private-serialization-fixture")

    monkeypatch.setattr(WebSearchResponse, "render", fail_render)
    response = post(client, auth)
    assert (
        response.status_code == 503
        and "private-serialization-fixture" not in response.text
    )
    assert_private(response)
    assert (
        current.quota.total == 1
        and not current.operations
        and not current.admission.locked()
    )


def test_success_has_normalized_query_original_citations_and_private_audit(
    search_client, caplog
):
    """Bind normalized explicit input to original fixture sources without identity/context/token transmission."""
    caplog.set_level(logging.INFO)
    client, auth, current = search_client
    response = post(client, auth, query="  PRIVATE-QUERY-FIXTURE  ")
    assert response.status_code == 200
    assert_private(response)
    payload = response.json()
    assert (
        payload["query"] == "PRIVATE-QUERY-FIXTURE" and payload["normalization_applied"]
    )
    assert payload["citations"][0]["url"] == "https://example.org/atlas"
    assert payload["semantic_validation"] is False
    assert current.pipeline.provider.calls == [
        dict(query="PRIVATE-QUERY-FIXTURE", max_results=5)
    ]
    assert (
        not current.operations
        and not current.admission.locked()
        and current.quota.total == 1
    )
    sent = json.dumps(current.pipeline.inference.calls)
    assert all(
        token not in sent + caplog.text + response.text for token in auth["tokens"]
    )
    assert "PRIVATE-QUERY-FIXTURE" not in caplog.text and "G-17" not in caplog.text


@pytest.mark.parametrize(
    "body",
    [
        {},
        dict(query=None),
        dict(query=1),
        dict(query=True),
        dict(query=[]),
        dict(query=""),
        dict(query="  "),
        dict(query="x\nvalue"),
        dict(query="!bing value"),
        dict(query="value :en"),
        dict(query="ế" * 171),
        *[
            dict(query="atlas", **{key: "FORGED-AUTHORITY"})
            for key in [
                "owner_id",
                "provider",
                "engines",
                "model",
                "max_results",
                "url",
                "files",
                "memory",
                "clock",
            ]
        ],
    ],
)
def test_invalid_or_authority_fields_never_reach_pipeline(search_client, body):
    """Reject strict field/type/selector/byte violations without quota charge or hidden context selection."""
    client, auth, current = search_client
    response = client.post("/api/v1/web/search", headers=auth["headers"][0], json=body)
    assert response.status_code == 422
    assert_private(response)
    assert "FORGED-AUTHORITY" not in response.text
    assert (
        current.quota.total == 0
        and current.pipeline.provider.calls == current.pipeline.inference.calls == []
    )


@pytest.mark.parametrize(
    "raw,status",
    [
        (b'{"query":"first","query":"second"}', 422),
        (b'{"query":NaN}', 422),
        (b'{"query":"\\ud800"}', 422),
        (b"[]", 422),
        (b"\xff", 422),
        (b"{", 422),
        (b" " * 2049, 413),
    ],
)
def test_strict_raw_json_and_stream_limit(search_client, raw, status):
    """Bound raw bytes and reject ambiguous/invalid JSON before framework serialization can expose input."""
    client, auth, current = search_client
    response = client.post(
        "/api/v1/web/search",
        headers={**auth["headers"][0], "Content-Type": "application/json"},
        content=raw,
    )
    assert response.status_code == status
    assert_private(response)
    assert current.quota.total == 0 and current.pipeline.provider.calls == []


@pytest.mark.parametrize(
    "headers",
    [
        {"Content-Type": "text/plain"},
        {"Content-Type": "application/json", "Content-Encoding": "gzip"},
    ],
)
def test_compression_and_non_json_media_are_not_body_authority(search_client, headers):
    """Deny unapproved representations before decoding, quota charge or provider work."""
    client, auth, current = search_client
    response = client.post(
        "/api/v1/web/search",
        headers={**auth["headers"][0], **headers},
        content=b'{"query":"atlas"}',
    )
    assert response.status_code == 415
    assert_private(response)
    assert current.quota.total == 0 and current.pipeline.provider.calls == []


@pytest.mark.parametrize(
    "extra",
    [
        {"Origin": "http://example.invalid"},
        {"X-Forwarded-For": "127.0.0.1"},
        {"Forwarded": "for=127.0.0.1"},
        {"X-Real-IP": "127.0.0.1"},
    ],
)
def test_origin_and_proxy_headers_are_denied_before_query_work(search_client, extra):
    """Reuse direct-local policy without trusting client forwarding or browser-origin metadata."""
    client, auth, current = search_client
    response = client.post(
        "/api/v1/web/search",
        headers={**auth["headers"][0], **extra},
        json=dict(query="atlas"),
    )
    assert response.status_code == 403
    assert_private(response)
    assert current.quota.total == 0 and current.pipeline.provider.calls == []


def test_rate_headers_two_principals_and_no_refund(search_client):
    """Enforce independent four-request principal windows and Retry-After without charging denied retries."""
    client, auth, current = search_client
    for _ in range(4):
        assert post(client, auth).status_code == 200
    response = post(client, auth)
    assert response.status_code == 429 and response.headers["retry-after"] == "60"
    assert_private(response)
    assert current.quota.total == 4
    assert (
        client.post(
            "/api/v1/web/search", headers=auth["headers"][1], json=dict(query="other")
        ).status_code
        == 200
    )
    assert current.quota.total == 5 and len(current.pipeline.provider.calls) == 5
    current.quota.clock.value = 60
    assert post(client, auth).status_code == 200 and current.quota.total == 1


def test_disabled_busy_and_dependency_failures_are_private_without_hidden_retry(
    search_client,
):
    """Preserve finite status codes, failed-attempt charging and zero work on unavailable/busy admission."""
    client, auth, current = search_client
    client.portal.call(current.admission.acquire)
    try:
        response = post(client, auth)
        assert response.status_code == 429 and current.quota.total == 0
    finally:
        client.portal.call(current.admission.release)
    current.pipeline.provider.error = RuntimeError("PRIVATE-DEPENDENCY-ERROR")
    response = post(client, auth)
    assert response.status_code == 503 and current.quota.total == 1
    assert (
        "PRIVATE-DEPENDENCY-ERROR" not in response.text
        and len(current.pipeline.provider.calls) == 1
    )
    assert_private(response)
    current.closing = True
    response = post(client, auth)
    assert response.status_code == 503 and current.quota.total == 1


def test_real_tcp_guards_and_response_completion(search_client):
    """Exercise actual Uvicorn/socket auth/private headers and joined request completion with controlled backend ports."""
    client, auth, current = search_client
    with (
        localhost_server(client) as origin,
        httpx.Client(base_url=origin, trust_env=False, timeout=5) as wire,
    ):
        denied = wire.post("/api/v1/web/search", json=dict(query="atlas"))
        assert denied.status_code == 401
        assert_private(denied)
        response = wire.post(
            "/api/v1/web/search",
            headers=auth["headers"][0],
            json=dict(query="  Atlas  "),
        )
        assert response.status_code == 200 and response.json()["query"] == "Atlas"
        assert_private(response)
    assert (
        not current.admission.locked()
        and not current.operations
        and current.quota.total == 1
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("fault", ["header", "body", "cancel"])
async def test_send_failure_or_cancellation_releases_entered_response_context(fault):
    """Close a real joined service operation after response send faults without refunding quota or rerunning work."""
    from apps.api.services.web_search import WebSearchService

    current = WebSearchService(
        SearchPipeline(
            provider_id="fixture", provider=FixtureSearch(), inference=FixtureCore()
        ),
        clock=FakeClock(),
    )
    context = current.operation(uuid4(), "atlas")
    payload = await context.__aenter__()
    response = WebSearchResponse(context, payload)

    async def receive():
        """Provide an unused inert ASGI receive endpoint for the finite response."""
        return dict(type="http.disconnect")

    async def send(message):
        """Inject a header/body error or actual task cancellation at response delivery."""
        target = (
            "http.response.start"
            if fault in {"header", "cancel"}
            else "http.response.body"
        )
        if message["type"] == target:
            if fault == "cancel":
                raise asyncio.CancelledError()
            raise OSError("controlled-send-failure")

    expected = asyncio.CancelledError if fault == "cancel" else OSError
    with pytest.raises(expected):
        await response(dict(type="http"), receive, send)
    assert (
        not current.operations
        and not current.admission.locked()
        and current.quota.total == 1
    )
    assert (
        len(current.pipeline.provider.calls)
        == len(current.pipeline.inference.calls)
        == 1
    )


@pytest.mark.asyncio
async def test_response_serialization_budget_closes_context_when_constructor_fails():
    """Enforce the encoded64KiB cap before headers while preserving the entered slot until explicit failure cleanup."""
    from apps.api.services.web_search import WebSearchService

    current = WebSearchService(
        SearchPipeline(
            provider_id="fixture", provider=FixtureSearch(), inference=FixtureCore()
        ),
        clock=FakeClock(),
    )
    context = current.operation(uuid4(), "atlas")
    payload = await context.__aenter__()
    try:
        with pytest.raises(WebSearchError, match="web_search_response_limit"):
            WebSearchResponse(context, dict(payload, answer="x" * 65537))
    finally:
        await context.__aexit__(None, None, None)
    assert (
        not current.admission.locked()
        and not current.operations
        and current.quota.total == 1
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("remote,expected", [(False, 401), (True, 403)])
async def test_authentication_and_local_policy_precede_body_receive(
    auth_settings, remote, expected
):
    """Prove the real ASGI route never consumes request bytes from unauthenticated or nonlocal callers."""
    consumed, sent = [], []

    async def receive():
        """Detect forbidden body consumption before request authentication completes."""
        consumed.append(True)
        raise AssertionError("body_read_before_auth")

    async def send(message):
        """Collect only finite ASGI response events for the denied request."""
        sent.append(message)

    scope = dict(
        type="http",
        asgi=dict(version="3.0"),
        http_version="1.1",
        method="POST",
        scheme="http",
        path="/api/v1/web/search",
        raw_path=b"/api/v1/web/search",
        query_string=b"",
        root_path="",
        headers=[(b"content-type", b"application/json")],
        client=("10.0.0.8" if remote else "127.0.0.1", 1234),
        server=("127.0.0.1", 80),
    )
    await app(scope, receive, send)
    assert not consumed and sent[0]["status"] == expected
