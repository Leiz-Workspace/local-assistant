# D76 — Pinned owner-bound MCP allowlist adapter

**Purpose:** Document the verified independent MCP protocol/transport subset, fixed admission boundaries and actual native fixture observations.

**Status:** Local adapter/transport VERIFIED; independent preparation while D74 manual/product acceptance remains open. [ADR116](ADR/116-pinned-mcp-adapter-and-host-allowlists.md). No production MCP server/provider was registered, installed or contacted.

## Protocol and trust

The adapter pins2026-07-28, checked against the official [per-request metadata](https://modelcontextprotocol.io/specification/2026-07-28/basic/index), [versioning](https://modelcontextprotocol.io/specification/2026-07-28/basic/versioning) and [tools](https://modelcontextprotocol.io/specification/2026-07-28/server/tools) specifications. Every request declares the pinned version and empty client capabilities. Only discovery, list and call are implemented. Unsupported versions fail without automatic legacy handshake, retry, callback, roots, sampling or elicitation. Missing `resultType` is treated as complete under the receive-side compatibility rule; other result types are rejected.

Construction requires a trusted owner and explicit CORE profile, plus immutable host server IDs/owned transports/read-only tools/local strict argument models/exact schema hashes. Server display names, instructions, descriptions and read-only annotations never determine authority. Discovery admits only that pinned subset; added tools do not register themselves. Duplicate names, schema drift, wrong identities, unknown server/operation, unrestricted profile, extra arguments and nontext results fail closed. A failed new discovery revokes the old admitted set.

Results retain owner, host server ID, operation and argument hash and are always untrusted. The adapter follows no resource URL, schema reference, icon or credential prompt. It exposes no mutation/approval/server-install operation. RPC budgets are8requests/60seconds/5seconds per request and64KiB total received, with16KiB framed messages and one active exchange. Incomplete/paginated catalogues are currently rejected rather than partially admitted.

## Constrained stdio transport

The host supplies an exact-hash local standard-library Python source. Its verified bytes are snapshotted privately before launch, so later host-path replacement cannot change executed code. A fresh offline read-only bwrap namespace exposes only stdlib and that script: no project root, ambient credentials, network or GPU. Limits:256MiBaddress space,10CPU seconds,16MiBtmpfs,32FDs,1MiBfile size,16KiBframes and32KiBstderr counting/discard. This is not an arbitrary command/Node/dependency installer or generic HTTP/OAuth transport.

All child exchanges and shutdown retain ownership through cancellation and drainers are joined. Oversized frames/diagnostics and repeated cancellation retire the real sandbox; untrusted stderr text is not logged or stored. Adapter cleanup attempts every owned connection and reports a cleanup failure instead of claiming a clean close. The host must await close on the adapter it owns.

## Actual verification

**214related tests PASS1.50s/0FAIL/0SKIP**, including27new MCP controls plus existing skill/workspace/approval/workflow tests. Actual native fixtures cover discovery/call, exact source snapshot despite original-path mutation, stdout/stderr floods, blocked-child repeated cancellation, child/drainer retirement and source-snapshot deletion. Other controls cover modern/legacy metadata, peer requests/IDs, unlisted tools, schema drift, malformed arguments/results, output/attempt/time budgets, foreign owner/profile, suppressed cancellation/late results and cleanup uncertainty/redaction.

The first native pair failed because the fixture schema omitted the strict local model's description. Retained first log; corrected only the authored fixture's exact schema without relaxing the pin/guard. A separate actual namespace demo then completed3RPCs, admitted only `echo`, rejected unsolicited `grant_admin`, returned the exact neutral expected string, exited0/reaped and removed its source snapshot. All connections are local inert fixtures; no user content or credentials transmitted. [Verification/source/log/demo receipt](evidence/d76-mcp-adapter-verification.json).

## Remaining integration scope

Production registration stays empty. HTTP/OAuth, legacy versions, pagination and dependency-bearing server runtimes are unscheduled compatibility candidates, not automatically enabled fallbacks: priority P2 only if an actual owner-selected server needs them; dependencies include its reviewed transport/identity/operation schemas; effort one bounded compatibility milestone; risks include credentials, origin/session handling, callbacks and unbounded discovery. D77's independent trusted hooks/error/stop controls are next. No model/default/service/database/skill-permission changes and no D74/release acceptance from this component.
