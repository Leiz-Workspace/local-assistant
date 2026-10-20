"""Verify actual private TCP/CLI two-approval coding composition with controlled inference, strict HTTP scope and retained lost-response receipts."""

import hashlib
import json
from uuid import UUID, uuid4

import httpx
import pytest
from test_check_http import approve_cli, approve_http
from test_check_http import check_client as check_client
from test_checkpoint_http import checkpoint_client as checkpoint_client
from test_coding_workflow_service import ControlledCore, sample_case
from test_patch_http import patch_client as patch_client
from test_reranker_tcp_trial import localhost_server
from test_workspace_http import workspace_client as workspace_client


@pytest.fixture
def workflow_client(request, monkeypatch):
    """Enable only disposable explicit workflow dependencies and assert controller drain precedes actual native authority shutdown."""
    monkeypatch.setenv("ASSISTANT_CODING_WORKFLOW_ENABLED", "1")
    value = request.getfixturevalue("check_client")
    service = value[0].app.state.coding_workflow_service
    core = ControlledCore()
    service.inference = core
    original = service.shutdown

    async def observed_shutdown():
        """Observe actual completed controller cleanup while all component authorities are still available for their subsequent drain."""
        await original()
        assert not service.operations and not service.admission.locked()
        assert (
            not service.checks.closing
            and not service.patches.closing
            and not service.approvals.closing
            and not service.workspace.closing
        )

    monkeypatch.setattr(service, "shutdown", observed_shutdown)
    yield (*value, core)


def base(spec):
    """Build only the fixed authenticated owner/workspace workflow collection URL."""
    return "/api/v1/workspaces/" + spec["workspace_id"] + "/coding-workflows"


def proposal_body(root):
    """Materialize only frozen disposable sample sources and explicit target/test hashes without selecting commands or model routing."""
    case = sample_case()
    for row in [case["target"], *case["tests"]]:
        path = root / row["path"]
        path.write_text(row["source"])
        path.chmod(0o644)
    return dict(
        issue=case["issue"],
        target=dict(
            path=case["target"]["path"], expected_sha256=case["target"]["sha256"]
        ),
        tests=[
            dict(path=row["path"], expected_sha256=row["sha256"])
            for row in case["tests"]
        ],
        profile="python_unittest",
    )


def test_actual_tcp_controlled_core_two_cli_reviews_and_snapshot_summary(
    workflow_client, caplog
):
    """Exercise real HTTP/CLI/native checkpoints and tests while disclosing that proposal inference is controlled, not a live quality measurement."""
    client, auth, specs, roots, _, _, core = workflow_client
    headers = auth["headers"][0]
    body = proposal_body(roots[0])
    shown = []
    with (
        localhost_server(client) as origin,
        httpx.Client(base_url=origin, trust_env=False, timeout=20) as http,
    ):
        response = http.post(base(specs[0]), headers=headers, json=body)
        assert response.status_code == 200, response.text
        value = response.json()
        target = base(specs[0]) + "/" + value["workflow_id"]
        patch = value["patch"]
        assert value["state"] == "awaiting_patch_review" and patch["diff"]
        assert (roots[0] / "sample.py").read_text() == core.case["target"]["source"]
        assert (
            http.post(
                target + "/apply",
                headers=headers,
                json=dict(approval_id=patch["approval_id"]),
            ).status_code
            == 409
        )
        approve_cli(origin, UUID(patch["approval_id"]), headers, shown)
        result = http.post(
            target + "/apply",
            headers=headers,
            json=dict(approval_id=patch["approval_id"]),
        )
        assert (
            result.status_code == 200
            and result.json()["summary"]["edit_applied"] is True
        )
        assert result.json()["check"] is None
        value = http.post(target + "/checks", headers=headers, json={}).json()
        assert value["check"]["observation"] is None
        request = value["check"]["approval_id"]
        assert request != patch["approval_id"]
        assert (
            http.post(
                target + "/run-checks",
                headers=headers,
                json=dict(approval_id=patch["approval_id"]),
            ).status_code
            == 409
        )
        approve_cli(origin, UUID(request), headers, shown)
        result = http.post(
            target + "/run-checks", headers=headers, json=dict(approval_id=request)
        )
        assert result.status_code == 200, result.text
        value = result.json()
        assert (
            value["state"] == "completed" and value["summary"]["native_exit_code"] == 0
        )
        assert (
            not value["summary"]["quality_evaluated"]
            and not value["summary"]["current_source_observed"]
        )
        assert result.headers["cache-control"] == "private, no-store"
        assert (
            http.post(
                target + "/run-checks", headers=headers, json=dict(approval_id=request)
            ).status_code
            == 409
        )
        assert len(http.get(base(specs[0]), headers=headers).json()["workflows"]) == 1
        assert http.get(target, headers=headers).json()["summary"] == value["summary"]
        assert str(roots[0]) not in result.text
    assert (
        hashlib.sha256((roots[0] / "sample.py").read_bytes()).hexdigest()
        == core.case["expected_fixed_source_sha256"]
    )
    assert (roots[0] / "test_sample.py").read_text() == core.case["tests"][0]["source"]
    assert len(core.calls) == 1 and len(shown) >= 4
    assert headers["Authorization"].split(" ", 1)[1] not in caplog.text


def test_auth_origin_and_foreign_workflow_fail_before_generation(workflow_client):
    """Authenticate/authorize before model/source work and make foreign records indistinguishable from absent ones."""
    client, auth, specs, roots, _, _, core = workflow_client
    headers = auth["headers"][0]
    body = proposal_body(roots[0])
    assert client.post(base(specs[0]), json=body).status_code == 401
    assert (
        client.post(
            base(specs[0]),
            headers=headers | {"Origin": "http://example.invalid"},
            json=body,
        ).status_code
        == 403
    )
    assert client.post(base(specs[1]), headers=headers, json=body).status_code == 404
    assert not core.calls
    value = client.post(base(specs[0]), headers=headers, json=body).json()
    target = base(specs[0]) + "/" + value["workflow_id"]
    foreign = client.get(target, headers=auth["headers"][1])
    unknown = client.get(base(specs[0]) + "/" + str(uuid4()), headers=headers)
    assert (
        foreign.status_code == unknown.status_code == 404
        and foreign.json() == unknown.json()
    )
    assert len(core.calls) == 1


@pytest.mark.parametrize(
    "field", ["command", "owner_id", "model", "max_tokens", "environment"]
)
def test_client_cannot_widen_workflow_scope_commands_or_model_routing(
    workflow_client, field
):
    """Reject extra action/model/budget inputs before allocating an inference attempt or pending approval."""
    client, auth, specs, roots, _, _, core = workflow_client
    body = proposal_body(roots[0]) | {field: "untrusted"}
    assert (
        client.post(base(specs[0]), headers=auth["headers"][0], json=body).status_code
        == 422
    )
    assert not core.calls and not client.app.state.coding_workflow_service.records


def test_default_off_workflow_route_is_inert(check_client):
    """Keep controller generation/actions unavailable even with accepted native dependencies when the new flag remains off."""
    client, auth, specs, roots, _, _ = check_client
    assert (
        client.post(
            base(specs[0]), headers=auth["headers"][0], json=proposal_body(roots[0])
        ).status_code
        == 503
    )
    assert client.app.state.coding_workflow_service is None


@pytest.mark.asyncio
async def test_lost_asgi_apply_response_preserves_committed_component_receipt(
    workflow_client,
):
    """Fail actual transmission after a workflow edit and recover the known receipt without silently proposing/running checks or retrying."""
    client, auth, specs, roots, _, _, core = workflow_client
    headers = auth["headers"][0]
    value = client.post(
        base(specs[0]), headers=headers, json=proposal_body(roots[0])
    ).json()
    request = value["patch"]["approval_id"]
    approve_http(client, headers, request)
    target = base(specs[0]) + "/" + value["workflow_id"]
    sent = []

    async def receive():
        """Deliver only the exact already-approved patch reference without any replacement command/content override."""
        return dict(
            type="http.request",
            body=json.dumps(dict(approval_id=request)).encode(),
            more_body=False,
        )

    async def send(event):
        """Lose the delivery acknowledgement after native commit and workflow receipt publication."""
        sent.append(event["type"])
        raise OSError("CONTROLLED-WORKFLOW-SEND")

    scope = dict(
        type="http",
        asgi=dict(version="3.0"),
        http_version="1.1",
        method="POST",
        scheme="http",
        path=target + "/apply",
        raw_path=(target + "/apply").encode(),
        query_string=b"",
        root_path="",
        headers=[
            (b"authorization", headers["Authorization"].encode()),
            (b"content-type", b"application/json"),
        ],
        client=("127.0.0.1", 43000),
        server=("127.0.0.1", 80),
    )
    with pytest.raises(OSError, match="CONTROLLED-WORKFLOW-SEND"):
        await client.app(scope, receive, send)
    result = client.get(target, headers=headers).json()
    assert (
        sent and result["summary"]["edit_applied"] is True and result["check"] is None
    )
    assert (
        hashlib.sha256((roots[0] / "sample.py").read_bytes()).hexdigest()
        == core.case["expected_fixed_source_sha256"]
    )
    assert (
        client.post(
            target + "/apply", headers=headers, json=dict(approval_id=request)
        ).status_code
        == 409
    )


@pytest.mark.parametrize(
    "raw",
    [
        b'{"issue":NaN}',
        b'{"issue":"first","issue":"second"}',
        b'{"issue":"\\ud800"}',
        b"x" * 16385,
    ],
)
def test_strict_bounded_json_rejects_ambiguity_before_generation(workflow_client, raw):
    """Reject duplicate/nonfinite/surrogate/oversized request bytes before retaining source or generating a model proposal."""
    client, auth, specs, _, _, _, core = workflow_client
    response = client.post(base(specs[0]), headers=auth["headers"][0], content=raw)
    assert response.status_code in {413, 422}
    assert not core.calls and not client.app.state.coding_workflow_service.records
