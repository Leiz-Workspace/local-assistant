# ADR 118 — Bounded plans and durable recovery

**Purpose:** Define D78's finite plan execution, explicit retries and crash-safe checkpoint/resume without recovering approvals or duplicating uncertain writes.

**Date:** 2026-10-23. **Status:** Accepted for independent implementation/tests; manual/product/release gates remain open.

## Decision

Admit a strict bounded version1plan with at most8fixed typed steps, no model-supplied owners/profiles/budgets/hooks/commands/endpoints. Trusted host tool contracts specify validators and read/write effects. Freeze exact raw plan and catalog hashes. Run through D77's owner/CORE/permission/cleanup guard. Bound total attempts12, per-step attempts2, elapsed lifetime120seconds and cumulative output262144bytes; budgets survive resume and elapsed pause time counts. There is no automatic retry. Explicit owner resume can retry a failed/in-flight read within those original bounds, never an uncertain write. Every write still requires its original action-specific approval at execution, not a recovered checkpoint flag.

Persist only source/scope/status/attempt/output-digest metadata, not arguments, output bodies, prompts or approval tokens. Before invoking a step, exclusively append/fsync a signed in-flight checkpoint. After complete guarded execution, append/fsync its terminal metadata. Use an owner-private fixed host directory and local32byte signing key, never model paths. This is a new isolated application checkpoint capability, not a Vault policy/key change or a migration of existing stores. Production storage remains unconfigured; actual tests use disposable directories/keys only.

Checkpoint files form a contiguous signed hash chain. Resume requires the latest exact reference, raw plan/catalog match, owner/workspace match, valid absolute lifetime and a nonblocking per-run filesystem lock. Partial/corrupt/unknown chains fail closed instead of falling back to an older version. Durable in-flight write state blocks recovery until authoritative action receipts are reconciled separately. A crash releases the kernel lock; it does not refund attempts, extend deadlines, restore skill/approval authority or authorize an operation.

## Validation and limits

Existing D78/P1, one planner/store/crash-recovery milestone. Dependencies: fixed tool schemas/effects, D77 joined handlers, private filesystem and fresh current authorization on every execution/resume. Risks include stale-checkpoint replay, concurrent resumers, lost action receipts, wall-clock rollback, disk-full after a write and signing-key disclosure. Store paths are host-only; the key is local0600inside0700storage and never logged/committed. Directory-FD relative I/O and no-follow regular-file checks constrain publication. If durable checkpointing fails, do not start an unrecorded action; retain in-flight ambiguity after an already invoked write. No secure erase or hardware power-loss guarantee is claimed beyond file/directory fsync.

Validate strict plans, budgets, stale/tampered/cross-owner snapshots, explicit resume, same-instance/new-process recovery, nonblocking locks, raw-input redaction and uncertain-write refusal with disposable actions. No actual production package/model/server/DB/approval store is changed. Rollback closes/join active guards and retains signed history; it never erases first evidence or automatically repeats an action.
