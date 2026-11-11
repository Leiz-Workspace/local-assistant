# D35 scoped read-only tool dispatch

**Purpose:** Describe the internal server dispatcher, shared schemas, measured acceptance and limits before CORE composition.

**Status:** PASS within the internal deterministic read-tool scope. [ADR-053](../ADR/053-scoped-readonly-tool-dispatch.md), [acceptance](../evidence/d35-tool-acceptance.json), [source freeze](../evidence/d35-tool-freeze.json).

The trusted application creates `WorkspaceToolRun(workspace_service, owner_uuid, workspace_uuid)` and must call its asynchronous `close()` at request completion. There is no public run-management endpoint, persisted run store, model call, automatic workspace registration or new configuration. Scope is immutable typed UUID data; run/call IDs are server-generated. Only the existing explicitly authorized catalog supplies roots.

Untrusted input is bounded strict UTF-8 JSON with exactly `name` and `arguments`. Registered names are `workspace.discover`, `workspace.inventory`, `workspace.read`, `workspace.search` and `workspace.symbols`. Example input:

```json
{"name":"workspace.read","arguments":{"path":"src/main.py","start_line":1,"end_line":20}}
```

`workspace_tool_schemas()` returns fresh JSON Schemas generated from the same strict argument classes imported by D34 HTTP routes. Existing HTTP body shapes remain unchanged. Native path/UTF-8/cross-field/source/auth guards also run; JSON Schema does not grant authority. Unknown tools, duplicate keys, nonfinite/deep/invalid-Unicode JSON, extras, coercions and ownership/root/model/command/budget overrides fail before root access.

Fixed server caps:8 attempts,60 seconds lifetime,20 seconds cumulative tool time,5 seconds per call,65536 bytes per result and262144 bytes per run. Every attempt counts, including malformed input, overlap, failures, cancellation and repeated calls. Complete serialized UTF-8 result envelopes include server IDs and are charged before final validation; failed/oversized results consume capacity and never become visible. No refund, retry, replay or fallback tool discovery. The exact last allowed byte is accepted; the next byte fails. A run that has reached its full output cap refuses subsequent calls.

One nonqueued admission per run composes with D34 shared service admission. Source contexts remain owned through bounded serialization, final native validation and cleanup. Time is charged through cleanup; expired results fail even after successful source work. Timeout/cancellation signals and joins the actual D34 worker before releasing admission. Closing a run rejects new work and cancels/joins an active call. Cooperative deadlines do not preempt uninterruptible kernel I/O. Audit contains server IDs, registered name, stable status, counters/bytes and elapsed time, never source/query/root or unknown tool spelling.

## Actual verification

Final related suite: **349 PASS/1.60s,0 SKIP,exit0**, including64 new D35 cases,164 D33/D34 workspace cases and121 prior auth/API/startup cases. Intermediate220/223 cases and121-case invocation are subsets, not extra totals. Full application collection:1849; **no fresh1849 full run claimed**. D34 actual1785 full PASS remains its historical checkpoint.

Native fixture tests cover all five tools, exact independent raw hashes/line quotes, owner/path/link/hidden denial, final source mutation, actual production output caps and joined file-thread cancellation/timeout/close. Disclosed controlled caps/clocks exercise exact byte/time/cleanup boundaries; these are correctness tests, not measured performance benchmarks. Malformed input cannot reach an explicitly forbidden root-open oracle. Schema identity/mutation and immutable registry/scope are checked. Final readonly audit verifies V006, empty inventories, original ACLs and protected hashes. Only old route imports change to share schemas; all other accepted baseline bytes remain intact.

D36 must separately compose the existing CORE and verify generated source-line citations and final source freshness after model delay. This dispatch gate is not a coding quality benchmark, semantic symbol resolver, general prompt-injection guarantee or execution/write sandbox. Disable its future caller and drain runs to roll back without data/model migration.
