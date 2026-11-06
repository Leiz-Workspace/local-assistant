# D78 — Bounded plans and durable recovery

**Purpose:** Explain verified finite plan execution and recovery without recreating approval authority.

**Status:** Independent local recovery component VERIFIED; D70 listening/D74 product gates remain open. [ADR118](ADR/118-bounded-plans-and-durable-recovery.md).

A strict version1 plan admits at most8typed steps. Owner/workspace/CORE, schemas, effects and exact host tool revisions are bound outside model input. Fixed limits are120seconds including pause time,12total attempts,2per step and262144accepted output bytes. There is no automatic retry. Authorization runs before work and publication through D77; existing action services still own any write approval.

The private host-selected0700directory contains a0600local signing key and contiguous HMAC/hash-chained metadata records. Every attempt is charged and fsynced before invocation. Nonblocking filesystem locks prevent concurrent execution; exact latest references, raw-plan/catalog hashes, owner and lifetime are required for explicit resume. Partial/corrupt/gapped records fail closed. Checkpoints retain output hashes and counters, never raw arguments/results/approval tokens. Resumed results contain newly completed bodies only; old bodies are not reconstructed.

Pause finishes the admitted step and its durable receipt before stopping between steps. Explicit resume preserves original time/attempt/output budgets. Failed or crashed reads may be retried within those bounds; in-flight/failed writes are uncertain and cannot be automatically replayed. Action-specific authoritative receipts must be reconciled separately. If checkpoint publication fails before action, no action starts; if it fails after action, the prior in-flight record remains ambiguous. Closing joins durable publication and owned handlers; a handler closing its own runner cannot deadlock its parent or publish a late body.

**28new/246related tests PASS10.09s/0FAIL/0SKIP**, including actual subprocess crash exit17 after durable in-flight publication. Kernel locks release, the fresh process sees the charged attempt, explicit read recovery succeeds and write recovery is refused. Tests cover signing/key modes, stale/tampered chains, root-FD pinning, concurrent locks, expiry, pause, output limits, changed host revisions and injected publication failures. Ruff PASS. First three failures were a test-helper argument mismatch, retained and corrected; no guard was weakened.

Storage tests use disposable directories and fixture actions. No production checkpoint directory/key, deployment or write grant is created. No secure erase, hostile-host-clock or physical power-loss guarantee beyond file/directory fsync is claimed. Original661source bytes remain unchanged. [Source/log receipts](evidence/d78-bounded-plans-verification.json). D79 routing with existing explicit approvals is next.
