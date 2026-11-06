"""Admit only owner-bound host-allowlisted MCP operations with pinned per-request metadata and untrusted bounded text results."""

import asyncio
import hashlib
import json
import logging
import math
import re
import time
from dataclasses import dataclass
from uuid import UUID, uuid4

from pydantic import BaseModel, ValidationError

from src.application.services.web_fetch_tasks import finish_owned, spawn_owned
from src.application.services.workspace_requests import parse_workspace_json

logger = logging.getLogger(__name__)
PROTOCOL = "2026-07-28"
MAX_REQUESTS = 8
MAX_OUTPUT = 65536


class McpError(Exception):
    """Expose finite local MCP failures without peer messages, argument data or credentials."""

    def __init__(self, code):
        """Keep the integration error and audit vocabulary closed against peer-controlled text."""
        self.code = (
            code
            if code
            in {
                "invalid_configuration",
                "invalid_scope",
                "not_allowed",
                "protocol_mismatch",
                "invalid_response",
                "schema_drift",
                "peer_error",
                "busy",
                "closed",
                "limit",
                "timeout",
            }
            else "invalid_response"
        )
        super().__init__(self.code)
        logger.warning("mcp_rejected code=%s", self.code)


def canonical(value):
    """Serialize finite bounded JSON deterministically without interpreting remote schemas or links."""
    try:
        raw = json.dumps(
            value,
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        ).encode()
        parse_workspace_json(raw)
        return raw
    except Exception:
        raise McpError("invalid_response") from None


def schema_digest(model):
    """Bind a trusted strict local input model to the exact reviewed input schema."""
    if (
        not isinstance(model, type)
        or not issubclass(model, BaseModel)
        or model.model_config.get("strict") is not True
        or model.model_config.get("extra") != "forbid"
    ):
        raise McpError("invalid_configuration")
    return hashlib.sha256(canonical(model.model_json_schema())).hexdigest()


@dataclass(frozen=True, slots=True, repr=False)
class McpTool:
    """Freeze a trusted local argument validator and schema hash for one explicitly reviewed read-only operation."""

    name: str
    input_model: type[BaseModel]
    input_schema_sha256: str
    read_only: bool


@dataclass(frozen=True, slots=True, repr=False)
class McpServer:
    """Bind a host-chosen server identity and owned transport to one authenticated principal and finite tool set."""

    identifier: str
    owner_id: UUID
    transport: object
    tools: tuple[McpTool, ...]


@dataclass(frozen=True, slots=True, repr=False)
class McpTextResult:
    """Retain exact host/server/operation/request provenance on bounded untrusted peer text without action authority."""

    owner_id: UUID
    server_id: str
    operation: str
    arguments_sha256: str
    content: tuple[str, ...]
    content_trust: str = "untrusted"


class McpAdapter:
    """Own finite connections to host-registered servers while refusing discovered permission expansion or profile changes."""

    def __init__(self, owner, servers, *, profile, clock=time.monotonic):
        """Validate immutable host configuration without contacting, installing or discovering any server."""
        if (
            type(owner) is not UUID
            or type(profile) is not str
            or profile != "core"
            or type(servers) is not tuple
            or not 1 <= len(servers) <= 8
        ):
            raise McpError("invalid_configuration")
        identifiers, transports = set(), set()
        for server in servers:
            if (
                type(server) is not McpServer
                or server.owner_id != owner
                or type(server.identifier) is not str
                or re.fullmatch(r"[a-z][a-z0-9-]{0,63}", server.identifier) is None
                or server.identifier in identifiers
                or id(server.transport) in transports
                or type(server.tools) is not tuple
                or not 1 <= len(server.tools) <= 16
            ):
                raise McpError("invalid_configuration")
            names = set()
            for tool in server.tools:
                if (
                    type(tool) is not McpTool
                    or type(tool.name) is not str
                    or re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", tool.name) is None
                    or tool.name in names
                    or tool.read_only is not True
                    or schema_digest(tool.input_model) != tool.input_schema_sha256
                ):
                    raise McpError("invalid_configuration")
                names.add(tool.name)
            identifiers.add(server.identifier)
            transports.add(id(server.transport))
        self.owner, self.servers = owner, {row.identifier: row for row in servers}
        self.profile = profile
        self.clock = clock
        self.started = self.now()
        self.calls, self.output_bytes = 0, 0
        self.validated, self.active = set(), None
        self.closed = False
        logger.info("mcp_adapter_initialized server_count=%d", len(servers))

    def now(self):
        """Refuse invalid trusted clock samples rather than allowing an unbounded request lifetime."""
        value = self.clock()
        if type(value) not in (float, int) or not math.isfinite(value) or value < 0:
            raise McpError("timeout")
        return value

    def server(self, owner, server_id, profile):
        """Resolve only fixed owner/CORE/server admission, never a server-reported identity, URL or model permission."""
        if self.closed:
            raise McpError("closed")
        if (
            type(owner) is not UUID
            or owner != self.owner
            or type(profile) is not str
            or profile != "core"
        ):
            raise McpError("invalid_scope")
        if type(server_id) is not str or server_id not in self.servers:
            raise McpError("not_allowed")
        return self.servers[server_id]

    async def rpc(self, server, method, params):
        """Send one complete pinned JSON-RPC request with bounded output and joined timeout/cancellation."""
        if self.closed:
            raise McpError("closed")
        if (
            type(server) is not McpServer
            or self.servers.get(server.identifier) is not server
            or method not in {"server/discover", "tools/list", "tools/call"}
        ):
            raise McpError("not_allowed")
        self.calls += 1
        if (
            self.calls > MAX_REQUESTS
            or not 0 <= self.now() - self.started < 60
            or self.output_bytes >= MAX_OUTPUT
        ):
            raise McpError("limit")
        if self.active is not None:
            raise McpError("busy")
        request_id = str(uuid4())
        metadata = {
            "io.modelcontextprotocol/protocolVersion": PROTOCOL,
            "io.modelcontextprotocol/clientInfo": {
                "name": "local-assistant",
                "version": "0.1.0",
            },
            "io.modelcontextprotocol/clientCapabilities": {},
        }
        request = canonical(
            dict(
                jsonrpc="2.0",
                id=request_id,
                method=method,
                params=dict(params, _meta=metadata),
            )
        )
        task = spawn_owned(server.transport.exchange(request))
        self.active = task
        try:
            try:
                async with asyncio.timeout(5) as deadline:
                    raw = await asyncio.shield(task)
                if deadline.expired() or not 0 <= self.now() - self.started < 60:
                    raise McpError("timeout")
                if self.closed:
                    raise McpError("closed")
                if asyncio.current_task().cancelling() or task.cancelling():
                    raise asyncio.CancelledError()
            except (TimeoutError, asyncio.CancelledError):
                task.cancel()
                try:
                    await finish_owned(task)
                except BaseException:
                    logger.info(
                        "mcp_exchange_cancel_joined server=%s", server.identifier
                    )
                await server.transport.close()
                self.closed = True
                if asyncio.current_task().cancelling():
                    raise asyncio.CancelledError()
                raise McpError("timeout") from None
            if type(raw) is not bytes:
                raise McpError("invalid_response")
            self.output_bytes += len(raw)
            if self.output_bytes > MAX_OUTPUT:
                raise McpError("limit")
            value = parse_workspace_json(raw)
            if (
                value.get("jsonrpc") != "2.0"
                or value.get("id") != request_id
                or set(value)
                not in ({"jsonrpc", "id", "result"}, {"jsonrpc", "id", "error"})
            ):
                raise McpError("invalid_response")
            if "error" in value:
                error = value["error"]
                raise McpError(
                    "protocol_mismatch"
                    if type(error) is dict and error.get("code") == -32022
                    else "peer_error"
                )
            result = value["result"]
            if (
                type(result) is not dict
                or result.get("resultType", "complete") != "complete"
            ):
                raise McpError("invalid_response")
            logger.info(
                "mcp_request_complete server=%s method=%s", server.identifier, method
            )
            return result
        except (McpError, asyncio.CancelledError):
            self.validated.discard(server.identifier)
            raise
        except Exception:
            self.validated.discard(server.identifier)
            raise McpError("invalid_response") from None
        finally:
            self.active = None

    async def discover(self, owner, server_id, *, profile="core"):
        """Validate the pinned remote catalog subset without registering additional tools or adopting instructions/annotations."""
        server = self.server(owner, server_id, profile)
        self.validated.discard(server_id)
        discovery = await self.rpc(server, "server/discover", {})
        if (
            type(discovery.get("supportedVersions")) is not list
            or PROTOCOL not in discovery["supportedVersions"]
            or type(discovery.get("capabilities")) is not dict
            or type(discovery["capabilities"].get("tools")) is not dict
        ):
            raise McpError("protocol_mismatch")
        result = await self.rpc(server, "tools/list", {})
        tools = result.get("tools")
        if (
            type(tools) is not list
            or len(tools) > 32
            or result.get("nextCursor") is not None
        ):
            raise McpError("limit")
        seen, remote = set(), {}
        for tool in tools:
            if (
                type(tool) is not dict
                or type(tool.get("name")) is not str
                or tool["name"] in seen
            ):
                raise McpError("invalid_response")
            seen.add(tool["name"])
            remote[tool["name"]] = tool
        for tool in server.tools:
            found = remote.get(tool.name)
            if (
                found is None
                or hashlib.sha256(canonical(found.get("inputSchema"))).hexdigest()
                != tool.input_schema_sha256
            ):
                raise McpError("schema_drift")
        self.validated.add(server_id)
        logger.info(
            "mcp_catalog_narrowed server=%s admitted=%d discovered=%d",
            server_id,
            len(server.tools),
            len(tools),
        )
        return tuple(tool.name for tool in server.tools)

    async def call(self, owner, server_id, operation, arguments, *, profile="core"):
        """Invoke exactly one locally reviewed read-only tool and expose only complete untrusted text content."""
        server = self.server(owner, server_id, profile)
        if type(operation) is not str:
            raise McpError("not_allowed")
        tool = next((item for item in server.tools if item.name == operation), None)
        if tool is None or server_id not in self.validated:
            raise McpError("not_allowed")
        if schema_digest(tool.input_model) != tool.input_schema_sha256:
            raise McpError("schema_drift")
        try:
            if type(arguments) is not dict:
                raise ValueError()
            validated = tool.input_model.model_validate(arguments).model_dump(
                mode="json"
            )
            raw = canonical(validated)
        except (ValidationError, ValueError):
            raise McpError("not_allowed") from None
        result = await self.rpc(
            server, "tools/call", dict(name=operation, arguments=validated)
        )
        content = result.get("content")
        if (
            result.get("isError", False) is not False
            or type(content) is not list
            or not 1 <= len(content) <= 16
        ):
            raise McpError("peer_error")
        texts = []
        for part in content:
            if (
                type(part) is not dict
                or set(part) != {"type", "text"}
                or part["type"] != "text"
                or type(part["text"]) is not str
                or len(part["text"].encode()) > 8192
            ):
                raise McpError("invalid_response")
            texts.append(part["text"])
        return McpTextResult(
            owner, server_id, operation, hashlib.sha256(raw).hexdigest(), tuple(texts)
        )

    async def close(self):
        """Join connection teardown despite repeated host cancellation before reporting closure or propagating cancellation."""
        task = spawn_owned(self.finish_close())
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            try:
                await finish_owned(task)
            except BaseException:
                logger.info("mcp_cancelled_close_joined")
            raise

    async def finish_close(self):
        """Close admission and join every owned connection even if one peer's shutdown fails."""
        self.closed = True
        if self.active is not None:
            self.active.cancel()
            try:
                await finish_owned(self.active)
            except BaseException:
                logger.info("mcp_active_exchange_joined")
        outcomes = await asyncio.gather(
            *(server.transport.close() for server in self.servers.values()),
            return_exceptions=True,
        )
        logger.info(
            "mcp_adapter_closed servers=%d close_errors=%d",
            len(outcomes),
            sum(isinstance(value, BaseException) for value in outcomes),
        )
        if any(isinstance(value, BaseException) for value in outcomes):
            raise McpError("invalid_response")
