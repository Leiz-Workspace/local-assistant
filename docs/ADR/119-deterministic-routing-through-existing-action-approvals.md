# ADR 119 — Deterministic routing through existing action approvals

**Purpose:** Bind D79 tool selection to fixed existing services without allowing model arguments, plans or checkpoints to grant action permission.

**Date:** 2026-10-23. **Status:** Accepted for independent implementation/tests; production and manual gates remain open.

## Decision

Provide an optional host-owned CORE router for the five existing read-only workspace operations and exact `patch.apply`/`checks.run` actions. Proposals and explicit review decisions stay in existing services. The model envelope contains only name and typed arguments; action arguments contain only the existing proposal/job identifier. Approval identifiers are attached separately by the authenticated host for exact owner/workspace/action/target scope, never decoded from tool input or checkpoint state. Attaching an identifier does not approve it. Existing PatchService/CheckService still validate and consume their original exact reviewed artifact grants immediately before native execution.

Use D77's fixed authorization/publication barriers and metadata hooks, with original services owning native child cleanup and authoritative receipts. Consume the router's local attachment before an action attempt; do not automatically retry writes, reinterpret an uncertain result or reconstruct approvals on resume. A missing reference fails before invoking a service. Revoked/expired/wrong-action/wrong-target/pending references fail at the original action authority. The router cannot approve reviews, widen workspace roots, run arbitrary shell commands, add tools or alter models.

## Impact, priority and rollback

Existing D79/P1, depends on D35/D39–D44 and D77. One optional composition file with strict models, fixture integration tests and retained audit evidence. Risks are scope confusion, forged grants, changed arguments, cancellation after native commit and duplicated writes. Exact host identities, finite catalog, original one-shot grants, bounded output/attempts and sticky uncertain-write stop address these risks. No API route or production registration is added. Rollback closes/join the router and retains original service histories; service owners close dependencies afterwards. No existing source or deployment needs modification.
