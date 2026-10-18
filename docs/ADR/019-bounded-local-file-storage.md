# ADR-019 — Owner-scoped file metadata and bounded local blob storage

**Purpose:** Decide the D16 foundation and record why D17 must use an explicit journal, quotas and descriptor-safe I/O.

**Date:** 2026-10-18 (Asia/Ho_Chi_Minh)
**Status:** Design accepted after executable policy tests and review; runtime file persistence/HTTP acceptance belongs to D17.

## Context

Day 15 has authenticated UUID principals, owner checks, shared PostgreSQL, DB-clock leases and verified local recovery. No file metadata table or blob adapter exists. MinIO is shared and available for future use, but adding an object provider now introduces credentials/policy and consistency work unrelated to a local single-worker upload milestone. Existing disk inspection showed approximately 617 GiB available; other server applications share the filesystem.

## Decision

Use the existing app PostgreSQL schema for typed file ownership, lifecycle/idempotency/provenance and global/owner allocated usage. Use a new private local root `ai/data/files` for V1 opaque blobs. Never store binary payloads in JSONB or use client filenames as paths. All keys derive from authenticated owner UUID + server file UUID; root paths and storage keys are internal. No new instance/service, migration, bucket, credential or runtime route is introduced in D16.

Keep display labels normalized and conservative; enforce declared and observed size/hash. Defaults are an 8 KiB pre-parse metadata envelope, 25 MiB/file, 1 GiB/1,000 allocated files per owner, 10 GiB/10,000 globally, two owner/four global upload slots, 2 GiB free-space floor, 64 KiB chunks, bounded stream/reservation/lease deadlines and bounded OOXML expansion. These are initial product limits, not throughput or security benchmark claims. Executable helpers in `file_storage_policy.py` validate these contracts; they are not invoked by any existing endpoint.

Require metadata reservation before accepting raw body streaming. The versioned fingerprint includes owner, normalized label, declared size and expected SHA-256, excluding generated file UUID and request key. Same-owner/same-key conflict/replay is deterministic. No cross-owner deduplication, implicit conversation attachment, remote URL import, macro or executable upload.

Atomic quota admission locks global -> owner -> file; streaming/verification/fsync/file-lock waits occur outside SQL sessions. Retain allocation until every owned payload link/FD is gone; ready releases the upload slot but retains bytes/file allocation. Release markers make cleanup idempotent. Use file locks in addition to DB leases: an expired but paused process or active reader can still hold inode bytes, so expiry/unlink alone is insufficient to release quota.

Create and verify staged regular files through directory descriptors/no-follow/exclusive opens. Durable same-filesystem publication must not replace an existing object. Only a verified, durably published journal row may become ready. A cross-resource crash leaves a hidden charged resource for fenced reconciliation. Purging never scans/deletes arbitrary paths and never releases usage before physical cleanup/close.

Future V002 is additive and owner-typed; structural checks, owner indexes, key equality, request uniqueness, usage consistency and app grants are specified in `FILE_STORAGE_DESIGN.md`. V001/Day 15 remain untouched. Rollback disables admission, drains/fences writers and preserves added tables/blobs. Once bytes exist, backup and restore must pair metadata, inventory and blobs; the existing DB-only drill is not enough.

## Alternatives

| Alternative | Decision and consequence |
|---|---|
| Shared MinIO immediately | Defer; no new MinIO service or broad root credential use. A later adapter requires scoped app bucket identity and parity tests for create/delete/lease/restore semantics |
| Client pathname or hash-only global object keys | Reject; traversal and cross-owner existence/deduplication leakage; opaque server UUID keys remain independently authorized |
| Filesystem-only metadata | Reject; loses atomic owner/quota/idempotency and crash-journal queries |
| Database BYTEA payloads | Defer; couples large streaming/restore to the metadata DB and pool; does not satisfy the selected bounded blob contract |
| Drop quota on lease expiry or unlink | Reject; an old writer/reader FD can retain bytes. Require cooperative file-lock cleanup/close before release |
| Hold a SQL transaction while receiving/verifying | Reject; consumes the validated shared pool for unbounded client I/O |
| Implement upload endpoints during D16 | Reject; D16 is design/policy acceptance. D17 requires real DB/FS/HTTP failure/race and paired-backup evidence |

## Review and validation

The detailed specification maps ownership, bounds, schema, request replay, lock order, blob durability, provenance and rollout/rollback to D17 tests. Scope additions carry priority/dependency/effort/risk assessments; unsupported features remain unscheduled rather than being silently inserted into a day.

D16 pure policy tests exercise boundary bytes/UTF-8, traversal labels, UUID-derived keys, canonical fingerprints, corrupt usage, quota/concurrency/free-space limits, type mismatch, ZIP expansion and log privacy. The complete Day 15 suite must be rerun with the existing app credential from Vault and ready CORE. Exact outputs are recorded in the D16 dev-log entry, never inferred from this ADR.

Remaining implementation risks: atomic SQL counters, real byte sniffing, bounded parsing, no-follow FD/inode behavior, file-lock fencing, no-replace publication, crash cleanup and paired backup. D16 PASS does not make any of these D17 behaviors PASS.

## Observed acceptance — 2026-10-18

Policy suite: **86 passed in 0.06s**. Full regression using the existing application credential from Vault and ready CORE: **237 passed in 9.48s**, zero skipped/no exclusions. Read-only inspection confirmed Alembic `0001` and four current tables; no V002 or blob-root mutation occurred. Existing Day 15 runtime and API code stayed unchanged.

Review corrected owner deletion during receiving/verifying to retain allocation until old FDs close, and required stable principal identity restoration instead of assigning records to a new credential identity. Detailed D17 gates remain open by design. This accepts D16's planned schema/storage/rollback contract, not file upload capability.
