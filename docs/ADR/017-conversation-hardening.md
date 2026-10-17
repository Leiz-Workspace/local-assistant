# ADR-017 — Conversation leases, intact context and failure fencing

**Purpose:** Record the consistency and context decisions implemented for D15-T06 and the release gates still open.

**Date:** 2026-10-17 (Asia/Ho_Chi_Minh)
**Status:** Accepted for localhost implementation; D15-T06 remains PARTIAL.

## Problem

T05 proves persistent HTTP chat but does not prove transaction races, cancelled requests, process death or context boundaries. The existing manager read the first 500 messages and sliced the last N individual messages; this could reject a new turn in a long conversation or split a previous pair. A dead worker could leave a pending run indefinitely. PostgreSQL is shared with other applications and V001 has no owner identity.

## Decision

### Leased inference with explicit interruption

Each manager instance receives a random owner UUID. Reservation stores `lease_owner` and `lease_expires_at` in the existing inference-run JSONB metadata. Defaults are 120 seconds for the lease and 30 seconds for heartbeat. Database `clock_timestamp()` supplies lease time, avoiding clock differences between workers. No DDL/migration or service changes are required.

Heartbeat uses short independent transactions and sleeps outside a DB session. If renewal fails or ownership expires, cancel the model coroutine and reject the result. Finalization locks the active conversation first, then locks and verifies pending status, owner and unexpired lease before inserting the assistant. This preserves the existing conversation-then-run lock order. Late results cannot complete an interrupted run.

On request cancellation, persist `interrupted` in a separate transaction when possible; if the process is killed before cleanup, the expiry path handles its owned reservation. Failure persists `failed`, and reservation/finalization writes remain atomic. Cleanup failure is logged with IDs/error category, never prompt/credential content; expiry remains the fallback.

Recovery is lazy on the next send, or an explicit `recover_expired(conversation_id)` call. It locks that conversation and commits recovery before attempting reservation/replay so a 409 cannot roll the recovery back. Only a leased pending run whose expiry has elapsed is interrupted. A still-live lease is preserved. Historical pending runs with no owner/lease are deliberately not inferred dead; operators must verify their worker is gone before manual repair. No startup sweep of every pending row and no automatic replay are allowed. Failed/interrupted/same-key requests keep deterministic 409 semantics.

A deployment rolling back to pre-lease code must first drain all active inference. Old code does not understand lease fencing; running old/new writers simultaneously is unsupported. A DB pause longer than the lease can interrupt healthy work; reject the late answer and let the caller inspect persisted state rather than claiming success.

### Intact, token-aware context

Read the latest bounded non-system messages and all system instructions, ordered by sequence, instead of the first history page. Select complete adjacent user/assistant pairs plus the current user message; omit earlier incomplete user turns. The transcript is never deleted or text-truncated. The default message limit remains 24 for bounded inference input; system instructions are retained independently of that limit.

The persistent inference adapter resolves Auto once using the established router. It uses the existing gateway chat template/tokenizer and preset budget policy, dropping the oldest complete pair until the chosen preset fits. It rejects impossible output settings without pruning history, and returns controlled 422 if system/current input alone exceeds the budget. The gateway rechecks the final input before generation. Stateless routes, preset thresholds and gateway implementation remain unchanged.

The adapter intentionally reuses gateway context/Auto helper methods, including private methods, to avoid duplicating the validated runtime policy. Unit tests pin this interaction. A future public context-planning port can remove this coupling without changing the HTTP contract; full dependency inversion is not claimed here.

### Operational boundaries

Continue the one-worker, direct-loopback deployment from ADR-016. These changes demonstrate cross-connection consistency and per-run recovery, not complete multiworker operation or user authorization. Logs carry operation/run/conversation IDs, selected presets, token/message counts and stable codes; no message bodies, reasoning traces, DSNs or secrets.

Pool acceptance instrumentation records checked-out connections while inference is blocked, including 12 simultaneous inferences against the existing 5+5 capacity. This is a test probe; production pool telemetry/export and long-running load SLOs remain open.

## Required validation

- Two managers race reservation through distinct `pg_backend_pid()` connections, with one inference and deterministic 409/replay.
- Cancelled requests and a SIGKILLed disposable worker never produce a completed assistant; expiry recovery fences late owners.
- Heartbeat extends a live lease; losing renewal stops inference; unowned legacy runs remain unchanged.
- Inject failure before reservation commit and after assistant insertion but before completion update; verify rollback.
- Reject length/model/preset mismatch; exercise the actual CORE tokenizer on an overflowing current message.
- Keep system instructions and recent pairs after more than 500 historical messages.
- Real pending update/archive/delete requests are rejected; full existing HTTP/runtime/CORE regression remains green.

Exact command results belong in `dev_log/dev_log.md`, not an assumed PASS here.

## Gates that remain open

Owner-based authentication/authorization requires an explicit identity contract, schema migration, backfill policy for existing conversations and negative access tests. Until those exist, external/proxy exposure stays prohibited; local peer rejection does not prove user-to-user isolation.

Shared PostgreSQL restart requires a maintenance plan: enumerate dependent consumers, create a protected backup, prove restore in an isolated target, record recovery/rollback commands and only then schedule the shared restart. This session does not restart the shared DB, create another service, or claim an untested dump is a verified backup.

Do not mark D15-T06 or Day 15 PASS until these gates and the remaining operational telemetry/review checks have evidence.
