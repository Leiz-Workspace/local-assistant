"""Verify actual local owner-authenticated Git checkpoint/recovery and separate explicit CLI approval for edits and byte restores."""

import hashlib
from uuid import UUID, uuid4

import httpx
import pytest
from test_patch_http import base, proposal_body
from test_patch_http import patch_client as patch_client
from test_reranker_tcp_trial import localhost_server
from test_workspace_http import workspace_client as workspace_client

from scripts.review_approval import review_approval


@pytest.fixture
def checkpoint_client(request, tmp_path, monkeypatch):
    """Enable durable composition solely for an explicit private directory outside both temporary synthetic workspace roots."""
    path = tmp_path / "durable-checkpoints"
    path.mkdir(mode=0o700)
    monkeypatch.setenv("ASSISTANT_CHECKPOINT_ENABLED", "1")
    monkeypatch.setenv("ASSISTANT_CHECKPOINT_ROOT", str(path))
    value = request.getfixturevalue("patch_client")
    yield (*value, path)


def checkpoint_base(spec):
    """Build only the fixed owner/workspace-scoped local checkpoint collection path."""
    return "/api/v1/workspaces/" + spec["workspace_id"] + "/checkpoints"


def approve_cli(origin, proposal, headers, shown):
    """Explicitly type the complete newly issued fixture approval UUID using the real bounded local CLI transport."""
    approval = UUID(proposal["approval_id"])
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
    return approval


def test_actual_tcp_two_independent_cli_approvals_restore_exact_source(
    checkpoint_client, caplog
):
    """Perform real Git checkpoint→CLI approved edit→new CLI approved rollback and retain historical journal without inferring causality."""
    client, auth, specs, roots, path = checkpoint_client
    headers = auth["headers"][0]
    original = (roots[0] / "main.py").read_bytes()
    shown = []
    with (
        localhost_server(client) as origin,
        httpx.Client(base_url=origin, trust_env=False) as http,
    ):
        response = http.post(
            base(specs[0]), headers=headers, json=proposal_body(roots[0] / "main.py")
        )
        assert response.status_code == 200, response.text
        proposal = response.json()
        checkpoint = checkpoint_base(specs[0]) + "/" + proposal["checkpoint_id"]
        snapshot = http.get(checkpoint, headers=headers)
        assert (
            snapshot.status_code == 200
            and snapshot.json()["original"].encode() == original
        )
        assert (
            len(snapshot.json()["commit_id"]) == 40
            and not snapshot.json()["recovered_approval"]
        )
        assert snapshot.headers["cache-control"] == "private, no-store"
        first = approve_cli(origin, proposal, headers, shown)
        target = base(specs[0]) + "/" + proposal["proposal_id"] + "/apply"
        assert (
            http.post(
                target, headers=headers, json=dict(approval_id=str(first))
            ).json()["receipt"]["applied"]
            is True
        )
        changed = (roots[0] / "main.py").read_bytes()
        recovery = http.get(checkpoint + "/recovery", headers=headers).json()
        assert (
            recovery["observation"] == "observed_replacement"
            and not recovery["action_taken"]
        )
        response = http.post(
            checkpoint + "/rollback",
            headers=headers,
            json=dict(expected_sha256=hashlib.sha256(changed).hexdigest()),
        )
        assert response.status_code == 200, response.text
        rollback = response.json()
        assert (
            rollback["replacement"].encode() == original
            and rollback["restores_checkpoint_id"] == proposal["checkpoint_id"]
        )
        assert (roots[0] / "main.py").read_bytes() == changed
        restore_target = base(specs[0]) + "/" + rollback["proposal_id"] + "/apply"
        assert (
            http.post(
                restore_target, headers=headers, json=dict(approval_id=str(first))
            ).status_code
            == 409
        )
        second = approve_cli(origin, rollback, headers, shown)
        assert second != first
        restored = http.post(
            restore_target, headers=headers, json=dict(approval_id=str(second))
        )
        assert (
            restored.status_code == 200
            and restored.json()["receipt"]["applied"] is True
        )
        assert (roots[0] / "main.py").read_bytes() == original
        after = http.get(checkpoint + "/recovery", headers=headers).json()
        assert (
            after["observation"] == "observed_original"
            and not after["causality_inferred"]
        )
        assert (
            http.get(checkpoint, headers=headers).json()["journal"]["state"]
            == "applied"
        )
        assert (
            len(
                http.get(checkpoint_base(specs[0]), headers=headers).json()[
                    "checkpoints"
                ]
            )
            == 2
        )
    assert "Birch" not in caplog.text and headers["Authorization"] not in caplog.text
    assert str(path) not in snapshot.text and str(roots[0]) not in snapshot.text
    assert not list(roots[0].glob(".assistant-patch-*"))


@pytest.mark.parametrize(
    "fault",
    [
        "auth",
        "origin",
        "foreign",
        "workspace",
        "unknown",
        "digest",
        "path",
        "replacement",
        "owner",
        "mode",
        "command",
        "approval_id",
    ],
)
def test_rollback_authority_and_body_cannot_change_historical_scope(
    checkpoint_client, fault
):
    """Deny scope/body/auth/Origin/old-grant overrides without source mutation, new grants or private checkpoint changes."""
    client, auth, specs, roots, _ = checkpoint_client
    headers = dict(auth["headers"][0])
    original = (roots[0] / "main.py").read_bytes()
    proposal = client.post(
        base(specs[0]), headers=headers, json=proposal_body(roots[0] / "main.py")
    ).json()
    target = checkpoint_base(specs[0]) + "/" + proposal["checkpoint_id"] + "/rollback"
    body = dict(expected_sha256=hashlib.sha256(original).hexdigest())
    if fault == "auth":
        headers = {}
    elif fault == "origin":
        headers["Origin"] = "https://untrusted.invalid"
    elif fault == "foreign":
        headers = auth["headers"][1]
    elif fault == "workspace":
        target = (
            checkpoint_base(specs[1]) + "/" + proposal["checkpoint_id"] + "/rollback"
        )
    elif fault == "unknown":
        target = checkpoint_base(specs[0]) + "/" + str(uuid4()) + "/rollback"
    elif fault == "digest":
        body["expected_sha256"] = "0" * 64
    else:
        body[fault] = "untrusted"
    response = client.post(target, headers=headers, json=body)
    assert response.status_code in {401, 403, 404, 409, 422}, response.text
    assert (roots[0] / "main.py").read_bytes() == original
    assert len(client.app.state.approval_store._records) == 1
    assert len(client.app.state.patch_service.records) == 1


def test_checkpoint_foreign_and_unknown_history_are_uniform(checkpoint_client):
    """Return indistinguishable owner-denied history and never reveal another owner's durable IDs through listing."""
    client, auth, specs, roots, _ = checkpoint_client
    proposal = client.post(
        base(specs[0]),
        headers=auth["headers"][0],
        json=proposal_body(roots[0] / "main.py"),
    ).json()
    known = checkpoint_base(specs[0]) + "/" + proposal["checkpoint_id"]
    foreign = client.get(known, headers=auth["headers"][1])
    unknown = client.get(
        checkpoint_base(specs[0]) + "/" + str(uuid4()), headers=auth["headers"][0]
    )
    assert (
        foreign.status_code == unknown.status_code == 404
        and foreign.json() == unknown.json()
    )
    assert (
        client.get(checkpoint_base(specs[1]), headers=auth["headers"][1]).json()[
            "checkpoints"
        ]
        == []
    )


@pytest.mark.parametrize(
    "raw",
    [b'{"expected_sha256":NaN}', b'{"x":1,"x":2}', b'{"x":"\\ud800"}', b"x" * 16385],
)
def test_strict_bounded_rollback_body_has_no_durable_side_effects(
    checkpoint_client, raw
):
    """Reject ambiguous/nonfinite/invalid-Unicode/oversized JSON before backup, source or approval transitions."""
    client, auth, specs, _, path = checkpoint_client
    before = set(path.iterdir())
    response = client.post(
        checkpoint_base(specs[0]) + "/" + str(uuid4()) + "/rollback",
        headers=auth["headers"][0],
        content=raw,
    )
    assert response.status_code in {413, 422} and set(path.iterdir()) == before
    assert not client.app.state.approval_store._records


def test_ephemeral_d40_does_not_implicitly_enable_checkpoint_history(patch_client):
    """Keep D41 history/rollback unavailable when only accepted standalone ephemeral patch capability is enabled."""
    client, auth, specs, _ = patch_client
    response = client.get(checkpoint_base(specs[0]), headers=auth["headers"][0])
    assert (
        response.status_code == 503
        and response.json()["detail"]["code"] == "checkpoint_unavailable"
    )
