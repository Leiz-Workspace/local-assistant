# ADR-021 — Additive file journal, immutable policy and fenced quota transactions

**Purpose:** Record the V002 rollout, counter invariants and DB/FS integration obligations for D17-T02.

**Date:** 2026-10-18 (Asia/Ho_Chi_Minh)
**Status:** Accepted for D17-T02 repository scope after V002 rollout, 24 real journal cases and full 327/327 PASS; HTTP/paired blob restore remain unaccepted.
**Dependencies:** ADR-018 principals, ADR-019 storage contract, ADR-020 resource guards.

## Decision

Add only `assistant.files`, `assistant.file_owner_usage`, and `assistant.file_global_usage`, using the existing migrator credential from `secret/server/local-assistant/postgresql-migrator`. The runtime continues using `local_assistant_app`. Keep V001 and existing conversation schema/behavior unchanged. Do not create services or use a superuser in the API.

Store a complete immutable policy snapshot with each reservation, alongside policy version, owner UUID, semantic fingerprint, expected bytes/SHA-256 and UUID-derived object key. Admission uses the current policy; an admitted upload uses its stored deadlines/bounds, avoiding reinterpretation after configuration changes. Database CHECKs enforce key/owner/provenance, nonnegative counters, upload progress, ready invariants and terminal release markers. Same-owner request keys remain unique through tombstones; there is no automatic retry of failed uploads or cross-owner deduplication.

All quota/state mutations use short transactions with the same lock order: singleton global usage, owner usage, file. Owner initialization occurs under the global lock. Canonical replay is resolved before capacity checks so retries never allocate again. Counters charge declared bytes and one file/upload slot through receiving/verifying/purging; ready releases only the slot. Terminal cleanup releases the remaining counters exactly once, atomically with release markers. Constraint violations roll back all mutations.

Use DB time for reservation/lease/absolute wall deadlines. Initial claim takes one DB timestamp so a lease equal to wall duration cannot violate ordering through microsecond drift. Heartbeat is monotonic, bounded by declared size, and capped by wall deadline; expired leases cannot revive. Each upload has one immutable lease UUID, also identifying its staging file. A separate purge token fences cleanup without losing that staging identity. Owner deletion hides/fences immediately and overrides an earlier failure cleanup target; ordinary expiry never releases quota by itself.

The repository contains no filesystem access. Caller must acquire the ADR-020 guard, recheck/claim inside it, close every borrowed verifier/writer FD, and prove physical purge before invoking release. `ready` trusts the internal service's bounded verifier and durable publication; it is not proof of bytes from the database alone. There is no HTTP route in T02 and no client can choose owner/lease/purge tokens.

## Rollout review

Priority is P0 within existing D17 scope. Dependencies are the accepted policy/FS adapter, quiet local consumers, a fresh verified protected backup, and the existing migrator identity. Effort includes migration, real independent-connection quota/replay/lease races, fault handling and regression; risk is counter drift or premature release across DB/FS, so runtime admission remains disabled.

1. Reuse `scripts/postgres_recovery_acceptance.py` with a new private directory, **without** `--execute-restart`. Verify all archives' hashes/permissions and app restore row/owner/ACL match; retain artifacts outside Git. Only the generated restore-probe DB on the existing instance is removed.
2. Render `uv run python -m alembic upgrade 0001:0002 --sql` with a credential-free offline URL. Review exactly three additive tables, indexes/CHECKs, owner-scoped uniqueness, explicit DML grants/revoked TRUNCATE, no old-table changes and guarded downgrade. DDL has local lock/statement timeouts and transactional rollback on failure.
3. Using only the existing Vault migrator credential, verify current database/role and revision 0001, then apply `upgrade 0002`. Compare existing conversation/message/run row and owner/ACL fingerprints before/after. No payload root, public proxy, parser or API feature is enabled by applying this schema.
4. Run real PostgreSQL tests using the app credential and the complete existing suite; only uniquely owned test records/counters are cleaned. Record exact outputs before declaring T02 accepted.

## Rollback and remaining acceptance

Disable file admission first; drain/fence writers, retain additive tables and private blobs. A rollback to Day 15 code can ignore these tables. Never drop populated tables or delete blobs to roll back code. Downgrade checks for *any* file row (including tombstones) or nonzero allocation before dropping; nonempty rollback must use a forward fix or reviewed paired DB/blob restore. A DB-only restore is insufficient after payloads exist.

This serializes quota admission globally, intentionally prioritizing correctness for the local single-worker deployment over high-throughput multiworker scaling. There is no PostgreSQL RLS, off-host DR or production multiworker certification implied. T03 bounded MIME, T04 HTTP/off-event-loop FS integration, and T05 DB/FS crash/race/paired restore remain mandatory D17 acceptance even after repository tests pass.
