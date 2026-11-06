"""Verify real local owner-authenticated proposal/explicit review/apply and denial routes on disposable source files only."""

import hashlib
import json
from uuid import UUID, uuid4

import httpx
import pytest
from test_approval_http import decision_body
from test_reranker_tcp_trial import localhost_server
from test_workspace_http import workspace_client as workspace_client

from scripts.review_approval import review_approval


@pytest.fixture
def patch_client(request, monkeypatch):
    """Enable patch and approval only for the accepted synthetic two-owner temporary workspace fixture."""
    monkeypatch.setenv("ASSISTANT_APPROVAL_ENABLED", "1")
    monkeypatch.setenv("ASSISTANT_PATCH_ENABLED", "1")
    value = request.getfixturevalue("workspace_client")
    for root in value[3]:
        root.chmod(0o700)
        (root / "main.py").chmod(0o644)
    yield value


def proposal_body(source):
    """Return a concrete one-file replacement whose digest binds the fixture's original raw bytes."""
    return dict(
        path="main.py",
        expected_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        replacement='"""Reviewed synthetic replacement."""\nVALUE = "Birch"\n',
    )


def base(spec):
    """Build the fixed local scoped patch collection URL from the server-configured fixture identity."""
    return "/api/v1/workspaces/" + spec["workspace_id"] + "/patches"


def test_actual_tcp_cli_review_then_atomic_apply_and_readonly_reflects_replacement(
    patch_client, caplog
):
    """Perform real TCP proposal, explicit typed CLI approval, one-shot native edit and fresh readonly source query."""
    client, auth, specs, roots = patch_client
    headers = auth["headers"][0]
    body = proposal_body(roots[0] / "main.py")
    original = (roots[0] / "main.py").read_bytes()
    with (
        localhost_server(client) as origin,
        httpx.Client(base_url=origin, trust_env=False) as http,
    ):
        response = http.post(base(specs[0]), headers=headers, json=body)
        assert response.status_code == 200, response.text
        proposal = response.json()
        target = base(specs[0]) + "/" + proposal["proposal_id"]
        assert response.headers["cache-control"] == "private, no-store"
        assert (roots[0] / "main.py").read_bytes() == original
        approval = UUID(proposal["approval_id"])
        assert (
            http.post(
                target + "/apply", headers=headers, json=dict(approval_id=str(approval))
            ).status_code
            == 409
        )
        shown = []
        token = headers["Authorization"].split(" ", 1)[1]
        assert (
            review_approval(
                origin + "/api/v1",
                approval,
                token,
                read_line=lambda prompt: "APPROVE " + str(approval),
                write=shown.append,
            )
            == 0
        )
        assert (roots[0] / "main.py").read_bytes() == original
        result = http.post(
            target + "/apply", headers=headers, json=dict(approval_id=str(approval))
        )
        assert result.status_code == 200, result.text
        assert result.json()["receipt"]["applied"] is True
        assert (roots[0] / "main.py").read_bytes() == body["replacement"].encode()
        assert (
            http.get(target, headers=headers).json()["receipt"]
            == result.json()["receipt"]
        )
        assert (
            http.post(
                target + "/apply", headers=headers, json=dict(approval_id=str(approval))
            ).status_code
            == 409
        )
        read = http.post(
            base(specs[0]).removesuffix("/patches") + "/read",
            headers=headers,
            json=dict(path="main.py", start_line=1, end_line=2),
        )
        assert (
            read.status_code == 200
            and read.json()["lines"][0]["source_sha256"] == result.json()["new_sha256"]
        )
    assert "Birch" not in caplog.text and token not in caplog.text
    assert not list(roots[0].glob(".assistant-patch-*"))


@pytest.mark.parametrize(
    "fault",
    [
        "auth",
        "origin",
        "foreign",
        "unknown",
        "workspace",
        "approval",
        "replacement",
        "path",
        "owner",
        "mode",
        "command",
        "digest",
        "traversal",
        "hidden",
    ],
)
def test_authority_scope_and_input_denials_leave_bytes_unchanged(patch_client, fault):
    """Reject all untrusted scope/input/approval overrides without changing source or writing temporary entries."""
    client, auth, specs, roots = patch_client
    headers = dict(auth["headers"][0])
    body = proposal_body(roots[0] / "main.py")
    original = (roots[0] / "main.py").read_bytes()
    response = client.post(base(specs[0]), headers=headers, json=body)
    assert response.status_code == 200
    proposal = response.json()
    approval = proposal["approval_id"]
    review = client.get("/api/v1/approvals/" + approval, headers=headers).json()
    assert (
        client.post(
            "/api/v1/approvals/" + approval + "/decision",
            headers=headers,
            json=decision_body(review),
        ).status_code
        == 200
    )
    target = base(specs[0]) + "/" + proposal["proposal_id"] + "/apply"
    payload = dict(approval_id=approval)
    if fault == "auth":
        headers = {}
    elif fault == "origin":
        headers["Origin"] = "https://untrusted.invalid"
    elif fault == "foreign":
        headers = auth["headers"][1]
    elif fault == "unknown":
        target = base(specs[0]) + "/" + str(uuid4()) + "/apply"
    elif fault == "workspace":
        target = base(specs[1]) + "/" + proposal["proposal_id"] + "/apply"
    elif fault == "approval":
        payload["approval_id"] = str(uuid4())
    elif fault in {"digest", "traversal", "hidden"}:
        target = base(specs[0])
        payload = dict(body)
        payload[
            {"digest": "expected_sha256", "traversal": "path", "hidden": "path"}[fault]
        ] = {"digest": "0" * 64, "traversal": "../outside", "hidden": ".env"}[fault]
    else:
        payload[fault] = "untrusted"
    result = client.post(target, headers=headers, json=payload)
    assert result.status_code in {401, 403, 404, 409, 422}, result.text
    assert (roots[0] / "main.py").read_bytes() == original
    assert not list(roots[0].glob(".assistant-patch-*"))


def test_changed_source_and_foreign_status_are_private(patch_client):
    """Treat foreign and absent status uniformly and reject an actually changed source after explicit review."""
    client, auth, specs, roots = patch_client
    proposal = client.post(
        base(specs[0]),
        headers=auth["headers"][0],
        json=proposal_body(roots[0] / "main.py"),
    ).json()
    target = base(specs[0]) + "/" + proposal["proposal_id"]
    foreign = client.get(target, headers=auth["headers"][1])
    unknown = client.get(
        base(specs[0]) + "/" + str(uuid4()), headers=auth["headers"][0]
    )
    assert (
        foreign.status_code == unknown.status_code == 404
        and foreign.json() == unknown.json()
    )
    identifier = proposal["approval_id"]
    review = client.get(
        "/api/v1/approvals/" + identifier, headers=auth["headers"][0]
    ).json()
    assert (
        client.post(
            "/api/v1/approvals/" + identifier + "/decision",
            headers=auth["headers"][0],
            json=decision_body(review),
        ).status_code
        == 200
    )
    (roots[0] / "main.py").write_text("independent changed source\n")
    response = client.post(
        target + "/apply", headers=auth["headers"][0], json=dict(approval_id=identifier)
    )
    assert (
        response.status_code == 409
        and (roots[0] / "main.py").read_text() == "independent changed source\n"
    )
    assert client.get(target, headers=auth["headers"][0]).json()["state"] == "failed"
    assert str(roots[0]) not in response.text


@pytest.mark.parametrize(
    "raw",
    [
        b'{"path":NaN}',
        b'{"path":"x","path":"y"}',
        b'{"replacement":"\\ud800"}',
        b"x" * 16385,
    ],
)
def test_strict_bounded_patch_body_never_creates_approval(patch_client, raw):
    """Reject oversized/duplicate/nonfinite/surrogate JSON through the accepted strict stream layer before native access."""
    client, auth, specs, _ = patch_client
    response = client.post(base(specs[0]), headers=auth["headers"][0], content=raw)
    assert response.status_code in {413, 422}
    assert (
        not client.app.state.patch_service.records
        and not client.app.state.approval_store._records
    )


def test_default_off_patch_route_is_inert(workspace_client):
    """Keep edit/proposal unavailable without explicit enablement even when accepted readonly workspaces are live."""
    client, auth, specs, roots = workspace_client
    assert (
        client.post(
            base(specs[0]),
            headers=auth["headers"][0],
            json=proposal_body(roots[0] / "main.py"),
        ).status_code
        == 503
    )


@pytest.mark.asyncio
async def test_lost_asgi_response_ack_keeps_applied_owner_receipt(patch_client):
    """Fail actual response transmission after commit and query the authoritative receipt instead of retrying or reverting source."""
    client, auth, specs, roots = patch_client
    headers = auth["headers"][0]
    proposal = client.post(
        base(specs[0]), headers=headers, json=proposal_body(roots[0] / "main.py")
    ).json()
    target = base(specs[0]) + "/" + proposal["proposal_id"]
    approval = proposal["approval_id"]
    review = client.get("/api/v1/approvals/" + approval, headers=headers).json()
    assert (
        client.post(
            "/api/v1/approvals/" + approval + "/decision",
            headers=headers,
            json=decision_body(review),
        ).status_code
        == 200
    )
    sent = []

    async def receive():
        """Deliver exactly the fixed linked-approval request body without client-controlled scope overrides."""
        return dict(
            type="http.request",
            body=json.dumps(dict(approval_id=approval)).encode(),
            more_body=False,
        )

    async def send(event):
        """Lose the actual response acknowledgement after route work has completed."""
        sent.append(event["type"])
        raise OSError("CONTROLLED-PRIVATE-SEND")

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
    with pytest.raises(OSError):
        await client.app(scope, receive, send)
    assert sent and (roots[0] / "main.py").read_text() == proposal["replacement"]
    status = client.get(target, headers=headers)
    assert status.status_code == 200 and status.json()["receipt"]["applied"] is True
    assert (
        client.post(
            target + "/apply", headers=headers, json=dict(approval_id=approval)
        ).status_code
        == 409
    )
