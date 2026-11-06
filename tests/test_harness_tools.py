"""Verify deterministic finite tool routes, real disposable approval workflows and refusal to accept model-selected action authority."""

import json
from uuid import UUID, uuid4

import pytest
from test_atomic_patch import patch_fixture as patch_fixture
from test_check_jobs import job_store as job_store
from test_check_service import check_service as check_service
from test_check_service import proposal as check_proposal
from test_patch_service import approve_existing, propose
from test_patch_service import patch_service as patch_service

from apps.api.services.harness_tools import HarnessToolRun
from src.application.services.tool_hooks import HookError


def envelope(name, **arguments):
    """Encode a model-like operation containing only its name and bounded literal arguments."""
    return json.dumps(dict(name=name, arguments=arguments)).encode()


def routed(service, spec, **changes):
    """Bind only already owned disposable service scope with no model-selected routes or approval decisions."""
    return HarnessToolRun(
        spec.owner_id,
        spec.workspace_id,
        profile="core",
        workspace_service=service.workspace,
        patches=service,
        **changes,
    )


@pytest.mark.parametrize(
    "fault", ["scope", "shell", "approval", "target", "coerce", "duplicate"]
)
@pytest.mark.asyncio
async def test_model_cannot_supply_scope_grants_commands_or_ambiguous_json(
    patch_service, patch_fixture, fault
):
    """Reject the complete malformed envelope before any pending proposal or original native file changes."""
    service, spec = patch_service
    value = routed(service, spec)
    raw = envelope("patch.apply", target_id=str(uuid4()))
    payload = json.loads(raw)
    if fault == "scope":
        payload["owner"] = str(uuid4())
    if fault == "shell":
        payload["name"] = "shell"
    if fault == "approval":
        payload["arguments"]["approval"] = str(uuid4())
    if fault == "target":
        payload["arguments"]["target_id"] = str(uuid4()).upper()
    if fault == "coerce":
        payload["arguments"]["target_id"] = 1
    raw = (
        b'{"name":"patch.apply","name":"workspace.read","arguments":{}}'
        if fault == "duplicate"
        else json.dumps(payload).encode()
    )
    with pytest.raises(HookError):
        await value.execute(raw)
    assert patch_fixture[1].read_bytes() == patch_fixture[2] and not service.records
    await value.close()


@pytest.mark.asyncio
async def test_real_pending_reference_is_not_approval_and_never_applies(
    patch_service, patch_fixture
):
    """Retain an existing pending reference without upgrading its state or allowing its native action."""
    service, spec = patch_service
    proposal = await propose(service, spec, patch_fixture[2])
    value = routed(service, spec)
    target, approval = UUID(proposal["proposal_id"]), UUID(proposal["approval_id"])
    value.attach_approval_reference(
        spec.owner_id, spec.workspace_id, "patch.apply", target, approval
    )
    with pytest.raises(HookError, match="uncertain"):
        await value.execute(envelope("patch.apply", target_id=str(target)))
    assert patch_fixture[1].read_bytes() == patch_fixture[2]
    assert service.approvals.review(spec.owner_id, approval)["state"] == "pending"
    assert value.references == {} and value.guard.stopping
    assert value.guard.events[-1].outcome == "uncertain"
    await value.close()


@pytest.mark.asyncio
async def test_actual_approved_patch_and_read_use_exact_existing_services(
    patch_service, patch_fixture, caplog
):
    """Apply the exact fixture-approved bytes once and retain native authoritative receipt without logging bodies or grants."""
    caplog.set_level("INFO")
    service, spec = patch_service
    proposal = await propose(
        service, spec, patch_fixture[2], replacement="private approved replacement\n"
    )
    target = UUID(proposal["proposal_id"])
    approval = approve_existing(service, spec, proposal)
    value = routed(service, spec)
    value.attach_approval_reference(
        spec.owner_id, spec.workspace_id, "patch.apply", target, approval
    )
    result = json.loads(
        await value.execute(envelope("patch.apply", target_id=str(target)))
    )
    assert (
        result["receipt"]["applied"]
        and patch_fixture[1].read_bytes() == b"private approved replacement\n"
    )
    assert service.approvals.review(spec.owner_id, approval)["state"] == "consumed"
    read = await value.execute(envelope("workspace.read", path="src/main.py"))
    assert b"private approved replacement" in read
    router_logs = "\n".join(
        record.getMessage()
        for record in caplog.records
        if record.name == "apps.api.services.harness_tools"
    )
    assert "private approved replacement" not in caplog.text
    assert str(approval) not in router_logs
    assert [event.outcome for event in value.guard.events] == [
        "pending",
        "completed",
        "pending",
        "completed",
    ]
    with pytest.raises(HookError):
        await value.execute(envelope("patch.apply", target_id=str(target)))
    assert (await service.review(spec.owner_id, spec.workspace_id, target))[
        "receipt"
    ] == result["receipt"]
    await value.close()


@pytest.mark.parametrize("fault", ["foreign", "target", "action", "revoked"])
@pytest.mark.asyncio
async def test_host_attachment_cannot_redirect_or_resurrect_original_action(
    patch_service, patch_fixture, fault
):
    """Reject cross-owner attachments and fail safely on wrong target/action or explicitly rejected original reviews."""
    service, spec = patch_service
    proposal = await propose(service, spec, patch_fixture[2])
    target, approval = UUID(proposal["proposal_id"]), UUID(proposal["approval_id"])
    value = routed(service, spec)
    if fault == "foreign":
        with pytest.raises(HookError):
            value.attach_approval_reference(
                uuid4(), spec.workspace_id, "patch.apply", target, approval
            )
    else:
        if fault == "revoked":
            review = service.approvals.review(spec.owner_id, approval)
            service.approvals.decide(
                spec.owner_id,
                approval,
                "reject",
                review["scope_digest"],
                review["review_nonce"],
            )
        else:
            approve_existing(service, spec, proposal)
        value.attach_approval_reference(
            spec.owner_id,
            spec.workspace_id,
            "checks.run" if fault == "action" else "patch.apply",
            uuid4() if fault == "target" else target,
            approval,
        )
        with pytest.raises(HookError):
            await value.execute(envelope("patch.apply", target_id=str(target)))
    assert patch_fixture[1].read_bytes() == patch_fixture[2]
    await value.close()


@pytest.mark.asyncio
async def test_actual_approved_native_check_and_history_survive_router_close(
    check_service,
):
    """Run existing pinned offline Ruff against approved disposable source and preserve its authoritative observation."""
    service, sources = check_service
    proposal = await check_proposal(check_service)
    target, approval = UUID(proposal["job_id"]), UUID(proposal["approval_id"])
    review = service.approvals.review(sources.owner, approval)
    service.approvals.decide(
        sources.owner,
        approval,
        "approve",
        review["scope_digest"],
        review["review_nonce"],
    )
    value = HarnessToolRun(
        sources.owner,
        sources.workspace,
        profile="core",
        workspace_service=service.workspace,
        checks=service,
    )
    value.attach_approval_reference(
        sources.owner, sources.workspace, "checks.run", target, approval
    )
    result = json.loads(
        await value.execute(envelope("checks.run", target_id=str(target)))
    )
    assert (
        result["observation"]["exit_code"] == 0
        and not result["observation"]["quality_evaluated"]
    )
    assert not result["live_proposal"] and not result["recovered_approval"]
    await value.close()
    assert (await service.read(sources.owner, sources.workspace, target))[
        "observation"
    ] == result["observation"]


@pytest.mark.parametrize("profile", [None, True, "unrestricted", "CORE"])
def test_profile_requires_explicit_host_core(patch_service, profile):
    """Refuse profile coercion or privilege fallback before allocating a routed run."""
    service, spec = patch_service
    with pytest.raises(HookError):
        HarnessToolRun(
            spec.owner_id,
            spec.workspace_id,
            profile=profile,
            workspace_service=service.workspace,
        )


@pytest.mark.asyncio
async def test_invalid_attempts_share_the_router_budget(patch_service):
    """Charge invalid model envelopes too and deny later work rather than providing an unlimited parsing oracle."""
    service, spec = patch_service
    value = routed(service, spec)
    for _ in range(8):
        with pytest.raises(HookError, match="invalid_scope"):
            await value.execute(b"{}")
    with pytest.raises(HookError, match="limit"):
        await value.execute(envelope("workspace.discover"))
    assert not value.guard.events
    await value.close()
