# ADR-053: Scoped deterministic read-only tool dispatch

**Purpose:** Prepare D35 schemas, per-run tool budgets and timeout ownership after D34 source-read acceptance.

**Date:** 2026-10-20 (Asia/Ho_Chi_Minh)

**Status:** Accepted design after D34 actual1785 full PASS/0 SKIP/exit0 and clean audit (`78542b0`). D35 implemented/accepted:349 related PASS/1.60s,0 SKIP,exit0, including64 new cases, plus clean final audit. [Acceptance](../evidence/d35-tool-acceptance.json); no new full1849 claim.

## Priority and dependencies

P1, depends on actual D34 acceptance and D33 kernel workspace boundary; estimated one dispatch milestone. Risks: model-generated tool/argument injection, caller-supplied scope/budget widening, invalid-call loops, duplicate calls, serialized output amplification and timeouts releasing resources before underlying file work joins. No model change, shell/git execution, write capability, package install or external tool discovery is proposed.

## Proposed decision

Create a finite immutable registry of deterministic workspace discovery/inventory/read/literal-search/lexical-symbol operations. Publish strict JSON schemas from the same validation contract used by dispatch. Bind one authenticated owner/workspace and server policy to a run before any untrusted model call. Tool arguments cannot choose another owner/root/workspace, model, regex engine, command or budget. No plugin/MCP/dynamic-tool discovery is implicit.

Accept bounded strict UTF-8 JSON tool envelopes only, reject duplicate/nonfinite/extra/mistyped fields and unknown names before root access. Scope is supplied by application context, not the model envelope. Each run tracks bounded call attempts, server-assigned run/call UUIDs, cumulative output bytes and monotonic deadlines; attempted invalid calls consume an attempt. The model never chooses scope, run/call IDs or policy. Repeated read calls consume the same budget; there is no persisted idempotency or automatic replay guarantee. No automatic retries or fallback tools. One nonqueued dispatcher operation per run; cancelled/failed work does not refund calls or extend the deadline.

Dispatch only through accepted WorkspaceService. Retain its source context until actual final root/inode/hash validation and bounded output serialization complete. Reuse owned stop events and joined cancellation so timeout cannot leave a live file worker while a result is returned. Deadlines remain cooperative for uninterruptible local I/O, as stated in D34; do not invent a hard kernel preemption guarantee. Subsequent command execution requires D42 isolation rather than this read-only dispatcher.

Proposed conservative server caps:8 attempts/run,60-second run lifetime,20-second cumulative tool time,5-second call wall,64KiB/call and256KiB cumulative returned data. The longer lifetime permits model reasoning between calls while keeping actual tool time bounded. Tool outputs are deliberately narrower than the human-facing D34 API; later CORE context budgeting remains independent and rejects overflow without truncation. Constants must be recorded before actual gate execution, with boundary/clock/cancel/overlap/native-owner cases. Output source text remains untrusted. Audit only run/call UUID, registered operation, count/bytes, latency and stable outcomes; no source/query/root/credential values.

D35 is a server-side dispatcher contract; D36 will separately compose the existing CORE into source-cited explanations and must test actual model behavior. There is no permission to follow commands printed by source files, reveal unrelated directories or adopt a coding specialist.

## Rollback and acceptance conditions

Remove/disable dispatcher composition without changing D34 source routes, source files, data or models. Before accepting D35, test actual authorized native reads and scope denial, malformed envelopes/schema drift, attempt/output/deadline boundaries, repeated cancellation and joined cleanup. Preserve every observed failure and distinguish controlled time/model inputs from actual filesystem behavior. D34 full regression/source/audit must finish first.

## Implementation scope

Internal request-owned `WorkspaceToolRun` only; no new public endpoint/session store or model call. Shared argument classes preserve D34 HTTP shapes through compatibility imports. Native fixed output limits and file-thread joins are exercised; synthetic clock/cap boundaries disclosed separately. [Guide](../D35_READ_TOOL_DISPATCH.md). Actual D34 full completed before implementation. D36 owns subsequent CORE/citation composition.
