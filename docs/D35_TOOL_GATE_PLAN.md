# D35 proposed deterministic read-tool gate

**Purpose:** Prepare bounded dispatch criteria during D34 full regression without advancing the current acceptance gate.

**Status:** Draft; depends on actual D34 PASS and [ADR-053](ADR/053-scoped-readonly-tool-dispatch.md). No D35 implementation or model adoption yet.

P1 after D34, one dispatch milestone. Source capabilities, authentication and file/line fences remain D33/D34. Registry names are fixed workspace discover/inventory/read/search/symbols, with immutable authenticated owner/workspace scope supplied by application context. Model envelope proposes only operation name and arguments. Server assigns run/call UUIDs; no model-selected identity, root, workspace, profile, budget or arbitrary tool command.

Publish structural argument schemas from shared input definitions rather than a second drifting hand-written list. Runtime guards still enforce UTF-8 byte limits, cross-field line ranges, authorization, path scope and source freshness; JSON Schema alone is not an authorization mechanism. Changing an input contract requires checking D34 routes and future tool callers together.

The proposed caps are8 attempts,60-second lifetime,20-second cumulative tool time,5-second call wall,64KiB/call and256KiB/run output. A request cannot override them. Invalid/repeated/failed/cancelled calls consume attempts and never refund time/output capacity or extend deadlines. No retries, fallback tool discovery, shell, git, writes or model call are implied.

| Gate | Actual or controlled evidence required |
|---|---|
| Source success | Actual authorized native read/search, independent raw hash/line/quote oracle; no model required |
| Scope | Fixed owner/workspace; foreign root not opened and no hidden/outside source exposed |
| Input/schema | Unknown tool, duplicate/nonfinite/extra/mistyped fields, forbidden ownership/command/budget keys rejected before file access |
| Attempts | Exact last permitted call succeeds; next attempt fails; invalid calls also exhaust the cap |
| Output | Exact per-call/cumulative boundary; over-budget payload never becomes visible or enters later model context |
| Time | Controlled monotonic clock for exact limits plus actual cooperative worker cancellation/join; distinguish synthetic clock from measured performance |
| Overlap | Nonqueued per-run admission, shared source-service admission, no parallel bypass |
| Cancellation | Normal, repeated and completed-result ownership race; no live thread or source handle after the dispatch task ends |
| Audit | Stable registered name/status, server IDs and counters only; no root/query/source/credential values |
| Compatibility | D34 API contracts/source fences and prior runtime/model/config/migration bytes revalidated as appropriate |

D36 will separately compose existing CORE and validate generated source citations. D35 test success alone is not an actual model coding benchmark, a general prompt-injection guarantee or an execution sandbox. CLI/UI approval, patches, git rollback and isolated commands remain D39–D45.
