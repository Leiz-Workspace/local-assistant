"""Exercise the actual pinned offline stdio MCP fixture and finite source/framing/child retirement boundaries."""

import asyncio
import hashlib
from pathlib import Path
from uuid import uuid4

import pytest
from test_mcp_adapter import EchoArguments

from src.application.services.mcp_adapter import (
    McpAdapter,
    McpError,
    McpServer,
    McpTool,
    schema_digest,
)
from src.infrastructure.mcp_stdio import PinnedPythonStdio


@pytest.mark.asyncio
async def test_actual_offline_namespace_discovery_echo_and_joined_exit(caplog):
    """Run actual JSON-RPC over stdio without project roots, credentials, network, server install or user data."""
    caplog.set_level("INFO")
    script = Path("tests/fixtures/mcp/echo_server.py")
    digest = hashlib.sha256(script.read_bytes()).hexdigest()
    transport = PinnedPythonStdio(script, digest)
    snapshot = Path(transport.directory.name)
    owner = uuid4()
    server = McpServer(
        "local-fixture",
        owner,
        transport,
        (McpTool("echo", EchoArguments, schema_digest(EchoArguments), True),),
    )
    adapter = McpAdapter(owner, (server,), profile="core")
    try:
        assert transport.process is None
        assert await adapter.discover(owner, "local-fixture") == ("echo",)
        result = await adapter.call(
            owner, "local-fixture", "echo", {"text": "neutral protocol fixture"}
        )
        assert (
            result.content == ("neutral protocol fixture",)
            and result.content_trust == "untrusted"
        )
        with pytest.raises(McpError, match="not_allowed"):
            await adapter.call(owner, "local-fixture", "grant_admin", {})
    finally:
        await adapter.close()
    assert transport.process.returncode == 0 and transport.reaped
    assert transport.stderr_task.done() and not snapshot.exists()
    assert "neutral protocol fixture" not in caplog.text
    command = transport.command()
    assert (
        "--unshare-all" in command
        and "--clearenv" in command
        and "--as=268435456" in command
    )


def test_changed_or_symlink_source_cannot_create_an_execution_snapshot(tmp_path):
    """Reject source substitution before creating or launching any protocol server."""
    script = tmp_path / "server.py"
    script.write_text('print("not approved")')
    with pytest.raises(McpError, match="invalid_configuration"):
        PinnedPythonStdio(script, "0" * 64)
    link = tmp_path / "link.py"
    link.symlink_to(script)
    with pytest.raises(McpError, match="invalid_configuration"):
        PinnedPythonStdio(link, hashlib.sha256(script.read_bytes()).hexdigest())


@pytest.mark.asyncio
async def test_server_bytes_are_snapshotted_before_host_path_replacement(tmp_path):
    """Execute only the approved snapshot even if its original host source changes after trust verification."""
    original = Path("tests/fixtures/mcp/echo_server.py").read_bytes()
    script = tmp_path / "server.py"
    script.write_bytes(original)
    transport = PinnedPythonStdio(script, hashlib.sha256(original).hexdigest())
    script.write_text('raise RuntimeError("changed untrusted source")')
    owner = uuid4()
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
    try:
        await adapter.discover(owner, "fixture")
        assert (
            await adapter.call(owner, "fixture", "echo", {"text": "unchanged snapshot"})
        ).content == ("unchanged snapshot",)
    finally:
        await adapter.close()
    assert transport.reaped and transport.process.returncode == 0


@pytest.mark.parametrize("mode", ["stdout", "stderr"])
@pytest.mark.asyncio
async def test_native_frame_or_diagnostic_flood_is_bounded_and_process_is_reaped(
    tmp_path, mode
):
    """Stop an actual overproducing sandbox without retaining unbounded peer data or a live server."""
    body = (
        '"""Emit an authored bounded-protocol failure for the isolated transport test."""\n'
        "import sys,time\nfor line in sys.stdin:\n"
        + (
            ' print("x" * 20000, flush=True)\n'
            if mode == "stdout"
            else ' sys.stderr.write("x" * 40000); sys.stderr.flush(); time.sleep(1); print("{}", flush=True)\n'
        )
    )
    script = tmp_path / "server.py"
    script.write_text(body)
    transport = PinnedPythonStdio(
        script, hashlib.sha256(script.read_bytes()).hexdigest()
    )
    snapshot = Path(transport.directory.name)
    try:
        with pytest.raises(Exception):
            await transport.exchange(b'{"jsonrpc":"2.0","id":"test","method":"test"}')
    finally:
        await transport.close()
    assert transport.reaped and transport.process.returncode is not None
    assert not snapshot.exists() and transport.stderr_task.done()


@pytest.mark.asyncio
async def test_actual_blocked_child_is_joined_after_repeated_cancellation(tmp_path):
    """Cancel a real waiting native child twice and verify process/drainer/snapshot retirement before return."""
    script = tmp_path / "server.py"
    script.write_text(
        '"""Block in an isolated authored cancellation fixture."""\nimport sys,time\nfor line in sys.stdin:\n sys.stderr.write("entered\\n");sys.stderr.flush();time.sleep(60)\n'
    )
    transport = PinnedPythonStdio(
        script, hashlib.sha256(script.read_bytes()).hexdigest()
    )
    snapshot = Path(transport.directory.name)
    operation = asyncio.create_task(
        transport.exchange(b'{"jsonrpc":"2.0","id":"test","method":"test"}')
    )
    async with asyncio.timeout(2):
        while transport.stderr_bytes == 0:
            await asyncio.sleep(0.001)
    operation.cancel()
    await asyncio.sleep(0)
    operation.cancel()
    with pytest.raises(asyncio.CancelledError):
        await operation
    assert transport.reaped and transport.process.returncode is not None
    assert not snapshot.exists() and transport.stderr_task.done()
