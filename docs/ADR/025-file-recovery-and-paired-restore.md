# ADR-025 — Namespace-scoped reconciliation and paired metadata/blob recovery

**Purpose:** Close D17's crash, retry and restore gates without inferring blob recoverability from DB-only backups.

**Date:** 2026-10-18 (Asia/Ho_Chi_Minh)
**Status:** Accepted for D17 local scope: 443 passed in 30.14s, zero skipped, plus retained actual paired restore/API-process drill. Production/off-host scope remains unaccepted.

## Decision

Start a bounded recovery pass on explicit file-feature startup, then one five-second process-local loop. Query only the root's namespace. For expired reserved/receiving/verifying records, recheck DB expiry under global -> owner -> file locks and fence to purging; live leases and ready resources are never expired by a stale candidate. Purging retains allocation until physical cleanup and release commit. Busy/error attempts move their journal retry timestamp to the queue tail, so one held inode cannot starve other resources under a bounded batch limit.

Page through ready resources separately with a UUID cursor. Check known staging names; remove only a same-inode redundant stage link after exclusive payload/resource locks, private inode/size/hash proof and parent fsync. Retain ready bytes/file allocation. Collisions, unknown names, held readers and corrupt/missing payloads remain unresolved; never delete/adopt unknown data or manufacture ready bytes. Download still checks the full hash before headers. Stop/join recovery before shutting down active requests/root/pool.

Use descriptor-based bounded inventory with no-follow traversal, private permissions/device/link checks, a required valid namespace marker and a 100,000-entry/depth ceiling. Backup must match the exact known ready payload inventory; unknown/staged/multiply linked/corrupt objects prevent certification rather than being silently ignored.

## Paired snapshot and restore

`scripts/file_storage_recovery_acceptance.py` is an operator CLI, never an API/model tool. Require stopped API consumers, zero other source-DB connections, no unresolved journal states, consistent global/owner counters, nonempty ready payloads and existing stable principal bindings. Reject mixed/missing root namespaces. Use an app-role repeatable-read read-only transaction with a DB-exported snapshot; the existing Docker PostgreSQL operator writes a private custom dump using that snapshot. Compare source row and normalized owner/ACL fingerprints before/after. No shared service is restarted.

Copy payloads using SH source FDs, bounded chunks, expected size/hash and private no-replace target publication. Preserve the logical root namespace explicitly. Retain a protected digest-only principal-binding copy; never store a raw API/Vault token. Verify exact inventory/hash/permissions again, create an independent restored blob root, then restore the paired DB dump into a uniquely generated probe on the **existing** PostgreSQL instance and compare all seven tables plus owner/ACL fingerprints. Drop only the exact probe using the existing guarded helper. Successful manifest binds archive SHA-256, expected blob inventory, namespace and identity verification.

Archive output is streamed to an exclusive 0600 file and synced; hash reads are chunked. The reviewed local restore helper is allowed to read an archive only after a 64 MiB cap. Ready inventory is capped at 10,000 rows; tombstones are counted/validated in SQL rather than fetched wholesale. Source statements/locks have 30s/5s limits. Artifacts remain 0700 directories/0600 files, outside Git; failed snapshots are retained without a success manifest. This is a verified local same-instance restore, not off-host/full-cluster disaster recovery or physical power-loss certification.

Restore activation must drain the old deployment, retain namespace and the original principal UUIDs, and use current authorized Vault credentials. Restoring an old digest file must not silently undo credential revocation/rotation. Never activate an incomplete clone merely by copying the namespace marker. A DB-only backup cannot restore blobs; a blob-only copy cannot restore ownership/quota/idempotency.

## Assessment, tests and rollback

P0 within planned D17 recovery/paired-restore scope; dependencies are T01–T04, quiet consumers and protected backup capacity. Effort is reconciler/operator tooling, real DB/FD/crash tests, isolated paired restore and process restart. Risk is wrong-root cleanup, split DB/FS snapshots, fairness, unsafe restore/adoption and secret leakage; namespace fencing, snapshots, hashes, principal checks and strict artifact permissions address those within the defined local scope. New services/roles/credentials are unnecessary.

Paired integration tests clone **schema only** into exclusive same-instance source probes, seed V002's version/zero singleton and use the app role. This prevents tests from depending on or copying live user blobs; source/restore probes are removed through the guarded exact-prefix helper. Runtime quota/FD tests remain uniquely owner/root scoped. The CLI allows only `local_assistant` or generated restore-probe names with the existing app identity.

Evidence includes real uploader SIGKILL with partial/published bytes and expired-but-live locks, fair retries, ready-stage link reconciliation, real unlink/fsync failure, rolled-back release counter updates and retry, concurrent HTTP replay/quota, delete-versus-receiving HTTP, negative snapshot cases, protected paired restore and API readback. A separate retained operational drill used the real Vault principal, two actual Uvicorn processes, replay/download/delete across restart and verified paired archive/blob/identity restoration. Original conversation rows/ACLs remain equal; canary/probe cleanup and zero final allocation are checked.

Rollback disables admission, drains/cancels and joins requests/recovery, and retains the journal/root marker/blobs/backups. Do not drop V002 or delete payloads to undo code. Populated downgrade remains prohibited; forward fixes or a separately reviewed paired restore are required. Production multiworker/load SLOs, off-host encryption/retention and malware guarantees remain future work.
