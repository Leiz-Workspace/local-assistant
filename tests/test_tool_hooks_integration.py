"""Verify trusted generic hooks delegate actual accepted workspace/MCP reads without changing scope or bypassing their checks."""

import hashlib
import json
from pathlib import Path
from uuid import uuid4

import pytest
from test_mcp_adapter import EchoArguments
from test_skill_contract import manifest
from test_workspace_reader import source_workspace as source_workspace

from apps.api.services.skill_tools import SkillToolRun
from apps.api.services.workspaces import WorkspaceService
from src.application.services.mcp_adapter import (
    McpAdapter,
    McpServer,
    McpTool,
    schema_digest,
)
from src.application.services.skill_contract import SkillRegistry
from src.application.services.tool_hooks import GuardedToolRun, HookCall
from src.infrastructure.mcp_stdio import PinnedPythonStdio


@pytest.mark.asyncio
async def test_actual_skill_narrowed_native_read_passes_both_permission_barriers(
    source_workspace,
):
    """Retain the existing kernel-scoped read and exact installed authority beneath metadata-only hooks."""
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
    workspace = WorkspaceService(catalog)
    skill = SkillToolRun(
        registry, installed, workspace, spec.owner_id, spec.workspace_id
    )
    payload = json.dumps(
        dict(
            name="workspace.read",
            arguments=dict(path="src/main.py", start_line=2, end_line=4),
        )
    ).encode()
    checks = []

    async def authorize(call):
        """Use the real installed owner/permission check and grant no additional authority."""
        registry.authorize(call.owner_id, call.workspace_id, installed, call.tool)
        checks.append(call.call_id)

    async def operation(call):
        """Delegate unchanged checked request bytes to the existing native dispatcher."""
        assert call.arguments_sha256 == hashlib.sha256(payload).hexdigest()
        return await skill.execute(payload)

    run = GuardedToolRun(
        spec.owner_id,
        spec.workspace_id,
        profile="core",
        effects={"workspace.read": "read"},
        authorize=authorize,
    )
    call = HookCall(
        spec.owner_id,
        spec.workspace_id,
        run.identifier,
        uuid4(),
        "core",
        "workspace.read",
        hashlib.sha256(payload).hexdigest(),
    )
    try:
        result = await run.execute(call, operation)
        assert json.loads(result)["name"] == "workspace.read" and len(checks) == 2
        assert run.events[-1].outcome == "completed"
    finally:
        await run.close()
        await skill.close()
        await workspace.shutdown()
        registry.shutdown()
    assert not workspace.operations and run.active is None


@pytest.mark.asyncio
async def test_actual_pinned_stdio_call_retains_untrusted_output_and_joined_connections():
    """Run the real inert MCP fixture through the generic guard without adopting server-advertised tools or instructions."""
    owner, workspace = uuid4(), uuid4()
    script = Path("tests/fixtures/mcp/echo_server.py")
    transport = PinnedPythonStdio(
        script, hashlib.sha256(script.read_bytes()).hexdigest()
    )
    adapter = McpAdapter(
        owner,
        (
            McpServer(
                "fixture",
                owner,
                transport,
                (McpTool("echo", EchoArguments, schema_digest(EchoArguments), True),),
            ),
        ),
        profile="core",
    )
    await adapter.discover(owner, "fixture")
    args = {"text": "neutral hook protocol sample"}
    digest = hashlib.sha256(
        json.dumps(args, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()

    async def authorize(call):
        """Require the bound owner and exact host-reviewed server/tool without using remote annotations."""
        assert (
            call.owner_id == owner
            and call.workspace_id == workspace
            and call.tool == "mcp.fixture.echo"
        )

    async def operation(call):
        """Serialize only the source-bound untrusted MCP result into complete immutable response bytes."""
        assert call.arguments_sha256 == digest
        result = await adapter.call(owner, "fixture", "echo", args)
        return json.dumps(
            dict(
                content=result.content,
                content_trust=result.content_trust,
                server_id=result.server_id,
            )
        ).encode()

    run = GuardedToolRun(
        owner,
        workspace,
        profile="core",
        effects={"mcp.fixture.echo": "read"},
        authorize=authorize,
    )
    call = HookCall(
        owner, workspace, run.identifier, uuid4(), "core", "mcp.fixture.echo", digest
    )
    try:
        result = json.loads(await run.execute(call, operation))
        assert (
            result["content_trust"] == "untrusted" and result["server_id"] == "fixture"
        )
        assert run.events[-1].outcome == "completed"
    finally:
        await run.close()
        await adapter.close()
    assert transport.reaped and transport.stderr_task.done()
