"""Verify real authenticated local approval reviews/decisions and explicit CLI consent on disposable owner-scoped fixtures."""

from uuid import UUID, uuid4

import pytest
from test_approvals import ARTIFACT
from test_reranker_tcp_trial import localhost_server
from test_workspace_http import workspace_client as workspace_client

from scripts.review_approval import review_approval
from src.application.services.approvals import ApprovalError


@pytest.fixture
def approval_client(request, monkeypatch):
    """Enable review only on a disposable configured catalog without production requests, actions, models or database access."""
    monkeypatch.setenv("ASSISTANT_APPROVAL_ENABLED", "1")
    client, auth, specs, roots = request.getfixturevalue("workspace_client")
    store = client.app.state.approval_store
    identifier = store.create(
        auth["principals"][0], UUID(specs[0]["workspace_id"]), "patch", ARTIFACT
    )
    yield client, auth, specs, roots, store, identifier


def url(identifier):
    """Return only the fixed review endpoint for a server-generated fixture request identity."""
    return "/api/v1/approvals/" + str(identifier)


def decision_body(review, decision="approve"):
    """Echo only the complete reviewed digest and nonce for one explicit synthetic owner choice."""
    return dict(
        decision=decision,
        scope_digest=review["scope_digest"],
        review_nonce=review["review_nonce"],
    )


def test_actual_owner_review_decision_and_private_event(approval_client, caplog):
    """Fetch full concrete data and approve exactly once through actual auth/routes without changing any source bytes."""
    client, auth, specs, roots, store, identifier = approval_client
    before = (roots[0] / "main.py").read_bytes()
    response = client.get(url(identifier), headers=auth["headers"][0])
    assert response.status_code == 200
    review = response.json()
    assert review["artifact"] == ARTIFACT.decode() and review["owner_id"] == str(
        auth["principals"][0]
    )
    assert (
        response.headers["cache-control"] == "private, no-store"
        and response.headers["x-content-type-options"] == "nosniff"
    )
    body = decision_body(review)
    approved = client.post(
        url(identifier) + "/decision", headers=auth["headers"][0], json=body
    )
    assert approved.status_code == 200 and approved.json()["state"] == "approved"
    assert "review_nonce" not in approved.json() and "artifact" not in approved.json()
    assert (
        client.post(
            url(identifier) + "/decision", headers=auth["headers"][0], json=body
        ).status_code
        == 409
    )
    receipt = store.consume(
        auth["principals"][0],
        identifier,
        UUID(specs[0]["workspace_id"]),
        "patch",
        ARTIFACT,
    )
    assert (
        receipt["state"] == "consumed" and (roots[0] / "main.py").read_bytes() == before
    )
    assert review["review_nonce"] not in caplog.text and "disposable" not in caplog.text


@pytest.mark.parametrize(
    "fault",
    [
        "unauthorized",
        "foreign",
        "unknown",
        "origin",
        "owner",
        "workspace",
        "artifact",
        "execute",
        "model",
        "nonce",
        "digest",
    ],
)
def test_actual_scope_and_authority_violations_cannot_approve(approval_client, fault):
    """Reject auth/owner/Origin/extra-authority/forged-review attempts while leaving the original request pending."""
    client, auth, _, _, store, identifier = approval_client
    review = store.review(auth["principals"][0], identifier)
    headers = dict(auth["headers"][0])
    request_id = identifier
    body = decision_body(review)
    if fault == "unauthorized":
        headers = {}
    elif fault == "foreign":
        headers = dict(auth["headers"][1])
    elif fault == "unknown":
        request_id = uuid4()
    elif fault == "origin":
        headers["Origin"] = "https://untrusted.invalid"
    elif fault in {"owner", "workspace", "artifact", "execute", "model"}:
        body[fault] = "untrusted"
    elif fault == "nonce":
        body["review_nonce"] = "a" * 43
    else:
        body["scope_digest"] = "0" * 64
    response = client.post(url(request_id) + "/decision", headers=headers, json=body)
    assert response.status_code in {401, 403, 404, 409, 422}
    assert store.review(auth["principals"][0], identifier)["state"] == "pending"


@pytest.mark.parametrize(
    "raw",
    [
        b'{"decision":NaN}',
        b'{"decision":"approve","decision":"reject"}',
        b'{"decision":"\\ud800"}',
        b"x" * 16385,
    ],
)
def test_strict_bounded_approval_json_never_changes_state(approval_client, raw):
    """Reuse actual bounded stream/strict JSON parsing before any approval transition."""
    client, auth, _, _, store, identifier = approval_client
    response = client.post(
        url(identifier) + "/decision", headers=auth["headers"][0], content=raw
    )
    assert response.status_code in {413, 422}
    assert store.review(auth["principals"][0], identifier)["state"] == "pending"


def test_foreign_unknown_review_and_no_public_create_consume_routes(approval_client):
    """Expose only owner review/decision and never turn arbitrary client JSON into request creation or execution authority."""
    client, auth, _, _, _, identifier = approval_client
    foreign = client.get(url(identifier), headers=auth["headers"][1])
    unknown = client.get(url(uuid4()), headers=auth["headers"][0])
    assert foreign.status_code == unknown.status_code == 404
    assert foreign.json() == unknown.json()
    assert client.post(
        "/api/v1/approvals", headers=auth["headers"][0], json={}
    ).status_code in {404, 405}
    assert (
        client.post(
            url(identifier) + "/consume", headers=auth["headers"][0], json={}
        ).status_code
        == 404
    )


def test_actual_http_exact_deadline_and_cli_expired_review(approval_client):
    """Use a disclosed server clock to reject expiry at the actual route without sleeping or extending grant lifetime."""
    client, auth, _, _, store, identifier = approval_client
    review = store.review(auth["principals"][0], identifier)
    store.clock = lambda: store._records[identifier].deadline
    response = client.post(
        url(identifier) + "/decision",
        headers=auth["headers"][0],
        json=decision_body(review),
    )
    assert response.status_code == 409
    assert (
        client.get(url(identifier), headers=auth["headers"][0]).json()["state"]
        == "expired"
    )


def test_real_loopback_cli_review_and_one_shot_fixture_consumption(approval_client):
    """Perform actual Uvicorn/TCP CLI fetch/explicit decision on a synthetic owner request without executing its proposed action."""
    client, auth, specs, roots, store, identifier = approval_client
    before = (roots[0] / "main.py").read_bytes()
    output = []
    token = auth["headers"][0]["Authorization"].split(" ", 1)[1]
    with localhost_server(client) as base:
        result = review_approval(
            base + "/api/v1",
            identifier,
            token,
            read_line=lambda prompt: "APPROVE " + str(identifier),
            write=output.append,
        )
    assert result == 0 and "No action executed." in output[-1]
    assert token not in "\n".join(output)
    assert (
        store.consume(
            auth["principals"][0],
            identifier,
            UUID(specs[0]["workspace_id"]),
            "patch",
            ARTIFACT,
        )["state"]
        == "consumed"
    )
    with pytest.raises(ApprovalError):
        store.consume(
            auth["principals"][0],
            identifier,
            UUID(specs[0]["workspace_id"]),
            "patch",
            ARTIFACT,
        )
    assert (roots[0] / "main.py").read_bytes() == before


def test_disabled_approval_review_is_inert(workspace_client):
    """Keep the authenticated route unavailable under default-off startup without creating implicit requests."""
    client, auth, _, _ = workspace_client
    assert client.get(url(uuid4()), headers=auth["headers"][0]).status_code == 503
