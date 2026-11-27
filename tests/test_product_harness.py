"""Exercise scoped skills, real workspace evidence, cancellation and the optional browser/API boundary."""

import asyncio
import hashlib
import json
import logging
import os
import re
import shutil
import subprocess
import time
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from apps.api.services.workspaces import WorkspaceService
from apps.harness.main import compose
from apps.harness.assets import PIN, VERSION
from apps.harness.routes import RunInput
from apps.harness.service import HarnessError, ProductHarness
from tests import test_workspace_reader

source_workspace = test_workspace_reader.source_workspace

LOGGER = logging.getLogger(__name__)
PREFIX = "/api/v1/harness"


class FixtureInference:
    """Supply controlled text and stream outputs without loading weights or accessing the network."""

    def __init__(self):
        """Record calls and optionally block one completion for cancellation/revocation tests."""
        self.calls, self.block = [], None

    async def complete(self, messages, **options):
        """Record evidence and the exact skill received by the task binder."""
        self.calls.append((messages, options))
        if self.block is not None:
            await self.block.wait()
        return {
            "choices": [
                {"message": {"content": "fixture answer"}, "finish_reason": "stop"}
            ]
        }, {"input_tokens": 10}

    async def stream(self, messages, **options):
        """Emit two actual asynchronous chunks for transport-contract tests."""
        self.calls.append((messages, options))
        yield b'data: {"choices":[{"delta":{"content":"fixture"}}]}\n\n'
        await asyncio.sleep(0)
        yield b"data: [DONE]\n\n"


def create_ui_fixture():
    """Expose an explicitly synthetic browser-QA app using real packaged UI assets and no model calls."""
    LOGGER.warning("product_browser_fixture_started_no_real_model")
    return compose(FastAPI(), inference=FixtureInference())


@pytest.mark.asyncio
async def test_real_workspace_task_reaches_injected_skill_and_evidence(
    source_workspace,
):
    """Read an actual fixture through the original dispatcher and bind only its reviewed skill."""
    catalog, spec, _, _ = source_workspace
    workspace = WorkspaceService(catalog)
    inference = FixtureInference()
    service = ProductHarness(inference, workspace)
    raw = Path("configs/skills/source-reader.v1.json").read_bytes()
    review = service.review(spec.owner_id, spec.workspace_id, raw)
    installation = service.install(
        spec.owner_id, spec.workspace_id, UUID(review["review_id"]), review["sha256"]
    )
    request = RunInput(
        workspace_id=spec.workspace_id,
        task="Explain the exact source.",
        skill=installation["installation_id"],
        tools=[{"name": "workspace.read", "arguments": {"path": "src/main.py"}}],
    )
    row = service.start(spec.owner_id, request)
    identifier = UUID(row["id"])
    await service.tasks[identifier]
    result = service.get(spec.owner_id, identifier)
    assert result["state"] == "succeeded"
    assert inference.calls[0][1]["skill"].identifier == "source-reader"
    assert b"src/main.py" in inference.calls[0][1]["evidence"][0]
    assert [event["sequence"] for event in result["events"]] == [1, 2, 3]
    with pytest.raises(HarnessError, match="run_not_found"):
        service.get(uuid4(), identifier)
    await service.close()
    await workspace.shutdown()
    assert not workspace.operations
    LOGGER.info("test_product_actual_workspace_binding_verified")


@pytest.mark.asyncio
async def test_cancellation_and_revocation_join_workers():
    """Reject in-flight output after skill removal and cancel queued or running tasks without retries."""
    owner, workspace_id = uuid4(), uuid4()
    inference = FixtureInference()
    inference.block = asyncio.Event()
    service = ProductHarness(inference)
    review = service.review(
        owner, workspace_id, Path("configs/skills/source-reader.v1.json").read_bytes()
    )
    installation = service.install(
        owner, workspace_id, UUID(review["review_id"]), review["sha256"]
    )
    request = RunInput(
        workspace_id=workspace_id,
        task="Read this task",
        skill=installation["installation_id"],
    )
    identifier = UUID(service.start(owner, request)["id"])
    await asyncio.sleep(0)
    installed = service.installed(
        owner, workspace_id, UUID(installation["installation_id"])
    )
    service.skills.uninstall(owner, workspace_id, installed)
    inference.block.set()
    await service.tasks[identifier]
    assert service.get(owner, identifier)["error"]["code"] == "skill_revoked"
    assert "result" not in service.get(owner, identifier)
    inference.block = asyncio.Event()
    second = UUID(
        service.start(owner, RunInput(workspace_id=workspace_id, task="Wait"))["id"]
    )
    await asyncio.sleep(0)
    assert (await service.cancel(owner, second))["state"] == "cancelled"
    assert service.tasks[second].done()
    assert service.remove(owner, second)["removed"]
    await service.close()


@pytest.mark.parametrize(
    "tool", ["shell", "patch.apply", "checks.run", "network.fetch"]
)
def test_write_and_unknown_tools_fail_before_admission(tool):
    """Keep the first product task surface strictly inside existing read-only schemas."""
    with pytest.raises(ValueError):
        RunInput(
            workspace_id=uuid4(), task="Task", tools=[{"name": tool, "arguments": {}}]
        )


def fixture_assets(tmp_path):
    """Write a minimal pinned UI asset tree with a matching receipt."""
    assets = tmp_path / "assets"
    assets.mkdir()
    index = b"<html><head></head><body>PINNED_UI_FIXTURE</body></html>"
    (assets / "index.html").write_bytes(index)
    (assets / "receipt.json").write_text(
        json.dumps(
            {
                "files": {"index.html": hashlib.sha256(index).hexdigest()},
                "source_pin": PIN,
                "version": VERSION,
            }
        )
    )
    return assets


@pytest.fixture
def product_client(auth_settings, tmp_path):
    """Create a direct-loopback fixture app with isolated assets and process-local product state."""
    assets = fixture_assets(tmp_path)
    inference = FixtureInference()
    app = compose(FastAPI(), inference=inference, asset_root=assets)
    with TestClient(
        app, base_url="http://127.0.0.1:7090", client=("127.0.0.1", 49001)
    ) as client:
        yield client, inference, auth_settings, assets


def bearer(settings, index=0):
    """Build finite JSON request headers for an independently authenticated test principal."""
    return {**settings["headers"][index], "Content-Type": "application/json"}


def pair(client, settings):
    """Pair the fixture browser through the bearer bootstrap and same-origin cookie exchange."""
    response = client.post(PREFIX + "/ui-pairings", headers=bearer(settings), json={})
    assert response.status_code == 200
    code = response.json()["code"]
    response = client.post(
        "/ui/pairings",
        headers={"Origin": "http://127.0.0.1:7090", "X-Harness-UI": "1"},
        json={"code": code},
    )
    assert response.status_code == 200
    assert "HttpOnly" in response.headers["set-cookie"]
    return code


def test_auto_session_bootstrap_opens_root_without_pairing(product_client, monkeypatch):
    """Allow the container UI to load first and establish its HttpOnly session automatically."""
    client, _, _, _ = product_client
    monkeypatch.setenv("ASSISTANT_WEB_AUTO_SESSION", "1")
    assert client.get("/").status_code == 200
    assert (
        client.post("/ui/session/bootstrap", headers=UI_HEADERS, json={}).status_code
        == 403
    )


def test_auto_session_bootstrap_requires_single_local_principal(
    product_client, monkeypatch
):
    """Bootstrap the browser cookie without exposing a bearer token to the product UI."""
    client, _, settings, _ = product_client
    monkeypatch.setenv("ASSISTANT_WEB_AUTO_SESSION", "1")
    assert (
        client.post("/ui/session/bootstrap", headers=UI_HEADERS, json={}).status_code
        == 403
    )

    single = settings["path"]
    payload = json.loads(single.read_text())
    single.write_text(json.dumps({"principals": payload["principals"][:1]}))
    single.chmod(0o600)
    response = client.post("/ui/session/bootstrap", headers=UI_HEADERS, json={})
    assert response.status_code == 200
    assert "HttpOnly" in response.headers["set-cookie"]
    assert client.get(PREFIX + "/status").status_code == 200


def test_browser_calls_without_cookie_get_401_so_the_ui_can_rebootstrap(
    product_client,
):
    """A browser POST always carries Origin; without a cookie it must get 401, not the CLI guard's 403."""
    client, inference, _, _ = product_client
    body = {"messages": [{"role": "user", "content": "Hi"}]}
    response = client.post(PREFIX + "/chat", headers=UI_HEADERS, json=body)
    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "ui_session_required"
    assert inference.calls == []


def test_bootstrap_replaces_the_presented_session(product_client, monkeypatch):
    """Repeated bootstraps rotate one cookie instead of accumulating sessions."""
    client, _, settings, _ = product_client
    monkeypatch.setenv("ASSISTANT_WEB_AUTO_SESSION", "1")
    payload = json.loads(settings["path"].read_text())
    settings["path"].write_text(json.dumps({"principals": payload["principals"][:1]}))
    settings["path"].chmod(0o600)
    assert (
        client.post("/ui/session/bootstrap", headers=UI_HEADERS, json={}).status_code
        == 200
    )
    first = client.cookies.get("assistant_harness_session")
    assert (
        client.post("/ui/session/bootstrap", headers=UI_HEADERS, json={}).status_code
        == 200
    )
    second = client.cookies.get("assistant_harness_session")
    assert first != second
    assert len(client.app.state.browser_sessions.sessions) == 1
    client.cookies.set("assistant_harness_session", first)
    assert client.get(PREFIX + "/status", headers=UI_HEADERS).status_code == 401


def test_full_session_table_evicts_the_oldest_session():
    """A full table must not lock the owner out of new sessions or pairings."""
    from apps.harness.browser import BrowserSessions

    now = [0.0]
    sessions = BrowserSessions(clock=lambda: now[0])
    owner = uuid4()
    for _ in range(64):
        sessions.create_session(owner, "digest")
        now[0] += 1
    oldest = min(row[2] for row in sessions.sessions.values())
    sessions.create_session(owner, "digest")
    assert len(sessions.sessions) == 64
    assert oldest not in {row[2] for row in sessions.sessions.values()}
    code = sessions.pairing(owner, "digest")
    assert sessions.exchange(code)


def test_cookie_session_mutations_accept_browser_origin_and_require_csrf(
    product_client,
):
    """Browser POSTs always carry Origin; the cookie path must accept it while the bearer path keeps refusing it."""
    client, inference, settings, _ = product_client
    pair(client, settings)
    body = {"messages": [{"role": "user", "content": "Hi"}]}
    answered = client.post(PREFIX + "/chat", headers=UI_HEADERS, json=body)
    assert answered.status_code == 200
    assert answered.json()["result"]["choices"][0]["message"]["content"]
    missing_marker = {"Origin": "http://127.0.0.1:7090"}
    assert (
        client.post(PREFIX + "/chat", headers=missing_marker, json=body).status_code
        == 403
    )
    foreign = {"Origin": "https://example.com", "X-Harness-UI": "1"}
    assert client.post(PREFIX + "/chat", headers=foreign, json=body).status_code == 403
    assert len(inference.calls) == 1
    client.cookies.clear()
    bearer_with_origin = {**bearer(settings), "Origin": "http://127.0.0.1:7090"}
    refused = client.post(PREFIX + "/chat", headers=bearer_with_origin, json=body)
    assert refused.status_code == 403
    assert refused.json()["detail"]["code"] == "local_access_required"


def test_auto_session_bootstrap_is_disabled_by_default(product_client):
    """Keep the compatibility pairing flow as the only mode unless explicitly enabled."""
    client, _, _, _ = product_client
    assert (
        client.post("/ui/session/bootstrap", headers=UI_HEADERS, json={}).status_code
        == 403
    )


def test_product_shell_serves_only_listed_modules(product_client):
    """Shell modules are public static files; anything else under /aevra stays private or absent."""
    client, _, settings, _ = product_client
    for module in (
        "/aevra/api.js",
        "/aevra/store.js",
        "/aevra/ui/composer.js",
        "/aevra/app.css",
    ):
        response = client.get(module)
        assert response.status_code == 200, module
        assert response.headers["cache-control"] == "no-store"
        assert response.headers["x-content-type-options"] == "nosniff"
    assert client.get("/aevra/ui/missing.js").status_code == 401
    assert client.get("/aevra/brand.js").status_code == 401
    pair(client, settings)
    assert client.get("/aevra/ui/missing.js").status_code == 404
    assert client.get("/aevra/%2e%2e/routes.py").status_code == 404
    assert client.get("/aevra/index.html").status_code == 404


def test_api_owner_isolation_and_run_lifecycle(product_client):
    """Run a task through HTTP and prevent another principal from observing or cancelling it."""
    client, inference, settings, _ = product_client
    assert client.get(PREFIX + "/status").status_code == 401
    status = client.get(PREFIX + "/status", headers=bearer(settings))
    assert status.status_code == 200 and not status.json()["image_generation"]
    assert UUID(status.headers["x-request-id"])
    response = client.post(
        PREFIX + "/runs",
        headers=bearer(settings),
        json={"workspace_id": str(uuid4()), "task": "Explain"},
    )
    identifier = response.json()["id"]
    for _ in range(20):
        row = client.get(
            PREFIX + "/runs/" + identifier, headers=bearer(settings)
        ).json()
        if row["state"] in {"failed", "succeeded"}:
            break
        time.sleep(0.01)
    assert row["state"] == "succeeded" and len(inference.calls) == 1
    assert (
        client.get(
            PREFIX + "/runs/" + identifier, headers=bearer(settings, 1)
        ).status_code
        == 404
    )
    assert (
        client.post(
            PREFIX + "/runs/" + identifier + "/cancel",
            headers=bearer(settings, 1),
            json={},
        ).status_code
        == 404
    )
    assert client.delete(
        PREFIX + "/runs/" + identifier, headers=bearer(settings)
    ).json()["removed"]


def test_skill_api_exact_hash_review_and_cross_owner_install(product_client):
    """Require an unexpired owner review, exact digest and distinct explicit install request."""
    client, _, settings, _ = product_client
    workspace = str(uuid4())
    raw = Path("configs/skills/source-reader.v1.json").read_text()
    review = client.post(
        PREFIX + "/skills/reviews",
        headers=bearer(settings),
        json={"workspace_id": workspace, "manifest": raw},
    ).json()
    body = dict(
        workspace_id=workspace, review_id=review["review_id"], sha256=review["sha256"]
    )
    assert (
        client.post(
            PREFIX + "/skills/installations", headers=bearer(settings, 1), json=body
        ).status_code
        == 409
    )
    installed = client.post(
        PREFIX + "/skills/installations", headers=bearer(settings), json=body
    )
    assert installed.status_code == 200
    install_id = installed.json()["installation_id"]
    detail = client.get(
        PREFIX + f"/skills/installations/{install_id}?workspace_id={workspace}",
        headers=bearer(settings),
    )
    assert detail.status_code == 200 and detail.json()["sha256"] == review["sha256"]
    assert "instructions" in detail.json()
    assert (
        client.get(
            PREFIX + f"/skills/installations/{install_id}?workspace_id={workspace}",
            headers=bearer(settings, 1),
        ).status_code
        == 404
    )
    assert (
        client.post(
            PREFIX + "/skills/installations", headers=bearer(settings), json=body
        ).status_code
        == 404
    )
    assert client.get(PREFIX + "/skills", headers=bearer(settings, 1)).json() == []


def test_browser_pairing_cookie_acl_and_real_stream(product_client):
    """Keep app credentials out of assets and stream asynchronous chunks only after pairing."""
    client, inference, settings, _ = product_client
    shell = client.get("/")
    assert shell.status_code == 200 and settings["tokens"][0] not in shell.text
    assert client.get("/index.html").status_code == 401
    assert client.get(PREFIX + "/status", headers=UI_HEADERS).status_code == 401
    code = pair(client, settings)
    response = client.get("/index.html")
    assert response.status_code == 200 and "harness-bridge.js" in response.text
    assert settings["tokens"][0] not in response.text
    product = client.get("/")
    assert product.status_code == 200 and "/aevra/app.js" in product.text
    for module in ("/aevra/app.js", "/aevra/markdown.js", "/aevra/history.js"):
        script = client.get(module)
        assert script.status_code == 200
        assert script.headers["content-type"].startswith("text/javascript")
    assert "harness-bridge.js" not in product.text and "brand.js" not in product.text
    assert "worker-src 'none'" in response.headers["content-security-policy"]
    assert client.get("/props?autoload=false").status_code == 200
    escaped = client.get("/props?escape=1")
    assert escaped.status_code == 403
    assert escaped.json()["detail"]["code"] == "unsupported_query"
    queried = client.get("/?next=/props")
    assert queried.status_code == 403
    assert queried.json()["detail"]["code"] == "unsupported_query"
    repeated = client.post(
        "/ui/pairings",
        headers={"Origin": "http://127.0.0.1:7090", "X-Harness-UI": "1"},
        json={"code": code},
    )
    assert repeated.status_code == 401
    from apps.api.core.model_config import get_model_profile

    response = client.post(
        "/v1/chat/completions",
        headers={"Origin": "http://127.0.0.1:7090", "X-Harness-UI": "1"},
        json={
            "model": get_model_profile("core")["model_id"],
            "messages": [{"role": "user", "content": "Hello"}],
            "stream": True,
        },
    )
    assert response.status_code == 200
    assert "data: [DONE]" in response.text and "fixture" in response.text
    assert len(inference.calls) == 1
    response = client.post(
        "/v1/chat/completions",
        headers={"Origin": "http://127.0.0.1:7090", "X-Harness-UI": "1"},
        json={
            "messages": [
                {"role": "user", "content": "MODEL mode omits the model field"}
            ],
            "stream": True,
            "max_tokens": -1,
            "tool_choice": "auto",
        },
    )
    assert response.status_code == 200 and "fixture" in response.text
    assert client.get("/tools").json() == []


UI_HEADERS = {"Origin": "http://127.0.0.1:7090", "X-Harness-UI": "1"}


def sse_data(text):
    """Return the data payloads of an SSE body in order."""
    return [line[6:] for line in text.splitlines() if line.startswith("data: ")]


def test_browser_stream_lookup_accepts_at_most_64_conversations(product_client):
    """The UI's resumable-stream lookup returns no sessions for up to 64 ids and refuses more (HAR-002 point 2)."""
    client, _, settings, _ = product_client
    pair(client, settings)
    ids = [f"conv-{index}" for index in range(65)]
    allowed = client.post(
        "/v1/streams/lookup", headers=UI_HEADERS, json={"conversation_ids": ids[:64]}
    )
    assert allowed.status_code == 200 and allowed.json() == []
    for body in (
        {"conversation_ids": ids},
        {"conversation_ids": ids[:1], "extra": True},
        {"conversation_ids": ["x" * 257]},
        {"conversation_ids": "conv-1"},
    ):
        refused = client.post("/v1/streams/lookup", headers=UI_HEADERS, json=body)
        assert refused.status_code == 422
        assert refused.json()["error"]["code"] == "invalid_stream_lookup"


def test_browser_chat_error_mappings(product_client):
    """customJson collisions, non-text content, long chats and malformed bodies map to their documented codes before any model call (HAR-002 point 6)."""
    client, inference, settings, _ = product_client
    pair(client, settings)
    user = [{"role": "user", "content": "Hello"}]
    cases = [
        ({"messages": user, "stream": False}, 422, "stream_required"),
        (
            {"messages": user, "stream": True, "max_tokens": 256},
            422,
            "invalid_output_budget",
        ),
        ({"messages": user, "stream": True, "model": "x"}, 422, "unapproved_model"),
        (
            {"messages": user, "stream": True, "tools": [{"type": "function"}]},
            422,
            "browser_tools_not_supported",
        ),
        (
            {
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "image_url", "image_url": {"url": "data:,"}}
                        ],
                    }
                ],
                "stream": True,
            },
            422,
            "text_only",
        ),
        ({"messages": user * 257, "stream": True}, 422, "invalid_messages"),
        ({"messages": [], "stream": True}, 422, "invalid_messages"),
        (
            {"messages": [{"role": "user", "content": "x" * 262144}], "stream": True},
            413,
            "request_limit",
        ),
    ]
    for body, status, code in cases:
        response = client.post("/v1/chat/completions", headers=UI_HEADERS, json=body)
        assert (response.status_code, response.json()["error"]["code"]) == (
            status,
            code,
        )
    response = client.post(
        "/v1/chat/completions",
        headers={**UI_HEADERS, "Content-Type": "text/plain"},
        content=b"{}",
    )
    assert (response.status_code, response.json()["error"]["code"]) == (
        415,
        "json_required",
    )
    response = client.post(
        "/v1/chat/completions",
        headers={**UI_HEADERS, "Content-Type": "application/json"},
        content=b'{"stream": true, "stream": false, "messages": []}',
    )
    assert (response.status_code, response.json()["error"]["code"]) == (
        422,
        "invalid_json",
    )
    assert inference.calls == []


class FailingStreamInference(FixtureInference):
    """Send one real chunk, then fail the way the gateway does when the stream exceeds its byte limit."""

    async def stream(self, messages, **options):
        """Yield a delta, then raise the gateway's stream_limit error."""
        from apps.api.services.llama_gateway import GatewayError

        self.calls.append((messages, options))
        yield b'data: {"choices":[{"delta":{"content":"partial"}}]}\n\n'
        raise GatewayError("stream_limit")


def test_browser_stream_failure_is_reported_as_inference_unavailable(
    auth_settings, tmp_path, caplog
):
    """A mid-stream stream_limit reaches the UI only as the generic inference_unavailable SSE error with no [DONE] after it, and admission is released (HAR-002 point 6)."""
    inference = FailingStreamInference()
    app = compose(FastAPI(), inference=inference, asset_root=fixture_assets(tmp_path))
    with TestClient(
        app, base_url="http://127.0.0.1:7090", client=("127.0.0.1", 49001)
    ) as client:
        pair(client, auth_settings)
        with caplog.at_level(logging.INFO):
            response = client.post(
                "/v1/chat/completions",
                headers=UI_HEADERS,
                json={"messages": [{"role": "user", "content": "Hi"}], "stream": True},
            )
        assert response.status_code == 200
        events = sse_data(response.text)
        assert json.loads(events[0])["choices"][0]["delta"]["content"] == "partial"
        assert json.loads(events[1])["error"]["code"] == "inference_unavailable"
        assert len(events) == 2 and "[DONE]" not in response.text
        assert "stream_limit" not in response.text
        assert "harness_ui_stream_failed" in caplog.text
        assert not app.state.product_harness.admission.locked()


class BlockingStreamInference(FixtureInference):
    """Send one chunk, then wait until cancelled; record whether the upstream generator was closed."""

    def __init__(self):
        """Track the first chunk and the generator's cleanup."""
        super().__init__()
        self.sent, self.closed = asyncio.Event(), False

    async def stream(self, messages, **options):
        """Yield one delta and block until the consumer cancels."""
        self.calls.append((messages, options))
        try:
            yield b'data: {"choices":[{"delta":{"content":"first"}}]}\n\n'
            self.sent.set()
            await asyncio.Event().wait()
        finally:
            self.closed = True


@pytest.mark.asyncio
async def test_browser_stream_disconnect_cancels_closes_upstream_and_releases_admission(
    auth_settings, tmp_path, caplog
):
    """A client disconnect mid-stream (uvicorn's ASGI 2.3 path) logs harness_ui_stream_cancelled, closes the upstream stream and frees admission (HAR-002 point 5)."""
    import httpx

    inference = BlockingStreamInference()
    app = compose(FastAPI(), inference=inference, asset_root=fixture_assets(tmp_path))
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app, client=("127.0.0.1", 49001))
        async with httpx.AsyncClient(
            transport=transport, base_url="http://127.0.0.1:7090"
        ) as client:
            response = await client.post(
                PREFIX + "/ui-pairings", headers=bearer(auth_settings), json={}
            )
            code = response.json()["code"]
            response = await client.post(
                "/ui/pairings", headers=UI_HEADERS, json={"code": code}
            )
            assert response.status_code == 200
            cookie = response.headers["set-cookie"].split(";", 1)[0]
        body = json.dumps(
            {"messages": [{"role": "user", "content": "Hi"}], "stream": True}
        ).encode()
        scope = {
            "type": "http",
            "asgi": {"version": "3.0", "spec_version": "2.3"},
            "http_version": "1.1",
            "method": "POST",
            "scheme": "http",
            "path": "/v1/chat/completions",
            "raw_path": b"/v1/chat/completions",
            "query_string": b"",
            "root_path": "",
            "headers": [
                (b"host", b"127.0.0.1:7090"),
                (b"origin", b"http://127.0.0.1:7090"),
                (b"x-harness-ui", b"1"),
                (b"content-type", b"application/json"),
                (b"cookie", cookie.encode()),
            ],
            "client": ("127.0.0.1", 49001),
            "server": ("127.0.0.1", 7090),
        }
        disconnect, messages, delivered = asyncio.Event(), [], False

        async def receive():
            """Deliver the body once, then report a disconnect when the test asks for it."""
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": body, "more_body": False}
            await disconnect.wait()
            return {"type": "http.disconnect"}

        async def send(message):
            """Collect response messages."""
            messages.append(message)

        with caplog.at_level(logging.INFO):
            call = asyncio.create_task(app(scope, receive, send))
            await asyncio.wait_for(inference.sent.wait(), 5)
            assert app.state.product_harness.admission.locked()
            disconnect.set()
            await asyncio.wait_for(call, 5)
        assert messages[0]["status"] == 200
        assert b"first" in b"".join(m.get("body", b"") for m in messages[1:])
        assert "harness_ui_stream_cancelled" in caplog.text
        assert inference.closed
        assert not app.state.product_harness.admission.locked()


@pytest.mark.parametrize(
    "path",
    ["/models/load", "/models", "/tools", "/cors-proxy", "/slots", "/v1/stream/1"],
)
def test_native_mutation_surfaces_are_denied(product_client, path):
    """Block direct native control requests even when a browser session is valid."""
    client, _, settings, _ = product_client
    pair(client, settings)
    assert (
        client.post(
            path,
            headers={"Origin": "http://127.0.0.1:7090", "X-Harness-UI": "1"},
            json={},
        ).status_code
        == 403
    )


def test_browser_csrf_auth_revocation_and_asset_tampering(product_client):
    """Reject cross-site mutation, changed assets and cookies after original credential revocation."""
    client, _, settings, assets = product_client
    pair(client, settings)
    assert (
        client.post(
            "/ui/logout",
            headers={"Origin": "https://example.com", "X-Harness-UI": "1"},
            json={},
        ).status_code
        == 403
    )
    assert client.post("/ui/logout", json={}).status_code == 403
    (assets / "index.html").write_text("tampered")
    assert client.get("/index.html").status_code == 404
    assert client.get("/").status_code == 200
    settings["path"].write_text('{"principals":[]}')
    assert client.get("/props").status_code == 401


def test_default_entrypoint_is_unchanged(monkeypatch):
    """Preserve the original app identity unless the new product flag is explicitly enabled."""
    from apps.api.main import app
    from apps.harness.main import create_app

    monkeypatch.delenv("ASSISTANT_HARNESS_ENABLED", raising=False)
    assert create_app() is app
    monkeypatch.setenv("ASSISTANT_HARNESS_ENABLED", "invalid")
    with pytest.raises(RuntimeError):
        create_app()


def test_product_route_audit_redacts_tokens_and_query_strings(product_client, caplog):
    """Log allowed and denied operations using route templates without leaking authentication or inputs."""
    client, _, settings, _ = product_client
    caplog.set_level(logging.INFO, logger="apps.harness.routes")
    caplog.set_level(logging.INFO, logger="apps.harness.browser")
    client.get(PREFIX + "/status?private=DO_NOT_LOG", headers=bearer(settings))
    client.get(PREFIX + "/status", headers={"Content-Type": "application/json"})
    client.post(PREFIX + "/runs", headers=bearer(settings), json={"task": "DO_NOT_LOG"})
    client.post(
        PREFIX + "/generations",
        headers=bearer(settings),
        json={"kind": "image", "prompt": "DO_NOT_LOG"},
    )
    pair(client, settings)
    client.get("/props")
    text = caplog.text
    assert (
        "product_api_request" in text and "status=200" in text and "status=401" in text
    )
    assert "status=422" in text and "status=503" in text
    assert "harness_browser_request operation=properties" in text
    assert "DO_NOT_LOG" not in text and settings["tokens"][0] not in text


def test_bodiless_product_requests_need_no_json_media_type(product_client, caplog):
    """GET and DELETE without a body work without Content-Type, keep auth, private headers and the audit log."""
    client, _, settings, _ = product_client
    caplog.set_level(logging.INFO, logger="apps.harness.routes")
    plain = settings["headers"][0]
    status = client.get(PREFIX + "/status", headers=plain)
    assert status.status_code == 200 and status.json()["product"] == "Aevra"
    assert UUID(status.headers["x-request-id"])
    assert status.headers["cache-control"] == "private, no-store"
    assert status.headers["x-content-type-options"] == "nosniff"
    purged = client.delete(PREFIX + "/context/summaries", headers=plain)
    assert purged.status_code == 200 and purged.json() == {"purged": 0}
    assert client.get(PREFIX + "/runs", headers=plain).json() == []
    text = caplog.text
    assert "method=GET route=/api/v1/harness/status status=200" in text
    assert "method=DELETE route=/api/v1/harness/context/summaries status=200" in text
    assert client.get(PREFIX + "/status").status_code == 401
    assert client.delete(PREFIX + "/context/summaries").status_code == 401
    assert (
        client.get(
            PREFIX + "/status", headers={**plain, "Origin": "http://127.0.0.1:7090"}
        ).status_code
        == 403
    )
    assert (
        client.get(
            PREFIX + "/status", headers={**plain, "X-Forwarded-For": "192.0.2.1"}
        ).status_code
        == 403
    )


@pytest.mark.parametrize(
    "headers", [{"Content-Type": "text/plain"}, {}, {"Content-Type": "application/xml"}]
)
def test_product_request_bodies_still_require_json(product_client, headers):
    """A request that carries a body must declare application/json, whatever the method."""
    client, inference, settings, _ = product_client
    body = json.dumps({"workspace_id": str(uuid4()), "task": "Explain"}).encode()
    for method, path in (
        ("POST", "/runs"),
        ("POST", "/chat"),
        ("DELETE", "/context/summaries"),
    ):
        response = client.request(
            method,
            PREFIX + path,
            headers={**settings["headers"][0], **headers},
            content=body,
        )
        assert response.status_code == 415, (method, path)
        assert response.json() == {"detail": {"code": "json_required"}}
        assert response.headers["cache-control"] == "private, no-store"
    assert inference.calls == []
    assert (
        client.post(PREFIX + "/runs", content=body, headers=headers).status_code == 401
    )
    response = client.post(
        PREFIX + "/runs",
        headers={
            **settings["headers"][0],
            "Content-Type": "Application/JSON; charset=utf-8",
        },
        content=body,
    )
    assert response.status_code == 200 and response.json()["state"] == "created"


def test_product_request_body_limit_boundary(product_client):
    """Accept a body of exactly 262144 bytes for validation and refuse one byte more with 413."""
    client, inference, settings, _ = product_client
    prefix = b'{"workspace_id":"' + str(uuid4()).encode() + b'","task":"'
    for size, status in ((262144, 422), (262145, 413)):
        body = prefix + b"x" * (size - len(prefix) - 2) + b'"}'
        assert len(body) == size
        response = client.post(PREFIX + "/runs", headers=bearer(settings), content=body)
        assert response.status_code == status, size
    assert response.json() == {"detail": {"code": "request_limit"}}
    assert inference.calls == []


def test_ui_pairing_route_is_guarded_and_audited_by_the_harness_router(
    product_client, caplog
):
    """The pairing mint uses the harness route guard and audit, with or without a JSON body."""
    client, _, settings, _ = product_client
    caplog.set_level(logging.INFO, logger="apps.harness.routes")
    path = PREFIX + "/ui-pairings"
    minted = client.post(path, headers=bearer(settings), json={})
    assert minted.status_code == 200 and minted.json()["expires_in_seconds"] == 60
    assert UUID(minted.headers["x-request-id"])
    assert minted.headers["cache-control"] == "private, no-store"
    assert "method=POST route=/api/v1/harness/ui-pairings status=200" in caplog.text
    bodiless = client.post(path, headers=settings["headers"][0])
    assert bodiless.status_code == 200 and bodiless.json()["code"]
    assert client.post(path, json={}).status_code == 401
    assert "route=/api/v1/harness/ui-pairings status=401" in caplog.text
    assert (
        client.post(
            path,
            headers={**bearer(settings), "Origin": "http://127.0.0.1:7090"},
            json={},
        ).status_code
        == 403
    )
    refused = client.post(
        path,
        headers={**settings["headers"][0], "Content-Type": "text/plain"},
        content=b"{}",
    )
    assert refused.status_code == 415
    code = client.post(path, headers=bearer(settings), json={}).json()["code"]
    exchanged = client.post("/ui/pairings", headers=UI_HEADERS, json={"code": code})
    assert exchanged.status_code == 200
    assert settings["tokens"][0] not in caplog.text


def test_ui_pairing_capacity_is_audited(product_client, caplog):
    """The 33rd live pairing is refused with 429 pairing_capacity and logged by the route audit."""
    client, _, settings, _ = product_client
    caplog.set_level(logging.INFO, logger="apps.harness.routes")
    path = PREFIX + "/ui-pairings"
    for _ in range(32):
        assert client.post(path, headers=bearer(settings), json={}).status_code == 200
    refused = client.post(path, headers=bearer(settings), json={})
    assert refused.status_code == 429
    assert refused.json() == {"detail": {"code": "pairing_capacity"}}
    assert "route=/api/v1/harness/ui-pairings status=429" in caplog.text


def test_ui_pairing_without_browser_sessions_is_a_finite_503(product_client, caplog):
    """Without the browser session store the pairing mint is 503 harness_unavailable, still guarded and audited."""
    client, _, settings, _ = product_client
    del client.app.state.browser_sessions
    caplog.set_level(logging.INFO, logger="apps.harness.routes")
    path = PREFIX + "/ui-pairings"
    assert client.post(path, json={}).status_code == 401
    refused = client.post(path, headers=bearer(settings), json={})
    assert refused.status_code == 503
    assert refused.json() == {"detail": {"code": "harness_unavailable"}}
    assert "route=/api/v1/harness/ui-pairings status=401" in caplog.text
    assert "route=/api/v1/harness/ui-pairings status=503" in caplog.text
    assert settings["tokens"][0] not in caplog.text


def body_request(receive, content_type=b"application/json"):
    """Build a browser POST request whose body arrives through the given ASGI receive."""
    from starlette.requests import Request

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/ui/pairings",
        "headers": [(b"content-type", content_type)],
        "query_string": b"",
    }
    return Request(scope, receive)


async def stalled():
    """Never deliver a body chunk."""
    await asyncio.Event().wait()


@pytest.mark.asyncio
async def test_bounded_json_body_timeout_is_a_finite_408(monkeypatch):
    """A body that stalls past the deadline becomes 408 request_timeout, not an escaped TimeoutError."""
    from fastapi import HTTPException

    from apps.harness import browser

    monkeypatch.setattr(browser, "BODY_SECONDS", 0.05)
    with pytest.raises(HTTPException) as raised:
        await browser.bounded_json(body_request(stalled))
    assert (raised.value.status_code, raised.value.detail) == (
        408,
        {"code": "request_timeout"},
    )


@pytest.mark.asyncio
async def test_bounded_json_cancellation_is_not_a_timeout(monkeypatch):
    """Cancelling the reader propagates CancelledError instead of turning into a 408."""
    from apps.harness import browser

    monkeypatch.setattr(browser, "BODY_SECONDS", 30)
    task = asyncio.create_task(browser.bounded_json(body_request(stalled)))
    await asyncio.sleep(0.01)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


@pytest.mark.asyncio
async def test_bounded_json_size_boundary():
    """Accept an object of exactly the limit and refuse one byte more with 413."""
    from fastapi import HTTPException

    from apps.harness.browser import bounded_json

    def once(data):
        """Deliver data as one complete body."""

        async def receive():
            """Return the whole body."""
            return {"type": "http.request", "body": data, "more_body": False}

        return receive

    exact = b'{"code":"' + b"x" * 1013 + b'"}'
    assert len(exact) == 1024
    assert await bounded_json(body_request(once(exact)), 1024) == {"code": "x" * 1013}
    with pytest.raises(HTTPException) as raised:
        await bounded_json(body_request(once(exact + b" ")), 1024)
    assert raised.value.status_code == 413


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["/ui/pairings", "/v1/chat/completions"])
async def test_stalled_browser_body_returns_408_and_releases_nothing(
    auth_settings, tmp_path, caplog, monkeypatch, path
):
    """Through the real middleware and handler, a stalled body gets 408 request_timeout and no model work."""
    import httpx

    from apps.harness import browser

    inference = FixtureInference()
    app = compose(FastAPI(), inference=inference, asset_root=fixture_assets(tmp_path))
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app, client=("127.0.0.1", 49001))
        async with httpx.AsyncClient(
            transport=transport, base_url="http://127.0.0.1:7090"
        ) as client:
            response = await client.post(
                PREFIX + "/ui-pairings", headers=bearer(auth_settings), json={}
            )
            code = response.json()["code"]
            response = await client.post(
                "/ui/pairings", headers=UI_HEADERS, json={"code": code}
            )
            cookie = response.headers["set-cookie"].split(";", 1)[0]
        monkeypatch.setattr(browser, "BODY_SECONDS", 0.05)
        scope = {
            "type": "http",
            "asgi": {"version": "3.0", "spec_version": "2.3"},
            "http_version": "1.1",
            "method": "POST",
            "scheme": "http",
            "path": path,
            "raw_path": path.encode(),
            "query_string": b"",
            "root_path": "",
            "headers": [
                (b"host", b"127.0.0.1:7090"),
                (b"origin", b"http://127.0.0.1:7090"),
                (b"x-harness-ui", b"1"),
                (b"content-type", b"application/json"),
                (b"cookie", cookie.encode()),
            ],
            "client": ("127.0.0.1", 49001),
            "server": ("127.0.0.1", 7090),
        }
        messages = []

        async def send(message):
            """Collect response messages."""
            messages.append(message)

        with caplog.at_level(logging.INFO):
            await asyncio.wait_for(app(scope, stalled, send), 5)
        assert messages[0]["status"] == 408
        body = json.loads(b"".join(m.get("body", b"") for m in messages[1:]))
        assert body["error"]["code"] == "request_timeout"
        assert "harness_browser_body_timeout" in caplog.text
        assert "status=408" in caplog.text
        assert inference.calls == []
        assert not app.state.product_harness.admission.locked()


class TruncatedStreamInference(FixtureInference):
    """Send one real chunk, then end the way stream() does when finish_reason is not stop."""

    async def stream(self, messages, **options):
        """Yield a delta, then raise the incomplete-completion error."""
        from apps.harness.inference import IncompleteCompletion

        self.calls.append((messages, options))
        yield b'data: {"choices":[{"delta":{"content":"partial"}}]}\n\n'
        raise IncompleteCompletion("INCOMPLETE")


def test_browser_truncated_stream_reports_incomplete_completion(
    auth_settings, tmp_path, caplog
):
    """A truncated answer ends with the closed incomplete_completion SSE error and no [DONE], not as a normal answer."""
    inference = TruncatedStreamInference()
    app = compose(FastAPI(), inference=inference, asset_root=fixture_assets(tmp_path))
    with TestClient(
        app, base_url="http://127.0.0.1:7090", client=("127.0.0.1", 49001)
    ) as client:
        pair(client, auth_settings)
        with caplog.at_level(logging.INFO):
            response = client.post(
                "/v1/chat/completions",
                headers=UI_HEADERS,
                json={"messages": [{"role": "user", "content": "Hi"}], "stream": True},
            )
        assert response.status_code == 200
        events = sse_data(response.text)
        assert json.loads(events[0])["choices"][0]["delta"]["content"] == "partial"
        assert json.loads(events[1])["error"]["code"] == "incomplete_completion"
        assert len(events) == 2 and "[DONE]" not in response.text
        assert "inference_unavailable" not in response.text
        assert "harness_ui_stream_incomplete" in caplog.text
        assert not app.state.product_harness.admission.locked()


def native_inference(finish):
    """Build the real ProductInference over a native SSE double that ends with the given finish_reason."""
    import httpx

    from apps.api.core.model_config import get_model_profile
    from apps.harness.inference import ProductInference

    model = get_model_profile("core")["model_id"]
    chunks = [
        {"choices": [{"index": 0, "delta": {"content": "native"}}]},
        {"choices": [{"index": 0, "delta": {}, "finish_reason": finish}]},
    ]
    body = "".join("data: " + json.dumps(chunk) + "\n\n" for chunk in chunks)
    body += "data: [DONE]\n\n"

    def respond(request):
        """Serve preparation calls and one native SSE completion."""
        path = request.url.path
        if path == "/v1/models":
            return httpx.Response(200, json={"data": [{"id": model}]})
        if path == "/apply-template":
            return httpx.Response(200, json={"prompt": "templated"})
        if path == "/tokenize":
            return httpx.Response(200, json={"tokens": [1, 2, 3]})
        if path == "/v1/chat/completions":
            return httpx.Response(
                200, text=body, headers={"content-type": "text/event-stream"}
            )
        raise AssertionError(path)

    return ProductInference(transport=httpx.MockTransport(respond))


@pytest.mark.parametrize(
    ("finish", "complete"), [("stop", True), ("length", False), (None, False)]
)
def test_browser_stream_verifies_the_native_finish_reason(
    auth_settings, tmp_path, finish, complete
):
    """Through the real ProductInference, only a stop-finished answer reaches DONE; any other ending gets the error event and no DONE."""
    inference = native_inference(finish)
    app = compose(FastAPI(), inference=inference, asset_root=fixture_assets(tmp_path))
    with TestClient(
        app, base_url="http://127.0.0.1:7090", client=("127.0.0.1", 49001)
    ) as client:
        pair(client, auth_settings)
        response = client.post(
            "/v1/chat/completions",
            headers=UI_HEADERS,
            json={"messages": [{"role": "user", "content": "Hi"}], "stream": True},
        )
        assert response.status_code == 200
        assert "native" in response.text
        events = sse_data(response.text)
        assert (events[-1] == "[DONE]") is complete
        assert ("[DONE]" in events) is complete
        assert ('"incomplete_completion"' in events[-1]) is not complete
        assert "inference_unavailable" not in response.text
        assert not app.state.product_harness.admission.locked()


def test_browser_stream_resume_is_refused(product_client):
    """The UI's resume request after a stream without [DONE] gets 403, so the UI reports an error instead of waiting."""
    client, inference, settings, _ = product_client
    pair(client, settings)
    for query in (
        {"conv_id": "conv-1::model", "from": "42"},
        {"conv_id": "conv-1", "from": "0"},
    ):
        resume = client.get("/v1/stream", params=query, headers={"X-Harness-UI": "1"})
        assert resume.status_code == 403
        assert resume.json() == {"detail": {"code": "unsupported_query"}}
    assert inference.calls == []


PINNED_STREAM_READER = r"""
const fs = require('fs');
const vm = require('vm');
const input = JSON.parse(fs.readFileSync(0, 'utf8'));
const source = fs.readFileSync(input.bundle, 'utf8');
function slice(start, end) {
  const from = source.indexOf(start);
  if (from < 0 || source.indexOf(start, from + 1) >= 0) throw new Error('marker ' + start);
  const to = source.indexOf(end, from);
  if (to < 0) throw new Error('marker ' + end);
  return source.slice(from, to);
}
const context = vm.createContext({
  TextDecoder, TextEncoder, DOMException,
  console: {log() {}, warn() {}, error() {}},
});
vm.runInContext('var ' + slice('iAt=3e3,Ite="::"', ',sAt={') + ';', context);
vm.runInContext('var ' + slice('Ore="AbortError",xGt=', ';function AGt(') + ';', context);
vm.runInContext(slice('function Xu(t){', 'function kG('), context);
vm.runInContext('var Q_;' + slice('Q_=(t=>(t.LOST=', ',hte=(t=>') + ';', context);
const method = slice('static async handleStreamResponse(', 'static async lookupStreamSessions(');
vm.runInContext(method.replace('static async handleStreamResponse(', 'async function handleStreamResponse('), context);
async function read(body) {
  const out = {chunks: '', complete: null, error: null, resumed: []};
  context.Un = {
    saveStreamState() {}, saveStreamStateThrottled() {}, notifyTimings() {},
    extractModelName() { return null; }, mergeToolCallDeltas(calls) { return calls; },
    clearStreamState() {}, flushStreamState() {},
    async resumeStream(id) { out.resumed.push(id); return {status: input.resume_status, body: null}; },
  };
  const parts = body.split(/(?<=\n\n)/).map((part) => new TextEncoder().encode(part));
  const response = {body: {getReader() {
    return {
      async read() { return parts.length ? {done: false, value: parts.shift()} : {done: true, value: undefined}; },
      releaseLock() {}, async cancel() {},
    };
  }}};
  await context.handleStreamResponse(
    response, (chunk) => { out.chunks += chunk; }, (content) => { out.complete = content; },
    (error) => { out.error = error.message; }, undefined, undefined, undefined, undefined,
    undefined, 'conv-1', undefined, () => {}, 'model');
  return out;
}
(async () => {
  const results = {};
  for (const [name, body] of Object.entries(input.bodies)) results[name] = await read(body);
  process.stdout.write(JSON.stringify(results));
})().catch((error) => { console.error(String(error)); process.exitCode = 1; });
"""


def pinned_ui_bundle():
    """Return the receipt-verified pinned UI bundle, or skip when the local download is absent.

    AEVRA_PINNED_UI_ASSETS may point at a downloaded b11557 tree outside this checkout.
    """
    from apps.harness.assets import ASSETS

    root = Path(os.environ.get("AEVRA_PINNED_UI_ASSETS") or ASSETS)
    if not (root / "receipt.json").is_file():
        pytest.skip("the pinned llama-ui assets are not downloaded")
    receipt = json.loads((root / "receipt.json").read_text())
    assert (receipt["version"], receipt["source_pin"]) == (VERSION, PIN)
    names = [
        name
        for name in receipt["files"]
        if re.fullmatch(r"_app/immutable/bundle\.[A-Za-z0-9_-]+\.js", name)
    ]
    assert len(names) == 1
    bundle = root / names[0]
    digest = hashlib.sha256(bundle.read_bytes()).hexdigest()
    assert digest == receipt["files"][names[0]]
    return bundle


def test_pinned_ui_shows_a_failed_stream_as_an_error(auth_settings, tmp_path):
    """The pinned llama-ui stream reader completes only a verified answer; a failed stream reaches its error callback."""
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required for browser-script validation")
    bundle = pinned_ui_bundle()
    bodies = {}
    for name, inference in (
        ("complete", FixtureInference()),
        ("native_stop", native_inference("stop")),
        ("native_length", native_inference("length")),
        ("truncated", TruncatedStreamInference()),
        ("failed", FailingStreamInference()),
    ):
        (tmp_path / name).mkdir()
        app = compose(
            FastAPI(), inference=inference, asset_root=fixture_assets(tmp_path / name)
        )
        with TestClient(
            app, base_url="http://127.0.0.1:7090", client=("127.0.0.1", 49001)
        ) as client:
            pair(client, auth_settings)
            response = client.post(
                "/v1/chat/completions",
                headers=UI_HEADERS,
                json={"messages": [{"role": "user", "content": "Hi"}], "stream": True},
            )
            assert response.status_code == 200
            bodies[name] = response.text
            resume = client.get(
                "/v1/stream",
                params={"conv_id": "conv-1::model", "from": "1"},
                headers={"X-Harness-UI": "1"},
            )
            assert resume.status_code == 403
    # The body this branch first sent: the error event followed by [DONE].
    bodies["error_then_done"] = bodies["truncated"] + "data: [DONE]\n\n"
    result = subprocess.run(
        [node, "-e", PINNED_STREAM_READER],
        input=json.dumps(
            {"bundle": str(bundle), "bodies": bodies, "resume_status": 403}
        ).encode(),
        capture_output=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, result.stderr.decode()
    seen = json.loads(result.stdout)
    assert seen["complete"] == {
        "chunks": "fixture",
        "complete": "fixture",
        "error": None,
        "resumed": [],
    }
    assert seen["native_stop"] == {
        "chunks": "native",
        "complete": "native",
        "error": None,
        "resumed": [],
    }
    for name, chunks in (
        ("native_length", "native"),
        ("truncated", "partial"),
        ("failed", "partial"),
    ):
        assert seen[name]["chunks"] == chunks
        assert seen[name]["complete"] is None
        assert seen[name]["error"] == "Stream connection lost and could not be resumed"
        assert seen[name]["resumed"] == ["conv-1"]
    # The pinned UI ignores SSE error events: with [DONE] the partial answer completes.
    assert seen["error_then_done"]["complete"] == "partial"
    assert seen["error_then_done"]["error"] is None
