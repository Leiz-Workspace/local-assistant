"""Verify reviewed skill narrowing through the actual accepted native workspace dispatcher and revocation boundaries."""

import json
from dataclasses import replace

import pytest
from test_skill_contract import manifest
from test_workspace_reader import source_workspace as source_workspace

from apps.api.services.skill_tools import SkillToolRun
from apps.api.services.workspaces import WorkspaceService
from src.application.services.skill_contract import SkillError, SkillRegistry


@pytest.mark.asyncio
async def test_actual_workspace_tool_is_narrowed_and_native_resources_are_joined(
    source_workspace,
):
    """Read a real disposable source using the old dispatcher while rejecting any undeclared tool or trust action."""
    catalog, spec, _, _ = source_workspace
    registry = SkillRegistry()
    raw = manifest()
    review = registry.review(spec.owner_id, spec.workspace_id, raw)
    installed = registry.install(
        spec.owner_id,
        spec.workspace_id,
        review.identifier,
        raw,
        reviewed_sha256=review.manifest_sha256,
        explicit_trust=True,
    )
    service = WorkspaceService(catalog)
    async with SkillToolRun(
        registry, installed, service, spec.owner_id, spec.workspace_id
    ) as run:
        result = await run.execute(
            json.dumps(
                dict(
                    name="workspace.read",
                    arguments=dict(path="src/main.py", start_line=2, end_line=4),
                )
            ).encode()
        )
        assert json.loads(result)["name"] == "workspace.read"
        assert run.run.attempts == 1
        with pytest.raises(SkillError, match="permission_denied"):
            await run.execute(
                b'{"name":"workspace.search","arguments":{"query":"text"}}'
            )
        assert run.run.attempts == 1
        registry.uninstall(spec.owner_id, spec.workspace_id, installed)
        with pytest.raises(SkillError, match="not_installed"):
            await run.execute(
                b'{"name":"workspace.read","arguments":{"path":"src/main.py"}}'
            )
    assert run.run.closed and not service.operations and not service.admission.locked()
    await service.shutdown()


@pytest.mark.asyncio
async def test_denied_calls_charge_the_outer_budget_and_revocation_blocks_a_completed_read(
    source_workspace,
):
    """Bound rejected model attempts and recheck exact installation after real native work finishes."""
    catalog, spec, _, _ = source_workspace
    registry = SkillRegistry()
    raw = manifest()
    review = registry.review(spec.owner_id, spec.workspace_id, raw)
    installed = registry.install(
        spec.owner_id,
        spec.workspace_id,
        review.identifier,
        raw,
        reviewed_sha256=review.manifest_sha256,
        explicit_trust=True,
    )
    service = WorkspaceService(catalog)
    async with SkillToolRun(
        registry, installed, service, spec.owner_id, spec.workspace_id
    ) as run:
        for _ in range(8):
            with pytest.raises(SkillError, match="permission_denied"):
                await run.execute(b'{"name":"shell","arguments":{}}')
        with pytest.raises(SkillError, match="attempt_limit"):
            await run.execute(
                b'{"name":"workspace.read","arguments":{"path":"src/main.py"}}'
            )
        assert run.run.attempts == 0
    async with SkillToolRun(
        registry, installed, service, spec.owner_id, spec.workspace_id
    ) as run:
        original = run.run.execute

        async def revoke_after_read(payload):
            """Revoke the installation between actual native completion and the wrapper's publication barrier."""
            result = await original(payload)
            registry.uninstall(spec.owner_id, spec.workspace_id, installed)
            return result

        run.run.execute = revoke_after_read
        with pytest.raises(SkillError, match="not_installed"):
            await run.execute(
                b'{"name":"workspace.read","arguments":{"path":"src/main.py","start_line":2,"end_line":4}}'
            )
    assert not service.operations
    await service.shutdown()


@pytest.mark.asyncio
async def test_forged_installation_and_malformed_tool_json_fail_before_native_work(
    source_workspace,
):
    """Reject copied installation authority and invalid/extra envelope keys without opening source files."""
    catalog, spec, _, _ = source_workspace
    registry = SkillRegistry()
    raw = manifest()
    review = registry.review(spec.owner_id, spec.workspace_id, raw)
    installed = registry.install(
        spec.owner_id,
        spec.workspace_id,
        review.identifier,
        raw,
        reviewed_sha256=review.manifest_sha256,
        explicit_trust=True,
    )
    service = WorkspaceService(catalog)
    with pytest.raises(SkillError, match="not_installed"):
        SkillToolRun(
            registry, replace(installed), service, spec.owner_id, spec.workspace_id
        )
    async with SkillToolRun(
        registry, installed, service, spec.owner_id, spec.workspace_id
    ) as run:
        for payload in [
            b"{}",
            b"{",
            b'{"name":"workspace.read","arguments":{},"owner_id":"fake"}',
            b'{"name":"workspace.read","name":"shell","arguments":{}}',
        ]:
            with pytest.raises(SkillError, match="permission_denied"):
                await run.execute(payload)
        assert run.run.attempts == 0 and not service.operations
    await service.shutdown()
