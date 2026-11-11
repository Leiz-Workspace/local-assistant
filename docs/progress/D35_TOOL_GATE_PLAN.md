# D35 proposed deterministic read-tool gate

**Purpose:** Prepare bounded dispatch criteria during D34 full regression without advancing the current acceptance gate.

**Status:** Historical pre-implementation plan; D34 actual full/audit passed before D35 work. D35 now PASS within the internal scope:349 related PASS/0 SKIP and clean audit. See [implemented scope](D35_READ_TOOL_DISPATCH.md), [acceptance](../evidence/d35-tool-acceptance.json) and [ADR-053](../ADR/053-scoped-readonly-tool-dispatch.md). Proposed language below records the original plan; no model adoption.

P1 after D34, one dispatch milestone. Source capabilities, authentication and file/line fences remain D33/D34. Registry names are fixed workspace discover/inventory/read/search/symbols, with immutable authenticated owner/workspace scope supplied by application context. Model envelope proposes only operation name and arguments. Server assigns run/call UUIDs; no model-selected identity, root, workspace, profile, budget or arbitrary tool command.

Publish structural argument schemas from shared input definitions rather than a second drifting hand-written list. Runtime guards still enforce UTF-8 byte limits, cross-field line ranges, authorization, path scope and source freshness; JSON Schema alone is not an authorization mechanism. Changing an input contract requires checking D34 routes and future tool callers together.

Proposed composition is an internal server service owned by a future authenticated request, not a new public run-management API or persisted session store. The trusted application creates one run with typed owner/workspace UUIDs and closes/joins it at request completion. Untrusted calls supply only `name` and `arguments`; the fixed names are `workspace.discover`, `workspace.inventory`, `workspace.read`, `workspace.search` and `workspace.symbols`. Existing D34 request models should move to a shared contract module with compatibility imports in the routes; do not change their accepted JSON shapes or weaken native runtime validation. This small related refactor prevents schema drift and requires rerunning the D34 source/HTTP/startup tests.

Count every attempt, including malformed input, overlap, cancellation and repeats, before validation/admission. Serialize the complete result envelope to immutable UTF-8 bytes, count those actual bytes (including server-assigned IDs), and refuse over-budget output before it can reach a model caller. Retain the D34 snapshot through final validation and serialization; close/join it before dispatch returns. Charge elapsed time through cleanup, including failures. A timeout cannot be reported as joined until its owned task and file worker have actually stopped. Per-run close must reject new work and join an active call. Tests must cover both run admission and the shared workspace-service admission.

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
