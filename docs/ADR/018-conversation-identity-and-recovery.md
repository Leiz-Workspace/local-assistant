# ADR-018 — Local principal ownership, pool log export and recovery acceptance

**Purpose:** Define and review the remaining D15-T06 identity, telemetry and database recovery changes before execution.

**Date:** 2026-10-18 (Asia/Ho_Chi_Minh)
**Status:** Accepted and verified for authenticated localhost on 2026-10-18; Day 15 local gate PASS.

## Identity contract

The persistent conversation API requires a bearer credential bound to a UUID principal. A protected `ASSISTANT_AUTH_FILE` contains only SHA-256 digests of high-entropy random tokens and their principal UUIDs. It must be a regular owner-only file, owned by the API process UID; final symlinks are rejected. Config is reloaded on each request so revocation takes effect without restart. Missing/bad configuration returns 503; absent/invalid credentials return 401. No token, digest or credential value is logged. Keep the existing direct-loopback, Origin and forwarding-header rejection; authentication does not authorize external exposure.

V1 uses the existing JSONB metadata `owner_id`, assigned exclusively by the authenticated service. Repository filters and manager row locks constrain reads, list/history, mutations, reservation, recovery and finalization. Another principal receives 404 for guessed conversation IDs and cannot replay an owner's response. Request bodies cannot set owner/metadata; arbitrary identity headers confer no rights. Internal maintenance callers may deliberately use unscoped repositories/services; the HTTP dependency always constructs a principal-bound service.

No DDL is required. Existing records with no owner remain quarantined from all HTTP principals. Do not infer ownership from title/profile or assign every historical row to the first token. A future explicit adoption operation requires a reviewed mapping and backup, or a typed owner-column migration with indexes once scale warrants it. This policy preserves legacy data without a silent backfill.

OIDC/Keycloak remains a future identity-provider option. Adding local principals does not change the shared Keycloak realm, app credential or infrastructure. Digest-only configuration is for random API tokens, never human passwords. The raw local API token belongs in the existing application Vault namespace; only the DB URL and auth-file path enter runtime environment, never an operator Vault token.

## Pool telemetry

Observe real checkout/checkin/invalidation events and count mapped pool timeouts. Export current size/checkout/overflow, observed peak and cumulative counters as periodic structured JSON logs (30-second interval), plus timeout/shutdown samples. No session, SQL, DSN or driver exception is retained. Logs are the V1 export transport; no new public diagnostics endpoint or monitoring service is introduced. Bound pool waiting to 10 seconds and suppress SQL parameters in SQLAlchemy errors.

An integration probe saturates a real one-slot pool, confirms timeout/invalidation counters and multiple sampler emissions. This demonstrates telemetry, not a long-duration production latency SLO.

## Reviewed database drill

The existing PostgreSQL container serves Keycloak and Local Assistant. Use only the existing instance and named data volume. Preflight requires: confirmed persistent data volume; no active consumer transaction, no application DB connection and no pending inference; Keycloak discovery reachable. Repeat the drain check immediately before restart. Abort on failed checks rather than forcing consumers or killing transactions.

The operator script writes exclusive 0600 archives in a new 0700 ignored backup directory. Back up every non-template database and global roles; globals can contain password hashes and must never be printed or committed. Insert only an isolated temporary canary into the app database. Restore the Local Assistant archive into a uniquely named temporary database on the same instance, compare all application table row counts/canonical row digests plus schema/table/sequence owners and normalized ACLs, then remove only that restore database. SHA-256 protects backup file integrity. No second service or database instance is created.

Only after the source remains stable and isolated restore passes may `--execute-restart` restart the existing container, with a 60-second graceful stop. Verify readiness, unchanged app table fingerprints/canary, and Keycloak discovery after reconnect. Remove only the canary created by the drill. Other consumers are not restarted or reconfigured.

Rollback/recovery: backups and manifests remain protected on failure. If PostgreSQL does not return, inspect/start the same container and existing volume first; never initialize/replace the volume. If data integrity differs, stop the drill and review the retained archives/role dump. Do not automatically restore over a production database, delete user records, change passwords or roll back other applications. The default script verifies backups/restore without restarting; explicit restart is exercised only as the user's requested remaining D15-T06 acceptance after this plan's preflight passes.

## Acceptance gates

- Two real authenticated principals: all cross-owner read/history/update/send/replay/archive/delete denied; own operations work; unowned history stays hidden; manager locks independently fence owner mismatch.
- Unsafe auth configuration and credential revocation behave deterministically without logging secrets.
- Real pool saturation, periodic samples, invalidation and safe HTTP timeout errors tested.
- Backup/restore preflight and destructive-target guards unit tested; actual isolated restore and shared restart outcomes logged.
- Full regression including CORE, auth, ownership and crash recovery passes; no skipped gate is counted as PASS.

## Actual acceptance — 2026-10-18

Full pytest: **151 passed in 9.45s**, zero skipped, with PostgreSQL/CORE enabled. Unsafe auth config, revocation, duplicate headers, two-principal isolation and direct manager fencing passed. Real one-slot pool saturation/invalidation/periodic export and stale owned-backend replacement passed. A fresh logging process and real Uvicorn runs emitted metrics without credentials.

The final drill in `data/backups/t06-acl-verified-20261018/` retained four custom database archives and globals (0600 files, 0700 directory), verified SHA-256, restored app rows and ownership/ACLs, then restarted the existing container after the repeated quiet gate. Source data stayed equal, Keycloak discovery returned 200, canary and restore database were removed. Earlier data-only drills remain retained as historical artifacts; final archives preserve owner and privilege metadata. No other service was reconfigured and no second database instance was created.

A raw API token now resides only in Vault at `secret/server/local-assistant/api` (`api_token`, `principal_id`); `data/auth/principals.json` holds only its digest binding. Two disposable Uvicorn processes used this real credential to prove anonymous denial, CORE chat, persisted history, cached replay and metrics. Both stopped and their test conversation was removed. Protected runtime artifacts are not Git deliverables.
