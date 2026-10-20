"""Verify actual default-off authenticated HTTP/TCP snapshot checks, explicit CLI review and unchanged original source."""

import hashlib
import json
from pathlib import Path
from uuid import UUID, uuid4

import httpx
import pytest
from test_checkpoint_http import checkpoint_client as checkpoint_client
from test_patch_http import decision_body
from test_patch_http import patch_client as patch_client
from test_reranker_tcp_trial import localhost_server
from test_workspace_http import workspace_client as workspace_client

from scripts.review_approval import review_approval


@pytest.fixture
def check_client(request, tmp_path, monkeypatch):
    """Enable checks only for explicit disposable roots and the existing pinned local runtime without database/model credentials."""
    root = tmp_path / "private-check-jobs"
    root.mkdir(mode=0o700)
    sha = "20cf97c5db04ca9c51249dec1a54cbc96c24462df280334ada04b8f3c877b746"
    ruff = next(
        (
            path
            for path in (Path.home() / ".cache/uv/archive-v0").glob("*/bin/ruff")
            if hashlib.sha256(path.read_bytes()).hexdigest() == sha
        ),
        None,
    )
    assert ruff is not None, "Existing pinned Ruff required; no install fallback"
    values = dict(
        ASSISTANT_CHECKS_ENABLED="1",
        ASSISTANT_CHECKS_ROOT=str(root),
        ASSISTANT_CHECKS_PYTHON_PATH="/usr/bin/python3.12",
        ASSISTANT_CHECKS_PYTHON_SHA256=hashlib.sha256(
            Path("/usr/bin/python3.12").read_bytes()
        ).hexdigest(),
        ASSISTANT_CHECKS_STDLIB_ROOT="/usr/lib/python3.12",
        ASSISTANT_CHECKS_RUFF_PATH=str(ruff),
        ASSISTANT_CHECKS_RUFF_SHA256=sha,
    )
    for name, value in values.items():
        monkeypatch.setenv(name, value)
    client = request.getfixturevalue("checkpoint_client")
    service = client[0].app.state.check_service
    shutdown = service.shutdown

    async def observed_shutdown():
        """Assert native/private quiescence only after the actual enclosing application lifespan drains checks."""
        await shutdown()
        assert service.closing and not service.operations
        assert service.store.runtime.fd is None and service.store.storage.fd is None

    monkeypatch.setattr(service, "shutdown", observed_shutdown)
    yield (*client, root)
    assert not service.operations and not service.admission.locked()


def base(spec):
    """Build only the fixed local owner/workspace check collection URL."""
    return "/api/v1/workspaces/" + spec["workspace_id"] + "/checks"


def body(root, profile="python_unittest"):
    """Create one described self-contained selected test fixture and its exact current source hash."""
    raw = b'"""Controlled HTTP native check fixture."""\nimport unittest\nclass Fixture(unittest.TestCase):\n    """Check only a disposable deterministic value."""\n    def test_value(self):\n        """Observe one real assertion inside the isolated runtime."""\n        self.assertEqual(2+2,4)\n'
    (root / "test_checks.py").write_bytes(raw)
    return dict(
        profile=profile,
        files=[
            dict(path="test_checks.py", expected_sha256=hashlib.sha256(raw).hexdigest())
        ],
    )


def approve_cli(origin, request, headers, shown):
    """Approve only the synthetic concrete fixture UUID through actual local TCP using the existing bounded CLI."""

    def typed_decision(prompt):
        """Supply the explicit complete fixture request identity without autoapproving any real project action."""
        return "APPROVE " + str(request)

    token = headers["Authorization"].split(" ", 1)[1]
    assert (
        review_approval(
            origin + "/api/v1",
            request,
            token,
            read_line=typed_decision,
            write=shown.append,
        )
        == 0
    )


def approve_http(client, headers, identifier):
    """Explicitly approve only the exact disposable fixture review using its current scope and nonce."""
    value = client.get("/api/v1/approvals/" + identifier, headers=headers).json()
    assert (
        client.post(
            "/api/v1/approvals/" + identifier + "/decision",
            headers=headers,
            json=decision_body(value),
        ).status_code
        == 200
    )


def test_changed_source_after_review_prevents_consumption_and_execution(check_client):
    """Deny a changed original source after concrete approval while retaining pending historical evidence without running it."""
    client, auth, specs, roots, _, _ = check_client
    headers = auth["headers"][0]
    value = client.post(base(specs[0]), headers=headers, json=body(roots[0])).json()
    approve_http(client, headers, value["approval_id"])
    (roots[0] / "test_checks.py").write_bytes(b'"""Changed source after review."""\n')
    target = base(specs[0]) + "/" + value["job_id"]
    result = client.post(
        target + "/run", headers=headers, json=dict(approval_id=value["approval_id"])
    )
    assert result.status_code == 409
    status = client.get(target, headers=headers).json()
    assert status["observation"] is None and not status["live_proposal"]
    assert (
        client.get("/api/v1/approvals/" + value["approval_id"], headers=headers).json()[
            "state"
        ]
        == "approved"
    )
    assert (
        client.post(
            target + "/run",
            headers=headers,
            json=dict(approval_id=value["approval_id"]),
        ).status_code
        == 409
    )


@pytest.mark.asyncio
async def test_lost_asgi_ack_preserves_consumed_grant_and_actual_native_observation(
    check_client,
):
    """Lose response delivery only after native completion and recover the actual retained result without a second execution."""
    client, auth, specs, roots, _, _ = check_client
    headers = auth["headers"][0]
    value = client.post(base(specs[0]), headers=headers, json=body(roots[0])).json()
    approve_http(client, headers, value["approval_id"])
    target = base(specs[0]) + "/" + value["job_id"]
    sent = []

    async def receive():
        """Deliver only the linked approval UUID without accepting a command or authority override."""
        return dict(
            type="http.request",
            body=json.dumps(dict(approval_id=value["approval_id"])).encode(),
            more_body=False,
        )

    async def send(event):
        """Inject a lost acknowledgement after the route has completed its actual native attempt."""
        sent.append(event["type"])
        raise OSError("CONTROLLED-CHECK-SEND")

    scope = dict(
        type="http",
        asgi=dict(version="3.0"),
        http_version="1.1",
        method="POST",
        scheme="http",
        path=target + "/run",
        raw_path=(target + "/run").encode(),
        query_string=b"",
        root_path="",
        headers=[
            (b"authorization", headers["Authorization"].encode()),
            (b"content-type", b"application/json"),
        ],
        client=("127.0.0.1", 43000),
        server=("127.0.0.1", 80),
    )
    with pytest.raises(OSError, match="CONTROLLED-CHECK-SEND"):
        await client.app(scope, receive, send)
    result = client.get(target, headers=headers).json()
    assert sent and result["state"] == "observed"
    assert (
        result["observation"]["started_acknowledged"]
        and result["observation"]["exit_code"] == 0
    )
    assert (
        not result["observation"]["quality_evaluated"] and not result["live_proposal"]
    )
    assert (
        client.get("/api/v1/approvals/" + value["approval_id"], headers=headers).json()[
            "state"
        ]
        == "consumed"
    )
    assert (
        client.post(
            target + "/run",
            headers=headers,
            json=dict(approval_id=value["approval_id"]),
        ).status_code
        == 409
    )


def test_actual_tcp_cli_review_and_one_shot_native_check_preserve_original_source(
    check_client, caplog
):
    """Perform real snapshot proposal, separate explicit CLI decision, native test execution and owner-only retained observation."""
    client, auth, specs, roots, _, _ = check_client
    headers = auth["headers"][0]
    value = body(roots[0])
    original = (roots[0] / "test_checks.py").read_bytes()
    shown = []
    with (
        localhost_server(client) as origin,
        httpx.Client(base_url=origin, trust_env=False, timeout=20) as http,
    ):
        response = http.post(base(specs[0]), headers=headers, json=value)
        assert response.status_code == 200, response.text
        proposal = response.json()
        target = base(specs[0]) + "/" + proposal["job_id"]
        request = UUID(proposal["approval_id"])
        assert proposal["observation"] is None and proposal["live_proposal"]
        assert (
            http.post(
                target + "/run", headers=headers, json=dict(approval_id=str(request))
            ).status_code
            == 409
        )
        approve_cli(origin, request, headers, shown)
        assert (roots[0] / "test_checks.py").read_bytes() == original
        response = http.post(
            target + "/run", headers=headers, json=dict(approval_id=str(request))
        )
        assert response.status_code == 200, response.text
        result = response.json()
        assert result["state"] == "observed" and result["observation"]["exit_code"] == 0
        assert (
            result["observation"]["started_acknowledged"]
            and not result["observation"]["quality_evaluated"]
        )
        assert not result["live_proposal"] and not result["recovered_approval"]
        assert response.headers["cache-control"] == "private, no-store"
        assert (
            http.get(target, headers=headers).json()["observation"]
            == result["observation"]
        )
        assert (
            http.post(
                target + "/run", headers=headers, json=dict(approval_id=str(request))
            ).status_code
            == 409
        )
        assert len(http.get(base(specs[0]), headers=headers).json()["jobs"]) == 1
        assert (
            str(roots[0]) not in response.text
            and "HIDDEN-WORKSPACE-CANARY" not in response.text
        )
    assert (roots[0] / "test_checks.py").read_bytes() == original
    assert any("run_checks" in line for line in shown)
    assert headers["Authorization"].split(" ", 1)[1] not in caplog.text


def test_auth_origin_foreign_unknown_and_default_private_status_gates(check_client):
    """Authenticate and authorize before original/private source access and mask foreign jobs like unknown identities."""
    client, auth, specs, roots, _, _ = check_client
    headers = auth["headers"][0]
    value = body(roots[0])
    assert client.post(base(specs[0]), json=value).status_code == 401
    assert (
        client.post(
            base(specs[0]),
            headers={**headers, "Origin": "http://example.invalid"},
            json=value,
        ).status_code
        == 403
    )
    assert client.post(base(specs[1]), headers=headers, json=value).status_code == 404
    proposed = client.post(base(specs[0]), headers=headers, json=value).json()
    target = base(specs[0]) + "/" + proposed["job_id"]
    foreign = client.get(target, headers=auth["headers"][1])
    unknown = client.get(base(specs[0]) + "/" + str(uuid4()), headers=headers)
    assert foreign.status_code == unknown.status_code == 404
    assert foreign.json() == unknown.json()
    assert (
        client.post(target + "/cancel", headers=auth["headers"][1], json={}).status_code
        == 404
    )
    assert client.get(target, headers=headers).json()["live_proposal"]


@pytest.mark.parametrize(
    "override",
    [
        {"profile": "shell"},
        {"argv": ["--fix"]},
        {"timeout": 999},
        {"environment": {"TOKEN": "CANARY"}},
        {"root": "/"},
        {"owner_id": "forged"},
        {"files": []},
        {"files": [{"path": "../secret.py", "expected_sha256": "a" * 64}]},
        {"files": [{"path": ".env", "expected_sha256": "a" * 64}]},
        {"files": [{"path": "test_checks.py", "expected_sha256": True}]},
    ],
)
def test_untrusted_body_cannot_widen_commands_resources_paths_or_identity(
    check_client, override
):
    """Reject extra/invalid fields and unsafe source paths without publishing a new job or execution grant."""
    client, auth, specs, roots, _, _ = check_client
    headers = auth["headers"][0]
    value = body(roots[0]) | override
    response = client.post(base(specs[0]), headers=headers, json=value)
    assert response.status_code == 422, response.text
    assert client.get(base(specs[0]), headers=headers).json()["jobs"] == []


def test_pending_cancel_retains_history_and_prevents_old_review_execution(check_client):
    """Close the pending capability without deleting evidence or converting cancellation into a grant consumption."""
    client, auth, specs, roots, _, _ = check_client
    headers = auth["headers"][0]
    proposed = client.post(base(specs[0]), headers=headers, json=body(roots[0])).json()
    target = base(specs[0]) + "/" + proposed["job_id"]
    response = client.post(target + "/cancel", headers=headers, json={})
    assert response.status_code == 200 and response.json()["state"] == "cancelled"
    assert (
        response.json()["observation"] is None and not response.json()["live_proposal"]
    )
    assert (
        client.post(
            target + "/run",
            headers=headers,
            json=dict(approval_id=proposed["approval_id"]),
        ).status_code
        == 409
    )
    assert len(client.get(base(specs[0]), headers=headers).json()["jobs"]) == 1


def test_checks_disabled_are_inert_and_require_no_runtime_settings(workspace_client):
    """Keep new endpoints unavailable by default while preserving accepted workspace routes and original files."""
    client, auth, specs, _ = workspace_client
    assert client.get(base(specs[0]), headers=auth["headers"][0]).status_code == 503
