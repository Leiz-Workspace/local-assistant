"""Exercise scoped skills, real workspace evidence, cancellation and the optional browser/API boundary."""

import asyncio
import hashlib
import json
import logging
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


@pytest.fixture
def product_client(auth_settings, tmp_path):
    """Create a direct-loopback fixture app with isolated assets and process-local product state."""
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
    assert client.get("/").status_code == 401
    code = pair(client, settings)
    response = client.get("/")
    assert response.status_code == 200 and "harness-bridge.js" in response.text
    assert settings["tokens"][0] not in response.text
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
    assert client.get("/").status_code == 404
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
