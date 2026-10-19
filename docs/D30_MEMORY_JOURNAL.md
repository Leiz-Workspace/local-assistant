# D30-T01 — Additive memory journal and controls

**Purpose:** Record the applied memory schema/repository checkpoint while keeping API, extraction and runtime-retention gates separate.

**Status:** T01 PASS for local repository/schema. D30 IN PROGRESS; T02 APIs and T03 source-verified opt-in extraction/retention remain open. [Acceptance](evidence/d30-t01-journal-acceptance.json), [ADR-045](ADR/045-memory-journal-and-control-transactions.md), [D29 contract](MEMORY_DESIGN.md).

## Schema and rollout

V005 adds `assistant.memory_settings`, `memory_consents` and `memories`, owner/expiry indexes and explicit grants. Existing V001–004 migrations and eight old data tables remain unchanged; only migration revision and three new tables are added. New table-level app privileges are first revoked to override inherited defaults, then SELECT/INSERT/DELETE and narrow mutable-column UPDATE are granted. Owner/class/scope/receipt/creation identity and receipt lifetime/epoch remain immutable to the runtime role. No new role, credential, service, DDL/TEMP/TRUNCATE permission, model or collection.

Before rollout, offline SQL was reviewed and a fresh private cluster/app backup proved an isolated restore with all nine original tables, rows and normalized owners/ACLs. Source was quiet and unchanged after canary cleanup. The existing Vault migrator applied V005. Eight original data-table fingerprints and all original relation/schema owners/ACLs remained equal. A new post-migration app backup restored all twelve tables and security on a uniquely owned temporary database in the existing instance; the probe was removed. No shared service restart. [Pre-restore](evidence/d30-t01-pre-migration-restore.json), [rollout/post-restore](evidence/d30-t01-v005-rollout.json).

Previously accepted file and ingestion initializers require explicit known revisions. Their only behavioral change admits reviewed0005 while preserving old compatible revisions, unknown-schema refusal and immutable-ingestion grant checks. Actual related source/HTTP/Core tests passed on0005; source storage, embeddings, vectors and original model configuration are unchanged.

## Repository semantics

`PostgresMemoryJournal` uses the existing bounded app pool. Management reads report missing settings as disabled bootstrap revision0 without creating consent. An explicit settings compare-and-swap creates revision1; each subsequent settings change advances the epoch. Old receipts never revive after disable/re-enable. Owner inspection/list/deletion remain available while owner memory use is disabled. The repository is unused by API startup in T01.

New receipts require enabled settings, exact expected epoch and class/scope/expiry validation. Session scopes additionally lock the actual active owned conversation; foreign, absent, archived and legacy unowned conversations confer no rights. Project UUIDs remain owner-local labels. Revocation is idempotent and immediately prevents future capture/edit. It is distinct from physical record deletion.

Manual capture derives IDs/scope/hash/provenance from server data and a locked receipt, never caller metadata. Default record expiry equals receipt expiry; explicit shorter duration must fit the receipt and class cap. Manual edit uses an expected version, exact new content hash, removes any producer and retains the same active consent/expiry. Inspect/list/delete are owner-scoped; list exposes bounded metadata rather than bulk text/provenance. Hard delete requires the expected version. Bounded expiry purge is a repository operation, not a running background service in T01.

All owner mutations serialize through settings locks. Global admission locks precede owner locks for new records and receipts, independently capped at1000 per owner/10000 globally. Initial121 focused cases covered record caps; a pre-API review found receipt growth was not bounded, so the same admission rule and two real full-inventory tests were added before final123-case acceptance. Applied V005 remained byte-identical. T03 must reclaim orphan inactive receipts without deleting provenance referenced by records.

## Actual tests and audit

Final focused **123 PASS/3.21s,0 SKIP** includes strict D29 policy, migration/serialization, schema/grant compatibility, temporary D29 constraints and real app-role repository cases. Actual cases exercise four classes, exact Unicode hashes, two-owner controls, legacy/session refusal, revoked/expired/old-epoch consent, stale versions, failed-write rollback, exact owner/global record and receipt caps, real concurrent settings CAS and capture-versus-disable/revoke ordering. Quota fixtures insert owned synthetic constrained rows to reach the caps; they do not claim10000 actual API captures/model calls.

Existing related suite **113 PASS/218.66s,0 SKIP** covers actual file journal/HTTP/crash/recovery, ingestion journal/worker/HTTP, dense retrieval and existing grounded ASGI/TCP/native-field generation on0005. This run precedes the new receipt cap but never imports/uses the new memory repository; affected accepted app guards remain byte-identical afterward. No full1437-test invocation is claimed: D28 baseline1334+2, D29 new63 and T01 new38 give1437 unique tests across checkpoints. A complete whole-system run remains required before D30 final acceptance.

Read-only final audit: revision0005; memory settings/receipts/records0, files/jobs/heads/quota0, restore probes/Qdrant collections/model workers/advisory locks0. App TEMP false, record owner/receipt expiry UPDATE denied, mutable text UPDATE allowed. All test writes were removable owned fixtures. [Post-audit](evidence/d30-t01-final-post-audit.json). Original model registry/CORE/UNRESTRICTED/Qwen selection/E5 rollback and dependencies remain unchanged.

## Rollback and remaining work

Leave additive schema in place when disabling future memory features. V005 downgrade refuses any settings/receipt/record row; do not discard user data or broaden grants to roll back. No memory API, source-derived extraction, prompt injection, retention worker, export or propagation is enabled by this checkpoint. Source-authenticity/final-delivery fences and source deletion remain T03/D31 obligations. Proceed T02 with default-off authenticated management APIs and independent owner opt-in; preserve agreed models.
