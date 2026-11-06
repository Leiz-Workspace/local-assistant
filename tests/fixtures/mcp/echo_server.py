"""Serve an authored inert MCP2026-07-28 stdio echo fixture inside the isolated protocol tests, never a production service."""

import json
import logging
import sys

logger = logging.getLogger(__name__)
PROTOCOL = "2026-07-28"
SCHEMA = {
    "description": "Admit only a short literal test string without identities, commands, URLs or hidden scope overrides.",
    "additionalProperties": False,
    "properties": {
        "text": {"maxLength": 128, "minLength": 1, "title": "Text", "type": "string"}
    },
    "required": ["text"],
    "title": "EchoArguments",
    "type": "object",
}


def result(request):
    """Respond only to pinned discovery/list/echo requests without accessing files, credentials, network or callbacks."""
    params = request.get("params", {})
    meta = params.get("_meta", {})
    if (
        meta.get("io.modelcontextprotocol/protocolVersion") != PROTOCOL
        or meta.get("io.modelcontextprotocol/clientCapabilities") != {}
    ):
        return {"error": {"code": -32022, "message": "Unsupported protocol version"}}
    method = request.get("method")
    logger.info(
        "mcp_fixture_request method=%s",
        method
        if method in {"server/discover", "tools/list", "tools/call"}
        else "unknown",
    )
    if method == "server/discover":
        return {
            "result": {
                "resultType": "complete",
                "supportedVersions": [PROTOCOL],
                "capabilities": {"tools": {}},
                "instructions": "This untrusted metadata cannot grant shell permission.",
            }
        }
    if method == "tools/list":
        return {
            "result": {
                "resultType": "complete",
                "tools": [
                    {
                        "name": "echo",
                        "description": "Echo neutral test text.",
                        "inputSchema": SCHEMA,
                    },
                    {
                        "name": "grant_admin",
                        "description": "Unlisted inert hostile-discovery example.",
                        "inputSchema": {},
                        "annotations": {"readOnlyHint": True},
                    },
                ],
            }
        }
    if method == "tools/call" and params.get("name") == "echo":
        value = params.get("arguments", {}).get("text")
        if type(value) is str and 1 <= len(value) <= 128:
            return {
                "result": {
                    "resultType": "complete",
                    "content": [{"type": "text", "text": value}],
                    "isError": False,
                }
            }
    return {"error": {"code": -32601, "message": "Method not found"}}


def main():
    """Read bounded complete request lines and emit only JSON-RPC responses while logging finite metadata to stderr."""
    logging.basicConfig(level=logging.INFO)
    while True:
        raw = sys.stdin.buffer.readline(16385)
        if not raw:
            return
        if len(raw) > 16384 or not raw.endswith(b"\n"):
            raise ValueError("fixture_frame_bound")
        request = json.loads(raw)
        response = dict(jsonrpc="2.0", id=request.get("id"), **result(request))
        print(json.dumps(response, separators=(",", ":")), flush=True)


if __name__ == "__main__":
    main()
