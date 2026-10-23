# ADR 116 — Pinned MCP adapter and host-owned allowlists

**Purpose:** Implement D76 independently with bounded protocol transport and trusted server/operation admission, without installing servers or accepting discovered permissions.

**Date:** 2026-10-23. **Status:** Accepted for independent implementation/tests; D74 manual/product gate remains open.

## Protocol and scope

Pin MCP2026-07-28 after checking the official [versioning](https://modelcontextprotocol.io/specification/2026-07-28/basic/versioning), [request metadata](https://modelcontextprotocol.io/specification/2026-07-28/basic/index), [discovery](https://modelcontextprotocol.io/specification/2026-07-28/server/discover), [tools](https://modelcontextprotocol.io/specification/2026-07-28/server/tools) and [stdio](https://modelcontextprotocol.io/specification/2026-07-28/basic/transports/stdio) specifications. Use per-request version/client-capability metadata, `server/discover`, `tools/list`, `tools/call`; do not implement the earlier `initialize` handshake or silently fall back to it. A version mismatch is a finite failure requiring a separately reviewed compatibility change. This initial subset supports text results and complete synchronous requests only; no sampling, roots, elicitation, subscriptions, extension/task negotiation, external references, HTTP/OAuth or URL following.

Host code registers immutable owner-bound server IDs, owned transport instances and exact allowed operation/input-model/schema digests before discovery. Initially only host-asserted read-only operations are admissible. Remote server names/descriptions/instructions/annotations are untrusted metadata, never permission or identity evidence. Discovery validates the pinned subset and excludes unlisted tools; schema drift/duplicate names/incomplete catalogues fail closed. Argument validation uses trusted strict local Pydantic models, not execution or network resolution of remote schemas.

Require bound owner and CORE profile before calls. Keep exact source/server/operation/request-hash provenance on untrusted text results. Limit attempts, bytes, concurrent admission and request/run time. Do not automatically retry a server error, run a client callback, promote a discovered capability or treat a read-only hint as approval. Side-effecting MCP operations remain unsupported until the explicit action-approval layer is integrated and reviewed.

## Transport and verification

The adapter accepts only trusted preconstructed transports. Provide a bounded stdio transport for exact-hash local standard-library Python servers, snapshotting approved source bytes into an owned private directory before execution. Run offline in a read-only bwrap namespace with no project roots, credentials, network or GPU, finite CPU/address-space/tmpfs/output limits. No arbitrary model-provided command, path, URL or package; no installation/download. This constrained transport is not claimed to support arbitrary Node/dependency-bearing MCP servers. Other trusted transports need their own bounded implementations/reviews.

A real authored fixture server verifies the wire protocol in that namespace. Test hostile discovery/schema/version/ID/result/callback output, wrong owner/profile/server/tool, invalid arguments, timeout/cancel/close and process retirement. Logs contain finite server/method/status metadata, not arguments or output text.

## Priority, risk and rollback

Existing D76/P1; one adapter/transport validation milestone, depending on fixed local schemas, kernel isolation and host-reviewed server configuration. Risks include confused identities, remote schema/annotation trust, unexpected protocol revisions, unbounded stdio, dangling children and illicit model/server callbacks. Production server registration is empty unless a host explicitly supplies it; no external server account or live data recipient is needed for the fixture test. Rollback joins owned connections/processes and retains first evidence, leaving existing services/models/data/skills untouched.
