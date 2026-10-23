# ADR 117 — Trusted tool hooks and stop ownership

**Purpose:** Generalize finite pre/post/error/stop audit control for D77 without exposing executable hooks or bypassing existing action approvals.

**Date:** 2026-10-23. **Status:** Accepted for independent implementation/tests; unresolved voice/release gates remain open.

## Decision

Use fixed built-in metadata hooks, not scripts/functions supplied by manifests, model output or MCP servers. A trusted host constructs immutable calls bound to owner/workspace/run/CORE/tool/request digest. A host-owned finite tool/effect map and authorization function remain separate from hooks. Recheck authorization before invocation and before publication; hook return values grant nothing. Mutation handlers still enforce the original patch/check approval layer themselves at the action boundary.

The guard owns one nonqueued task including authorization, invocation and post-check. Record finite before/after events, complete only after joined cleanup, and never log argument/output/prompt/approval-token contents. Eight attempted calls and bounded call timeout/output limits apply. Stop is an explicit owner/run-bound signal that cancels only the owned task; close/caller cancellation join actual dependency cleanup. A dependency must itself retain its native child ownership, as the accepted workspace/MCP adapters do. A cancelled task is not proof of native retirement without that adapter contract.

If a write invocation has started and then errors, times out, stops, loses authorization or returns malformed output, mark its audit outcome uncertain. Do not claim rollback or automatically retry. Existing action receipts remain authoritative. Read-only failures can safely withhold output. No hook callback, return flag or stopped-run restart grants an approval or new scope.

## Priority, dependencies and rollback

Existing D77/P1, one generalized control validation milestone; depends on explicit host policy/adapters and existing source/action approvals. Risks include stale late results, pre-hook privilege injection, unjoined cancellation and duplicate effects after ambiguous write errors. Test denial/immutable scope, revoked permissions after work, all terminal outcomes, repeated cancellation, stop ownership and capacity/time/output bounds with real existing read-only adapters where applicable. No database/model/config/server installation. Rollback closes/join guards and retains events; existing workflow controls remain unchanged.
