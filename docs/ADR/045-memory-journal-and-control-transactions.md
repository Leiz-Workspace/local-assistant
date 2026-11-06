# ADR-045 — Additive memory journal and owner control transactions

**Purpose:** Implement D30-T01 storage and consent controls from accepted D29 contracts before enabling memory APIs or extraction.

**Date:** 2026-10-19
**Status:** Accepted for local T01 repository/schema after reviewed V005 rollout/backup/restore and actual tests; T02/T03 and D30 final acceptance remain pending.

## Scope and dependencies

D29 commit `ab6cff9` accepts strict classes/consent/provenance and actual temporary PostgreSQL constraints, not a runtime. D30-T01 adds three tables and an unused owner-scoped repository. D30-T02 adds default-off authenticated APIs; T03 separately opt-in source-verified CORE extraction/retention. D30 remains open until all three pass; D31 privacy/export/propagation is later.

P1; dependencies ADR-018/044, existing PostgreSQL/migrator/runtime identities and verified D28 source lifecycle. Effort at least three implementation tasks within D30, extend numbering if acceptance needs more. Risks: implicit consent, concurrent disable/revoke/capture, default privilege inheritance, quota/retention leaks, source deletion and migration startup incompatibility. No model/download/precision/routing change or new service/credential.

## Journal decision

V005 copies the reviewed proposed settings/receipts/records schema and adds owner/expiry indexes. Preserve V001–004 and all existing tables/rows/grants. Explicitly revoke inherited app privileges on only new relations before granting SELECT/INSERT/DELETE and narrow mutable-column UPDATE. Receipt owner/class/scope/epoch/expiry and record owner/class/scope/receipt/creation identity remain immutable. No application DDL/TEMP/TRUNCATE privileges are introduced. Downgrade refuses any memory/settings/receipt row; rollback normally disables/drains the feature and retains additive schema for forward repair.

Review offline SQL and exact grant/downgrade guards, take a fresh private cluster/app backup, prove isolated restore on the same existing instance, then recheck quiet source fingerprints before applying through the existing Vault migrator. Never restore over the app or restart shared services for this migration. Verify old rows/owners/ACLs afterward and prove a new post-migration restore. Add0005 only to reviewed file/ingestion compatibility guards; unknown revisions and immutable ingestion privilege checks remain enforced. Those necessary guard changes require related tests, not broad rewrites of accepted source behavior.

## Transactions

All mutations lock the owner settings row first; new record admission takes a fixed transaction advisory quota lock before the owner lock. Bound records to1000 per owner/10000 globally and4096 UTF-8 bytes each. Use server UUIDs/DB time and content-free audit logs. A missing settings row reports a disabled bootstrap revision0 to management only; its first explicit configure creates revision1. This sentinel is not an authorized D29 snapshot. Expected revisions fence concurrent configuration and record edits.

Every settings change increments the epoch and immediately invalidates old receipts for write/use, including re-enable; there is no automatic resurrection of old memories. Stored records remain owner-inspectable/deletable while disabled. New consent requires enabled current settings and an exact expected epoch. Session consent additionally verifies the existing owned active conversation under its normal owner lock; project scopes remain owner-local labels. Revocation is idempotent and immediately denies dependent capture/use; it does not claim physical erasure before purge.

Manual capture derives immutable scope/receipt fields from the locked owner receipt, builds source text SHA itself and validates the D29 bundle against fresh DB time before insertion. Default record expiry equals receipt expiry; explicit shorter retention must fit the receipt and class cap. Editing replaces text/provenance with exact manual content, removes any model producer and increments version under the same still-active consent; expired/inactive records require new explicitly consented capture. Delete/inspect controls do not require memory enabled. No arbitrary owner/model/provenance fields are accepted as user capabilities.

Repository snapshots alone do not authorize source-derived extraction or prompt use. T03 must hold/revalidate actual user-message/file source across model delay and capture, use exact verified producer metadata and current receipt/settings fences. No automatic transcript/file scanning or memory prompt injection is enabled by T01. Retention cleanup must be bounded and cancel/joined before pool shutdown when later enabled. D31 tests delete/export/injection propagation across the actual stores then in use; no invented vector memory exists here.

## Acceptance

Actual runtime-role grants/immutability, four-class/manual capture, two-owner denial, revision/epoch/revoke/expiry, quota, concurrent controls and rollback of failed transactions must pass. Existing source/API/ingestion behavior requires related regression and a full actual-system run before D30 final acceptance. Backup/restore and old-data/security fingerprints are mandatory before/after applied migration. Code alone cannot close T01 or D30; no production feature flag is enabled during acceptance.


## Pre-API resource review amendment

The first repository-focused121 PASS/2.85s and existing source-related113 PASS/218.66s expose no functional regression. Related-system review identified a missing resource bound on receipt creation even though records were bounded. Before any API enablement, cap receipts independently at1000 per owner/10000 globally, using the same global-before-owner transaction admission order. Add actual full-inventory tests; no applied V005/schema/grant/model change. T03 must prune bounded orphan inactive receipts so released capacity can be reclaimed without deleting provenance still referenced by records. Earlier source freeze and test checkpoint remain retained; new focused verification is required for this amendment.


## Observed T01 acceptance — 2026-10-19

Fresh private pre-backup restores all9 original tables/security; quiet reviewed V005 rollout preserves8 old data tables and original owners/ACLs. New post-backup restores all12 tables/security; all restore probes removed, no shared restart. Applied migration bytes unchanged after rollout. Necessary file/ingestion revision guards admit0005 with immutable-ingestion checks preserved. Final focused123 PASS/3.21s, related existing source/HTTP/CORE113 PASS/218.66s,0 SKIP. Final memory/source/quota/probe/vector/worker/lock inventories0 and runtime immutable-column/TEMP/TRUNCATE permissions remain denied. [T01 acceptance](../evidence/d30-t01-journal-acceptance.json). No memory API/runtime enabled. T02 APIs and T03 extraction/retention remain next tasks within open D30; final full regression remains mandatory for whole-day acceptance.
