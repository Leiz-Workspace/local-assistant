"""Verify real local TCP/CLI controlled proposal retry, strict owner cancellation and retained lost-response receipts without claiming model quality."""

import asyncio
import hashlib
import json
from uuid import UUID, uuid4

import httpx
import pytest
from test_check_http import approve_cli
from test_check_http import check_client as check_client
from test_checkpoint_http import checkpoint_client as checkpoint_client
from test_coding_workflow_http import base, proposal_body
from test_coding_workflow_http import workflow_client as workflow_client
from test_patch_http import patch_client as patch_client
from test_reranker_tcp_trial import localhost_server
from test_workspace_http import workspace_client as workspace_client


@pytest.fixture
def controls_client(request, monkeypatch):
    """Select controls only inside the disposable application fixture and retain its actual native scopes and disclosed controlled inference."""
    monkeypatch.setenv("ASSISTANT_CODING_WORKFLOW_CONTROLS_ENABLED", "1")
    return request.getfixturevalue("workflow_client")


def test_real_tcp_retry_requires_two_new_cli_reviews_and_retains_original_failure(
    controls_client,
):
    """Run first-invalid/second-valid controlled inference through real HTTP, typed reviews and native checks without action retry or first-attempt replacement."""
    client, auth, specs, roots, _, _, core = controls_client
    headers, body, shown = auth["headers"][0], proposal_body(roots[0]), []
    good, core.raw = core.raw, "first controlled invalid completion"
    with (
        localhost_server(client) as origin,
        httpx.Client(base_url=origin, trust_env=False, timeout=20) as http,
    ):
        first_response = http.post(base(specs[0]), headers=headers, json=body)
        assert first_response.status_code == 200, first_response.text
        first = first_response.json()
        root = base(specs[0]) + "/" + first["workflow_id"]
        assert first["state"] == "proposal_failed"
        core.raw = good
        response = http.post(root + "/retry-proposal", headers=headers, json={})
        assert response.status_code == 200, response.text
        value = response.json()
        target = base(specs[0]) + "/" + value["workflow_id"]
        assert target != root and value["selected_files"] == first["selected_files"]
        assert (
            value["controls"]["proposals_used"] == 2
            and value["controls"]["automatic_retries"] == 0
        )
        patch = value["patch"]["approval_id"]
        assert (
            http.post(
                target + "/apply", headers=headers, json=dict(approval_id=patch)
            ).status_code
            == 409
        )
        approve_cli(origin, UUID(patch), headers, shown)
        assert http.post(
            target + "/apply", headers=headers, json=dict(approval_id=patch)
        ).json()["summary"]["edit_applied"]
        response = http.post(target + "/checks", headers=headers, json={})
        assert response.status_code == 200, response.text
        check = response.json()["check"]["approval_id"]
        assert check != patch
        assert (
            http.post(
                target + "/run-checks", headers=headers, json=dict(approval_id=patch)
            ).status_code
            == 409
        )
        approve_cli(origin, UUID(check), headers, shown)
        response = http.post(
            target + "/run-checks", headers=headers, json=dict(approval_id=check)
        )
        assert response.status_code == 200, response.text
        final = response.json()
        assert (
            final["summary"]["native_exit_code"] == 0
            and final["summary"]["edit_applied"]
        )
        assert (
            not final["summary"]["quality_evaluated"]
            and final["controls"]["lineage_steps_used"] == 5
        )
        assert (
            http.post(root + "/retry-proposal", headers=headers, json={}).status_code
            == 429
        )
        assert (
            http.post(target + "/retry-proposal", headers=headers, json={}).status_code
            == 409
        )
        original = http.get(root, headers=headers).json()
        assert (
            original["model_observation"] == first["model_observation"]
            and original["state"] == "proposal_failed"
        )
        terminal = http.post(target + "/cancel", headers=headers, json={}).json()
        assert (
            terminal["cancel_status"] == "already_terminal"
            and terminal["controls"]["events"] == final["controls"]["events"]
        )
        assert response.headers["cache-control"] == "private, no-store"
    assert len(core.calls) == 2 and len(shown) >= 4
    assert (
        hashlib.sha256((roots[0] / "sample.py").read_bytes()).hexdigest()
        == core.case["expected_fixed_source_sha256"]
    )


@pytest.mark.parametrize("action", ["cancel", "retry-proposal"])
def test_control_owner_auth_origin_and_foreign_denials_have_no_effect(
    controls_client, action
):
    """Mask unknown and foreign targets and reject unauthenticated or nonlocal requests before cancellation intent or another model call."""
    client, auth, specs, roots, _, _, core = controls_client
    headers = auth["headers"][0]
    value = client.post(
        base(specs[0]), headers=headers, json=proposal_body(roots[0])
    ).json()
    path = base(specs[0]) + "/" + value["workflow_id"] + "/" + action
    assert client.post(path, json={}).status_code == 401
    assert (
        client.post(
            path, headers=headers | {"Origin": "http://example.invalid"}, json={}
        ).status_code
        == 403
    )
    foreign = client.post(path, headers=auth["headers"][1], json={})
    unknown = client.post(
        base(specs[0]) + "/" + str(uuid4()) + "/" + action, headers=headers, json={}
    )
    assert (
        foreign.status_code == unknown.status_code == 404
        and foreign.json() == unknown.json()
    )
    service = client.app.state.coding_workflow_service
    assert (
        not service.controls[UUID(value["workflow_id"])].cancel_requested
        and len(core.calls) == 1
    )


@pytest.mark.parametrize("action", ["cancel", "retry-proposal"])
@pytest.mark.parametrize(
    "raw",
    [
        b'{"model":"override"}',
        b'{"approval_id":"old"}',
        b'{"x":NaN}',
        b'{"x":1,"x":2}',
        b'{"x":"\\ud800"}',
        b"x" * 16385,
    ],
)
def test_controls_accept_only_strict_bounded_empty_input(controls_client, action, raw):
    """Reject model/grant overrides, duplicate/nonfinite/surrogate and oversized JSON before touching any workflow control state."""
    client, auth, specs, _, _, _, core = controls_client
    response = client.post(
        base(specs[0]) + "/" + str(uuid4()) + "/" + action,
        headers=auth["headers"][0],
        content=raw,
    )
    assert response.status_code in {413, 422} and not core.calls


@pytest.mark.parametrize("action", ["cancel", "retry-proposal"])
def test_disabled_controls_cannot_change_accepted_base_workflow(
    workflow_client, action
):
    """Keep control actions unavailable while preserving the default accepted pending workflow and its original approval."""
    client, auth, specs, roots, _, _, core = workflow_client
    headers = auth["headers"][0]
    value = client.post(
        base(specs[0]), headers=headers, json=proposal_body(roots[0])
    ).json()
    response = client.post(
        base(specs[0]) + "/" + value["workflow_id"] + "/" + action,
        headers=headers,
        json={},
    )
    assert response.status_code == 503 and len(core.calls) == 1


async def asgi_request(app, path, headers, body, *, lose_response=False):
    """Execute an exact authenticated local request on the current event loop and optionally lose only the response acknowledgement."""
    sent = []

    async def receive():
        """Deliver the complete fixed JSON request without any additional source or authority input."""
        return dict(
            type="http.request", body=json.dumps(body).encode(), more_body=False
        )

    async def send(event):
        """Retain transport metadata or inject a failure after the actual action completed."""
        sent.append(event)
        if lose_response:
            raise OSError("CONTROLLED-CONTROLS-SEND")

    scope = dict(
        type="http",
        asgi=dict(version="3.0"),
        http_version="1.1",
        method="POST",
        scheme="http",
        path=path,
        raw_path=path.encode(),
        query_string=b"",
        root_path="",
        headers=[
            (b"authorization", headers["Authorization"].encode()),
            (b"content-type", b"application/json"),
        ],
        client=("127.0.0.1", 43000),
        server=("127.0.0.1", 80),
    )
    await app(scope, receive, send)
    return sent


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["cancel", "retry-proposal"])
async def test_lost_response_retains_cancel_or_distinct_retry_without_replaying(
    controls_client, action
):
    """Lose the real ASGI response after cancellation or explicit retry and recover bounded history without repeating its effect."""
    client, auth, specs, roots, _, _, core = controls_client
    headers, body = auth["headers"][0], proposal_body(roots[0])
    if action == "retry-proposal":
        core.raw = "invalid controlled completion"
    first = client.post(base(specs[0]), headers=headers, json=body).json()
    path = base(specs[0]) + "/" + first["workflow_id"]
    with pytest.raises(OSError, match="CONTROLLED-CONTROLS-SEND"):
        await asgi_request(
            client.app, path + "/" + action, headers, {}, lose_response=True
        )
    service = client.app.state.coding_workflow_service
    result = await service.read(
        UUID(specs[0]["owner_id"]),
        UUID(specs[0]["workspace_id"]),
        UUID(first["workflow_id"]),
    )
    if action == "cancel":
        assert (
            result["controls"]["cancel_finished"]
            and result["patch"]["state"] == "failed"
            and len(core.calls) == 1
        )
    else:
        assert (
            result["state"] == "proposal_failed"
            and len(service.records) == len(core.calls) == 2
        )
        assert result["model_observation"] == first["model_observation"]
    assert (
        not service.operations
        and not service.cancel_requests
        and not service.cancel_workers
    )


@pytest.mark.asyncio
async def test_active_http_generation_can_be_discovered_and_cancelled_by_exact_owner(
    controls_client,
):
    """Hold the actual model-port await inside an HTTP request and use owned progress to cancel and join only that request."""
    client, auth, specs, roots, _, _, core = controls_client
    headers, body = auth["headers"][0], proposal_body(roots[0])
    core.block = True
    task = asyncio.create_task(asgi_request(client.app, base(specs[0]), headers, body))
    await asyncio.wait_for(core.entered.wait(), 5)
    service = client.app.state.coding_workflow_service
    values = await service.list(
        UUID(specs[0]["owner_id"]), UUID(specs[0]["workspace_id"])
    )
    path = base(specs[0]) + "/" + values[0]["workflow_id"] + "/cancel"
    events = await asgi_request(client.app, path, headers, {})
    with pytest.raises(asyncio.CancelledError):
        await task
    assert (
        next(item for item in events if item["type"] == "http.response.start")["status"]
        == 200
    )
    assert (
        core.exited.is_set() and not service.active_tasks and not service.cancel_workers
    )
