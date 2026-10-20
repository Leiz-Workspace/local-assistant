"""Verify finite shared tool contracts, native source provenance and exact controlled run-budget/cancellation boundaries."""

import asyncio
import hashlib
import json
import logging
import threading
from contextlib import asynccontextmanager
from dataclasses import FrozenInstanceError
from uuid import UUID, uuid4

import pytest
from test_workspace_reader import source_workspace as source_workspace

from apps.api.routes import workspaces as routes
from apps.api.services import workspace_tools as module
from apps.api.services import workspaces as workspace_module
from apps.api.services.workspace_tools import WorkspaceToolRun
from apps.api.services.workspaces import WorkspaceService
from src.application.services.workspace_policy import WorkspaceAccessError
from src.application.services.workspace_tool_contracts import (
    TOOL_REGISTRY,
    DirectoryInput,
    ReadInput,
    SearchInput,
    workspace_tool_schemas,
)


def envelope(name="read", **arguments):
    """Encode independent model-like tool input without trusted identities or policy controls."""
    return json.dumps(dict(name="workspace." + name, arguments=arguments)).encode()


@pytest.fixture
def tool_run(source_workspace):
    """Create an actual workspace service and ephemeral trusted run on disposable source fixtures."""
    catalog, spec, _, _ = source_workspace
    return WorkspaceToolRun(WorkspaceService(catalog), spec.owner_id, spec.workspace_id)


def test_finite_shared_contracts_and_fixed_server_policy():
    """Verify exact registered models, fresh schemas and server defaults without duplicated HTTP schemas."""
    assert routes.DirectoryInput is DirectoryInput
    assert routes.ReadInput is ReadInput
    assert routes.SearchInput is SearchInput
    assert set(TOOL_REGISTRY) == {
        "workspace." + name
        for name in ("discover", "inventory", "read", "search", "symbols")
    }
    schemas = workspace_tool_schemas()
    for row in schemas:
        assert row["parameters"] == TOOL_REGISTRY[row["name"]][1].model_json_schema()
        assert row["parameters"]["additionalProperties"] is False
    schemas[0]["parameters"]["additionalProperties"] = True
    assert workspace_tool_schemas()[0]["parameters"]["additionalProperties"] is False
    with pytest.raises(TypeError):
        TOOL_REGISTRY["shell"] = ("shell", ReadInput)
    assert (
        module.MAX_ATTEMPTS,
        module.MAX_RUN_SECONDS,
        module.MAX_TOOL_SECONDS,
        module.MAX_CALL_SECONDS,
        module.MAX_CALL_BYTES,
        module.MAX_RUN_BYTES,
    ) == (8, 60, 20, 5, 65536, 262144)


@pytest.mark.asyncio
@pytest.mark.parametrize("name", ["discover", "inventory", "read", "search", "symbols"])
async def test_actual_native_tool_success_and_cleanup(tool_run, source_workspace, name):
    """Verify original native paths/hashes/quotes and release admission before returning immutable bytes."""
    arguments = {
        "read": dict(path="src/main.py", start_line=2, end_line=4),
        "search": dict(query="chào 𝄞"),
    }.get(name, {})
    raw = await tool_run.execute(envelope(name, **arguments))
    result = json.loads(raw)
    assert isinstance(raw, bytes) and result["name"] == "workspace." + name
    assert UUID(result["run_id"]) == tool_run.scope.run_id
    assert UUID(result["call_id"]) != tool_run.scope.run_id
    assert tool_run.output_bytes == len(raw) and tool_run.attempts == 1
    assert (
        not tool_run.workspace.admission.locked() and not tool_run.workspace.operations
    )
    data = result["data"]
    if name == "read":
        assert [r["line_number"] for r in data["lines"]] == [2, 3, 4]
        for row in data["lines"]:
            assert (
                row["source_sha256"] == hashlib.sha256(source_workspace[3]).hexdigest()
            )
            assert row["line_text"] == source_workspace[3].decode().split("\n")[
                row["line_number"] - 1
            ].removesuffix("\r")
    assert b"HIDDEN-CANARY" not in raw and b"OUTSIDE-CANARY" not in raw
    await tool_run.close()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "raw",
    [
        b'{"name":"shell","arguments":{}}',
        b'{"name":"workspace.read","arguments":{"path":"a"},"owner_id":"x"}',
        b'{"name":"workspace.discover","arguments":{"workspace_id":"x"}}',
        b'{"name":"workspace.discover","arguments":{"root":"/etc"}}',
        b'{"name":"workspace.discover","arguments":{"budget":999}}',
        b'{"name":"workspace.discover","arguments":{"command":"id"}}',
        b'{"name":"workspace.discover","arguments":{"profile":"unrestricted"}}',
        b'{"name":"workspace.discover","arguments":{},"call_id":"x"}',
        b'{"name":"workspace.read","arguments":{"path":"../outside.txt"}}',
        b'{"name":"workspace.read","arguments":{"path":".env"}}',
        b'{"name":"workspace.read","arguments":{"path":"/etc/passwd"}}',
        b'{"name":"workspace.read","arguments":{"path":"a","start_line":true}}',
        b'{"name":"workspace.read","arguments":{"path":"a","start_line":2,"end_line":1}}',
        b'{"name":"workspace.read","arguments":{"path":"a","end_line":201}}',
        b'{"name":"workspace.search","arguments":{"query":" "}}',
        envelope("search", query="á" * 129),
        b'{"name":"workspace.search","arguments":{"query":1}}',
        b'{"name":"workspace.search","arguments":{"query":"a","regex":true}}',
        b'{"name":"workspace.read","arguments":{"path":"a","path":"b"}}',
        b'{"name":"workspace.discover","arguments":{},"name":"shell"}',
        b'{"name":"workspace.discover","arguments":{"x":NaN}}',
        b'{"name":"workspace.discover","arguments":{"x":1e999}}',
        b'{"name":"workspace.discover","arguments":{"x":"\\ud800"}}',
        b'{"name":"workspace.discover","arguments":[]}',
        b"[]",
        b"not json",
        b" " * 16385,
    ],
)
async def test_invalid_untrusted_envelopes_fail_before_root_open(
    tool_run, monkeypatch, raw
):
    """Reject malformed schema, traversal and authority injection with a forbidden native-open oracle."""

    def forbidden(*arguments, **options):
        """Fail if rejected untrusted arguments ever reach workspace-root admission."""
        pytest.fail("invalid input reached native root")

    monkeypatch.setattr(tool_run.workspace.catalog, "open", forbidden)
    with pytest.raises(WorkspaceAccessError):
        await tool_run.execute(raw)
    assert tool_run.attempts == 1 and not tool_run.output_bytes
    assert not tool_run.admission.locked() and tool_run.active is None


@pytest.mark.asyncio
async def test_exact_attempt_limit_and_invalid_calls_consume_capacity(tool_run):
    """Admit the eighth repeated call and reject the ninth without retries or budget refunds."""
    with pytest.raises(WorkspaceAccessError):
        await tool_run.execute(b"invalid")
    identifiers = set()
    for _ in range(7):
        result = json.loads(await tool_run.execute(envelope("discover")))
        identifiers.add(result["call_id"])
    assert len(identifiers) == 7 and tool_run.attempts == 8
    with pytest.raises(WorkspaceAccessError, match="tool_attempt_limit"):
        await tool_run.execute(envelope("discover"))
    assert tool_run.attempts == 9


@pytest.mark.asyncio
@pytest.mark.parametrize("fault", ["foreign", "unknown", "symlink", "hidden"])
async def test_actual_scope_and_native_path_denial(source_workspace, fault):
    """Exercise real owner authorization and kernel/path denials through the dispatcher."""
    catalog, spec, _, _ = source_workspace
    owner = uuid4() if fault == "foreign" else spec.owner_id
    workspace = uuid4() if fault == "unknown" else spec.workspace_id
    run = WorkspaceToolRun(WorkspaceService(catalog), owner, workspace)
    path = {"symlink": "linked.txt", "hidden": ".env"}.get(fault, "readme.txt")
    with pytest.raises(WorkspaceAccessError):
        await run.execute(envelope(path=path))
    assert not run.workspace.operations and not run.workspace.admission.locked()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "boundary", ["call_exact", "call_over", "run_exact", "run_over"]
)
async def test_serialized_output_boundaries(tool_run, monkeypatch, boundary):
    """Measure complete actual UTF-8 envelopes and test exact versus one-byte-over controlled caps."""
    first = await tool_run.execute(envelope("discover"))
    length = len(first)
    if boundary.startswith("call"):
        monkeypatch.setattr(
            module, "MAX_CALL_BYTES", length - (boundary == "call_over")
        )
    else:
        monkeypatch.setattr(
            module, "MAX_RUN_BYTES", 2 * length - (boundary == "run_over")
        )
    if boundary.endswith("over"):
        with pytest.raises(WorkspaceAccessError, match="tool_output_limit"):
            await tool_run.execute(envelope("discover"))
    else:
        assert len(await tool_run.execute(envelope("discover"))) == length
    assert tool_run.output_bytes == 2 * length
    assert not tool_run.workspace.operations and not tool_run.admission.locked()
    if boundary == "run_exact":
        with pytest.raises(WorkspaceAccessError, match="tool_output_limit"):
            await tool_run.execute(envelope("discover"))


@pytest.mark.asyncio
@pytest.mark.parametrize("boundary", ["lifetime", "cumulative", "call"])
async def test_controlled_exact_time_boundaries(
    source_workspace, monkeypatch, boundary
):
    """Use a disclosed tool-only synthetic clock to reject exact elapsed server deadlines."""
    clock = [0.0]
    monkeypatch.setattr(module, "monotonic", lambda: clock[0])
    catalog, spec, _, _ = source_workspace
    run = WorkspaceToolRun(WorkspaceService(catalog), spec.owner_id, spec.workspace_id)
    if boundary == "lifetime":
        clock[0] = 60.0
    elif boundary == "cumulative":
        run.tool_seconds = 20.0
    else:
        original = run.workspace.validate

        async def expire(snapshot):
            """Validate actual source then advance only the controlled dispatch clock to its exact call limit."""
            await original(snapshot)
            clock[0] = 5.0

        monkeypatch.setattr(run.workspace, "validate", expire)
    with pytest.raises(WorkspaceAccessError, match="tool_time_limit"):
        await run.execute(envelope("discover"))
    assert run.attempts == 1 and not run.workspace.operations
    assert not run.workspace.admission.locked() and not run.admission.locked()
    if boundary == "call":
        assert run.tool_seconds == 5.0 and run.output_bytes > 0


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["cancel", "repeat_cancel", "close", "timeout"])
async def test_actual_worker_cancel_timeout_overlap_and_join(
    tool_run, monkeypatch, action
):
    """Hold a real file worker and verify nonqueued admission, stop propagation and joined teardown."""
    entered, exited = threading.Event(), threading.Event()
    original = workspace_module.build_snapshot

    def delayed(*arguments):
        """Wait for the actual cooperative stop event before executing original native cleanup."""
        entered.set()
        arguments[-1].wait(2)
        try:
            return original(*arguments)
        finally:
            exited.set()

    monkeypatch.setattr(workspace_module, "build_snapshot", delayed)
    if action == "timeout":
        monkeypatch.setattr(module, "MAX_CALL_SECONDS", 0.03)
    task = asyncio.create_task(tool_run.execute(envelope("discover")))
    assert await asyncio.to_thread(entered.wait, 2)
    with pytest.raises(WorkspaceAccessError, match="tool_run_busy"):
        await tool_run.execute(envelope("discover"))
    if action == "close":
        await tool_run.close()
    elif action != "timeout":
        task.cancel()
        if action == "repeat_cancel":
            await asyncio.sleep(0)
            task.cancel()
    expected = WorkspaceAccessError if action == "timeout" else asyncio.CancelledError
    with pytest.raises(expected):
        await task
    assert exited.is_set() and not tool_run.workspace.operations
    assert tool_run.attempts == 2 and not tool_run.admission.locked()
    assert not tool_run.workspace.admission.locked()


@pytest.mark.asyncio
async def test_shared_service_admission_across_different_runs(tool_run):
    """Prevent a second run from bypassing the accepted shared workspace admission policy."""
    scope = tool_run.scope
    async with tool_run.workspace.operation(
        scope.owner_id, scope.workspace_id, "discover", {}
    ):
        with pytest.raises(WorkspaceAccessError, match="workspace_busy"):
            await tool_run.execute(envelope("discover"))
    assert tool_run.attempts == 1 and not tool_run.admission.locked()


@pytest.mark.asyncio
async def test_final_native_source_mutation_fails_closed(
    tool_run, source_workspace, monkeypatch
):
    """Change actual bytes after snapshot construction and require final hash fencing before exposure."""
    original = tool_run.workspace.validate

    async def mutate(snapshot):
        """Modify only the disposable fixture between native construction and final validation."""
        (source_workspace[2] / "src/main.py").write_text("changed\n")
        await original(snapshot)

    monkeypatch.setattr(tool_run.workspace, "validate", mutate)
    with pytest.raises(WorkspaceAccessError, match="workspace_source_changed"):
        await tool_run.execute(envelope(path="src/main.py"))
    assert tool_run.output_bytes > 0 and not tool_run.workspace.operations


@pytest.mark.asyncio
@pytest.mark.parametrize("boundary", ["call", "run"])
async def test_actual_fixed_output_caps_without_policy_override(
    tool_run, source_workspace, boundary
):
    """Exceed production byte caps with actual admitted UTF-8 source while preserving the fixed server policy."""
    path = source_workspace[2] / "large.txt"
    if boundary == "call":
        path.write_text(("á" * 400 + "\n") * 100)
        with pytest.raises(WorkspaceAccessError, match="tool_output_limit"):
            await tool_run.execute(envelope(path="large.txt", end_line=100))
        assert tool_run.output_bytes > 65536 and tool_run.attempts == 1
    else:
        path.write_text(("á" * 200 + "\n") * 100)
        first = await tool_run.execute(envelope(path="large.txt", end_line=100))
        assert len(first) < 65536
        accepted = 262144 // len(first)
        assert 1 < accepted < 8
        for _ in range(accepted - 1):
            assert len(
                await tool_run.execute(envelope(path="large.txt", end_line=100))
            ) == len(first)
        with pytest.raises(WorkspaceAccessError, match="tool_output_limit"):
            await tool_run.execute(envelope(path="large.txt", end_line=100))
        assert tool_run.output_bytes > 262144
        assert tool_run.attempts == accepted + 1
    assert (
        not tool_run.workspace.operations and not tool_run.workspace.admission.locked()
    )


@pytest.mark.asyncio
async def test_private_native_failure_is_sanitized_and_charged(
    tool_run, monkeypatch, caplog
):
    """Sanitize a disclosed native failure after serialization and retain its consumed output/attempt budget."""

    async def fail(snapshot):
        """Inject an OS failure with sensitive-looking diagnostics without changing the actual source fixture."""
        raise OSError("PRIVATE-NATIVE-DIAGNOSTIC-CANARY")

    monkeypatch.setattr(tool_run.workspace, "validate", fail)
    with pytest.raises(WorkspaceAccessError, match="tool_unavailable") as caught:
        await tool_run.execute(envelope("discover"))
    assert caught.value.status_code == 503 and tool_run.output_bytes > 0
    assert tool_run.attempts == 1 and not tool_run.workspace.operations
    assert "PRIVATE-NATIVE-DIAGNOSTIC-CANARY" not in caplog.text


@pytest.mark.asyncio
async def test_private_audit_closed_run_and_scope_identity(tool_run, caplog):
    """Log server IDs/status only and preserve immutable scope with sanitized unknown-tool rejection."""
    caplog.set_level(logging.INFO)
    await tool_run.execute(envelope("search", query="Cedar"))
    with pytest.raises(WorkspaceAccessError):
        await tool_run.execute(envelope("PRIVATE-UNKNOWN-CANARY"))
    with pytest.raises(FrozenInstanceError):
        tool_run.scope.owner_id = uuid4()
    await tool_run.close()
    with pytest.raises(WorkspaceAccessError, match="tool_run_closed"):
        await tool_run.execute(envelope("discover"))
    assert tool_run.attempts == 3
    assert "Cedar" not in caplog.text and "PRIVATE-UNKNOWN-CANARY" not in caplog.text
    assert "src/main.py" not in caplog.text and "Xin" not in caplog.text
    assert str(tool_run.scope.run_id) in caplog.text


@pytest.mark.parametrize("bad", [None, "uuid", 1, True])
@pytest.mark.parametrize("field", ["owner", "workspace"])
def test_trusted_scope_requires_typed_identity(source_workspace, bad, field):
    """Reject accidental untyped application scope before any filesystem operation."""
    catalog, spec, _, _ = source_workspace
    with pytest.raises(WorkspaceAccessError, match="tool_scope_invalid"):
        WorkspaceToolRun(
            WorkspaceService(catalog),
            bad if field == "owner" else spec.owner_id,
            bad if field == "workspace" else spec.workspace_id,
        )


@pytest.mark.asyncio
async def test_cleanup_elapsed_time_prevents_late_result(source_workspace, monkeypatch):
    """Include a disclosed controlled cleanup delay in the charged deadline after actual descriptor release."""
    clock = [0.0]
    monkeypatch.setattr(module, "monotonic", lambda: clock[0])
    catalog, spec, _, _ = source_workspace
    service = WorkspaceService(catalog)
    original = service.operation
    retained = []

    @asynccontextmanager
    async def delayed_cleanup(*arguments):
        """Finish native snapshot cleanup then advance only the controlled tool clock to its call deadline."""
        async with original(*arguments) as snapshot:
            retained.append(snapshot)
            yield snapshot
        clock[0] = 5.0

    monkeypatch.setattr(service, "operation", delayed_cleanup)
    run = WorkspaceToolRun(service, spec.owner_id, spec.workspace_id)
    with pytest.raises(WorkspaceAccessError, match="tool_time_limit"):
        await run.execute(envelope("discover"))
    assert retained[0].closed and run.tool_seconds == 5.0
    assert not service.operations and not service.admission.locked()
