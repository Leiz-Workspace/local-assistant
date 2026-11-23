# ADR 182 — Opt-in signed harness metadata history

**Purpose:** Preserve bounded run metadata across an owned harness restart without restoring task execution, skill trust, approvals or private prompt/result text.

**Date:** 2026-11-10. **Status:** Accepted for staged implementation under the owner's continuation request. Existing databases, model decisions and product/release gates remain unchanged.

## Decision

Add an optional owner-private filesystem store selected only by the host CLI `serve --state-dir PATH` or `ASSISTANT_HARNESS_STATE_DIR`. Default behavior stays in-memory. Use a pinned 0700 directory, 0600 single-link regular files, a local signing key and an exclusive process lock; fail startup on an invalid directory, record or competing process. No database migration, Vault lookup, arbitrary model/user file path or automatic production configuration.

Persist a versioned finite snapshot containing only run/owner/workspace identities, state/event sequence, request hash, result/context hashes and a finite error code. Never store task text, evidence, model answer, skill instructions, install/review/approval/session tokens or executable plan arguments. Per-owner/global run caps remain enforced. Publish with exclusive temporary file, file fsync, atomic rename and directory fsync; never treat an unpublished temporary file as a completed record.

On startup verify every bounded record signature/schema/identity. Retain terminal metadata with `archive_only=true`, `result_available=false`. Convert created/running snapshots to `interrupted` and record that transition; do not resume, refund budgets, recover skills, restore approvals or replay any operation. Historical inspection and terminal deletion remain owner-scoped through the existing API/CLI. This does not synchronize browser history with PostgreSQL Conversation.

Write the created record before scheduling a task and the running record before reading sources or invoking inference. If persistence fails, stop new admissions and do not silently fall back to memory. A completed model output whose terminal record cannot be published must not be exposed as a persisted success. Mark the in-memory failure explicitly; the last durable active snapshot becomes interrupted on a later successful recovery. Do not retry a failed metadata publication automatically.

## Alternatives and limits

Reusing the plan checkpoint format would blur metadata history with execution recovery. Modifying PostgreSQL would expand the scope into migrations/shared state. Keep this isolated snapshot store separate and preserve earlier checkpoint code.

Signatures detect malformed/tampered bytes but are not an anti-rollback ledger or protection against an attacker controlling the same OS user/signing key. Filesystem fsync is not a guarantee about every storage device's power-loss behavior. Snapshot history is informational, never authority. Raw results, skill catalog persistence, durable resume, chat Conversation synchronization and generation artifact durability remain separate tasks.

## Acceptance and rollback

Test owner isolation, terminal and active recovery, no secret/raw-text retention, signature/unknown-field/truncation/path/link/permission failures, competing-process exclusion, interrupted writes and failure before inference. Prove actual separate-process restart with no model call before recovering history. Run related harness/auth/skill/context tests; report software/history acceptance separately from specialist quality.

Stop/join the owned service, keep its state directory for audit, then omit the new state-dir option to return to the original memory-only entrypoint. Do not delete or rewrite any existing data store, revive grants or count recovered metadata as a completed task execution.
