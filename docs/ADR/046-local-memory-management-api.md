# ADR-046 — Default-off local memory management API

**Purpose:** Compose accepted D30-T01 transactions with authenticated owner controls without enabling extraction or automatic memory use.

**Date:** 2026-10-19
**Status:** Accepted for local T02 manual management after actual tests; T03 and D30 final full acceptance remain open.

## Scope and assessment

P1; depends ADR-018/044/045 and verified V005/grants. Effort one T02 milestone within open D30. Risks are caller owner/provenance injection, stale-version changes, unsafe startup credentials/grants, disabled-user control loss and cancellation during SQL. Preserve existing models/source/index/conversation behavior. No migration, new dependency, secret, service, model inference or prompt injection.

## Decision

Add `ASSISTANT_MEMORY_ENABLED=0` by default. Initialization is inert when off. When explicitly enabled, require existing app sessions, exactly reviewed V005 and immutable/mutable/TRUNCATE privilege checks before creating a management service. The API continues using the runtime app credential; no Vault/operator URL is read by it. Owner memory and extraction settings remain independently default-off regardless of the operator feature flag.

Use existing direct-localhost/Origin/forwarding rejection and bearer principal for every `/api/v1/memory` route. Strict bodies accept only settings expected revision/flags, bounded consent class/scope/duration, or manual text/receipt/expected record version. Authoritative owner/IDs/provenance/model fields are server-derived. Owner-wide scope defaults to principal; session/project UUIDs confer no rights by themselves. Settings changes invalidate old receipt epochs; no automatic resurrection on re-enable.

Expose settings inspect/configure, consent grant/revoke and bounded record metadata list/inspect/manual create/edit/delete. Management inspection/deletion remains available when the owner's memory is disabled or consent inactive. Editing/capture still requires active consent. Responses are private/no-store/nosniff; errors are stable content-free codes. Bulk lists contain metadata only; explicit record inspection returns its own bounded untrusted text/provenance. Missing/foreign IDs share404 behavior. Bootstrap revision0 is management-only, never a valid D29 authorization snapshot.

Track and cancel/join owned SQL operations before pool/file shutdown. Transactions roll back on cancellation. Management reads/mutations linearize at their SQL transaction; they are not long source-held generation responses. T03 must separately add source/model ownership, final receipt/source fences, extraction cancellation and bounded retention worker. This milestone does not provide extraction, export, source propagation or memory-to-prompt injection and must not claim them through successful CRUD.

## Acceptance and rollback

Require default-off/no-I/O and schema/grant startup gates, strict input/error/privacy tests, actual two-principal HTTP CRUD/consent/disable/version/revocation tests on V005, operation cancellation/shutdown and actual loopback TCP. Preserve preexisting model/source behavior; full D30 acceptance still requires T03 and final full regression. Disable/drain the feature to restore prior API behavior, retaining additive journal/data. No populated downgrade or user data deletion for rollback.


## Actual local T02 acceptance — 2026-10-19

Initial37 focused/108 related PASS did not cover repeated cancellation. A new precise rollback-cleanup barrier test failed (25 PASS/1 FAIL/.58s); replace inline awaited SQL with a tracked shielded child and cancellation-resistant finish_task join.26 unit PASS/.53s. Final related109 PASS/9.11s,0 SKIP includes38 new T02 cases: strict schema/error/default-off startup, actual two-principal HTTP/control/disable/version gates, observed PostgreSQL PgSleep cancellation/rollback/pool checkout0 and real ephemeral loopback TCP. Validation failures no longer echo private inputs, using a memory-only route wrapper; old API exception behavior unchanged. Read-only final audit clean, V005/model choices unchanged. [Acceptance](../evidence/d30-t02-api-acceptance.json). Production flags remain off; no source extraction, retention worker or prompt injection claimed.
