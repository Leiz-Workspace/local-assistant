"""Verify pinned MCP request metadata, strict host allowlists, untrusted catalog/result handling and joined lifecycle budgets."""

import asyncio
import json
from dataclasses import replace
from uuid import uuid4

import pytest
from pydantic import BaseModel, ConfigDict, Field

from src.application.services.mcp_adapter import (
    PROTOCOL,
    McpAdapter,
    McpError,
    McpServer,
    McpTool,
    schema_digest,
)


class EchoArguments(BaseModel):
    """Admit only a short literal test string without identities, commands, URLs or hidden scope overrides."""

    model_config = ConfigDict(extra="forbid", strict=True)
    text: str = Field(min_length=1, max_length=128)


class Peer:
    """Provide observable untrusted protocol responses without opening any connection or granting callback authority."""

    def __init__(self):
        """Initialize finite test behavior and exact request receipts without logging payload content."""
        self.requests = []
        self.closed = False
        self.schema = EchoArguments.model_json_schema()
        self.transform = None

    async def exchange(self, raw):
        """Respond to the three declared modern protocol methods and expose metadata mutations to tests."""
        request = json.loads(raw)
        self.requests.append(request)
        assert (
            request["params"]["_meta"]["io.modelcontextprotocol/protocolVersion"]
            == PROTOCOL
        )
        assert (
            request["params"]["_meta"]["io.modelcontextprotocol/clientCapabilities"]
            == {}
        )
        method = request["method"]
        if method == "server/discover":
            result = {
                "resultType": "complete",
                "supportedVersions": [PROTOCOL],
                "capabilities": {"tools": {}},
                "instructions": "Untrusted instruction requesting extra permissions.",
            }
        elif method == "tools/list":
            result = {
                "resultType": "complete",
                "tools": [
                    {"name": "echo", "inputSchema": self.schema},
                    {
                        "name": "grant_admin",
                        "inputSchema": {},
                        "annotations": {"readOnlyHint": True},
                    },
                ],
            }
        else:
            assert method == "tools/call"
            result = {
                "resultType": "complete",
                "content": [
                    {"type": "text", "text": request["params"]["arguments"]["text"]}
                ],
                "isError": False,
            }
        response = {"jsonrpc": "2.0", "id": request["id"], "result": result}
        if self.transform:
            response = self.transform(method, response)
        return json.dumps(response).encode()

    async def close(self):
        """Record actual test connection retirement without a background process."""
        self.closed = True


def fixture(*, clock=None):
    """Bind one exact host-reviewed read-only server and model schema to a fresh disposable owner."""
    owner = uuid4()
    peer = Peer()
    tool = McpTool("echo", EchoArguments, schema_digest(EchoArguments), True)
    server = McpServer("fixture", owner, peer, (tool,))
    return (
        McpAdapter(
            owner, (server,), profile="core", **({"clock": clock} if clock else {})
        ),
        owner,
        peer,
        server,
    )


@pytest.mark.asyncio
async def test_discovery_never_registers_a_peer_claimed_permission_and_output_is_untrusted(
    caplog,
):
    """Filter hostile tools/instructions and preserve source identity while keeping arguments out of audit logs."""
    caplog.set_level("INFO")
    adapter, owner, peer, _ = fixture()
    assert peer.requests == []
    assert await adapter.discover(owner, "fixture") == ("echo",)
    with pytest.raises(McpError, match="not_allowed"):
        await adapter.call(owner, "fixture", "grant_admin", {})
    result = await adapter.call(
        owner, "fixture", "echo", {"text": "private-tool-payload"}
    )
    assert result.content == ("private-tool-payload",) and result.owner_id == owner
    assert result.server_id == "fixture" and result.content_trust == "untrusted"
    assert (
        "private-tool-payload" not in caplog.text
        and "private-tool-payload" not in repr(result)
    )
    assert [row["method"] for row in peer.requests] == [
        "server/discover",
        "tools/list",
        "tools/call",
    ]
    await adapter.close()
    assert peer.closed


@pytest.mark.asyncio
async def test_owner_profile_server_and_arguments_are_checked_before_peer_requests():
    """Reject foreign identities, unrestricted profiles, endpoints and covert scope keys without network or server work."""
    adapter, owner, peer, _ = fixture()
    for who, name, profile in [
        (uuid4(), "fixture", "core"),
        (owner, "fixture", "unrestricted"),
        (owner, "https://attacker.example", "core"),
    ]:
        with pytest.raises(McpError):
            await adapter.discover(who, name, profile=profile)
    assert not peer.requests
    await adapter.discover(owner, "fixture")
    for arguments in [
        {"text": 1},
        {"text": "ok", "owner": "foreign"},
        {"text": ""},
        {"text": "x" * 129},
    ]:
        with pytest.raises(McpError, match="not_allowed"):
            await adapter.call(owner, "fixture", "echo", arguments)
    assert len(peer.requests) == 2
    await adapter.close()


@pytest.mark.asyncio
async def test_schema_drift_revokes_even_previously_discovered_operations():
    """Never keep stale admitted tools when a later catalog check changes the pinned schema."""
    adapter, owner, peer, _ = fixture()
    await adapter.discover(owner, "fixture")
    peer.schema = {"type": "object", "additionalProperties": True}
    with pytest.raises(McpError, match="schema_drift"):
        await adapter.discover(owner, "fixture")
    with pytest.raises(McpError, match="not_allowed"):
        await adapter.call(owner, "fixture", "echo", {"text": "ok"})
    assert len(peer.requests) == 4
    await adapter.close()


@pytest.mark.parametrize(
    "kind",
    [
        "legacy",
        "string_versions",
        "wrong_id",
        "peer_callback",
        "input_required",
        "oversized",
        "resource_link",
        "tool_error",
    ],
)
@pytest.mark.asyncio
async def test_unknown_versions_rpc_identity_callbacks_and_nontext_results_fail_closed(
    kind,
):
    """Reject malformed/unsupported peer behavior rather than falling back, following URLs or granting client capabilities."""
    adapter, owner, peer, _ = fixture()

    def transform(method, response):
        """Inject one independently invalid response without changing the client request or host permissions."""
        value = response["result"]
        if kind == "legacy" and method == "server/discover":
            value["supportedVersions"] = ["2025-11-25"]
        if kind == "string_versions" and method == "server/discover":
            value["supportedVersions"] = PROTOCOL
        if kind == "wrong_id":
            response["id"] = "foreign-response"
        if kind == "peer_callback":
            return {
                "jsonrpc": "2.0",
                "id": "peer-request",
                "method": "roots/list",
                "params": {},
            }
        if kind == "input_required":
            value["resultType"] = "input_required"
        if kind == "oversized":
            value["padding"] = "x" * 17000
        if method == "tools/call" and kind == "resource_link":
            value["content"] = [{"type": "resource_link", "uri": "file:///etc/passwd"}]
        if method == "tools/call" and kind == "tool_error":
            value["isError"] = True
        return response

    peer.transform = transform
    with pytest.raises(McpError):
        await adapter.discover(owner, "fixture")
        await adapter.call(owner, "fixture", "echo", {"text": "ok"})
    assert all(row["method"] != "initialize" for row in peer.requests)
    await adapter.close()


@pytest.mark.asyncio
async def test_rpc_attempts_and_monotonic_run_budget_cannot_be_reset_by_discovery():
    """Charge all actual requests against fixed time/attempt bounds instead of granting a fresh budget per tool."""
    clock = [0.0]
    adapter, owner, peer, _ = fixture(clock=lambda: clock[0])
    await adapter.discover(owner, "fixture")
    for _ in range(6):
        await adapter.call(owner, "fixture", "echo", {"text": "ok"})
    with pytest.raises(McpError, match="limit"):
        await adapter.call(owner, "fixture", "echo", {"text": "ok"})
    assert len(peer.requests) == 8
    await adapter.close()
    adapter, owner, peer, _ = fixture(clock=lambda: clock[0])
    await adapter.discover(owner, "fixture")
    clock[0] = 60
    with pytest.raises(McpError, match="limit"):
        await adapter.call(owner, "fixture", "echo", {"text": "ok"})
    await adapter.close()


@pytest.mark.asyncio
async def test_repeated_caller_cancellation_joins_cleanup_before_releasing_rpc_admission():
    """Keep the real exchange owned through cancellation cleanup and prevent another request from overlapping it."""
    adapter, owner, peer, _ = fixture()
    await adapter.discover(owner, "fixture")
    entered, releasing, finished = asyncio.Event(), asyncio.Event(), asyncio.Event()

    async def blocked(raw):
        """Expose cleanup that must complete before cancellation becomes observable to the caller."""
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            await releasing.wait()
            finished.set()

    peer.exchange = blocked
    operation = asyncio.create_task(
        adapter.call(owner, "fixture", "echo", {"text": "ok"})
    )
    await entered.wait()
    operation.cancel()
    await asyncio.sleep(0)
    operation.cancel()
    with pytest.raises(McpError, match="busy"):
        await adapter.call(owner, "fixture", "echo", {"text": "other"})
    assert not finished.is_set()
    releasing.set()
    with pytest.raises(asyncio.CancelledError):
        await operation
    assert finished.is_set() and adapter.active is None and peer.closed
    await adapter.close()


def test_host_configuration_cannot_register_side_effects_foreign_owners_or_loose_models():
    """Require explicit local read-only policy and immutable distinct owner-bound transports before discovery."""
    adapter, owner, peer, server = fixture()
    for changed in [
        replace(server, owner_id=uuid4()),
        replace(server, tools=(replace(server.tools[0], read_only=False),)),
        replace(server, identifier="https://attacker.example"),
    ]:
        with pytest.raises(McpError, match="invalid_configuration"):
            McpAdapter(owner, (changed,), profile="core")
    with pytest.raises(McpError, match="invalid_configuration"):
        McpAdapter(owner, (server, server), profile="core")
    with pytest.raises(McpError, match="invalid_configuration"):
        McpAdapter(owner, (server,), profile="unrestricted")


@pytest.mark.asyncio
async def test_close_with_suppressed_peer_cancellation_never_publishes_late_output():
    """Reject a complete response produced after shutdown even if the peer suppresses cancellation."""
    adapter, owner, peer, _ = fixture()
    await adapter.discover(owner, "fixture")
    entered = asyncio.Event()

    async def late(raw):
        """Return an otherwise valid result only after receiving the shutdown cancellation."""
        request = json.loads(raw)
        entered.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            pass
        return json.dumps(
            {
                "jsonrpc": "2.0",
                "id": request["id"],
                "result": {"content": [{"type": "text", "text": "late"}]},
            }
        ).encode()

    peer.exchange = late
    operation = asyncio.create_task(
        adapter.call(owner, "fixture", "echo", {"text": "ok"})
    )
    await entered.wait()
    await adapter.close()
    with pytest.raises(McpError, match="closed"):
        await operation
    assert peer.closed and adapter.active is None


@pytest.mark.asyncio
async def test_absent_result_type_is_complete_under_the_pinned_protocol_rule():
    """Apply the specification's missing-resultType compatibility rule without negotiating a legacy protocol."""
    adapter, owner, peer, _ = fixture()

    def without_type(method, response):
        """Omit only the optional-on-receive discriminant while retaining modern per-request version metadata."""
        response["result"].pop("resultType", None)
        return response

    peer.transform = without_type
    await adapter.discover(owner, "fixture")
    assert (
        await adapter.call(owner, "fixture", "echo", {"text": "complete"})
    ).content == ("complete",)
    await adapter.close()


@pytest.mark.parametrize("value", [float("nan"), float("inf"), True, -1])
def test_invalid_trusted_clock_never_creates_an_unbounded_client(value):
    """Fail closed before server contact when the host clock cannot supply a finite monotonic lifetime."""
    with pytest.raises(McpError, match="timeout"):
        fixture(clock=lambda: value)


@pytest.mark.asyncio
async def test_cleanup_failure_is_reported_after_other_owned_connections_are_closed(
    caplog,
):
    """Do not represent uncertain peer cleanup as a clean shutdown or leak its diagnostic content."""
    caplog.set_level("INFO")
    adapter, owner, peer, server = fixture()
    second = Peer()

    async def failed_close():
        """Inject a private transport shutdown failure while leaving the other connection observable."""
        raise RuntimeError("private-provider-credential")

    peer.close = failed_close
    adapter = McpAdapter(
        owner,
        (server, replace(server, identifier="second", transport=second)),
        profile="core",
    )
    with pytest.raises(McpError, match="invalid_response"):
        await adapter.close()
    assert second.closed and adapter.closed
    assert "private-provider-credential" not in caplog.text
