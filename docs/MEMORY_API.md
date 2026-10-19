# D30-T02 — Local owner memory management API

**Purpose:** Document implemented manual memory controls, independent operator/owner opt-in and measured API boundaries.

**Status:** T02 PASS locally; D30 remains IN PROGRESS for T03 source-verified opt-in extraction/retention and final full regression. [Acceptance](evidence/d30-t02-api-acceptance.json), [ADR-046](ADR/046-local-memory-management-api.md), [journal](D30_MEMORY_JOURNAL.md). No production memory flag is enabled.

## Enablement and trust

`ASSISTANT_MEMORY_ENABLED` defaults0. Disabled initialization reads no credentials/schema or creates a worker. Explicitly enabled startup requires the existing app pool, V005 and immutable/mutable/TRUNCATE grant checks. The API never reads the operator temporary-schema probe URL or Vault root material. Existing loopback/bearer/Origin/forwarding rejection applies to every route.

The operator flag only exposes management capability. Every owner starts with memory/extraction false and management bootstrap revision0. PUT settings with expected_revision0 explicitly creates revision1; every later settings change advances the epoch, invalidating old receipts. Re-enable does not resurrect old consent. Owner inspection/deletion remains available while owner use is off or consent inactive. This milestone performs no extraction, automatic learning or memory-to-prompt injection; an extraction setting is policy consent, not proof that an extraction pipeline exists.

## Implemented routes

All paths below start `/api/v1/memory`. JSON primitives are strict; unknown owner/provenance/model/trust fields are rejected. UUID strings are IDs, never capabilities. Text is nonblank and at most4096 UTF-8 bytes, without NUL. Responses and rejected requests are private/no-store/nosniff; invalid input is a stable `memory_input_invalid` code without echoed private fields.

| Method/path | Input / behavior |
|---|---|
| GET `/settings` | Own flags/epoch; missing row reports disabled revision0 without creating consent |
| PUT `/settings` | `expected_revision`, `enabled`, optional `extraction_enabled` (defaultfalse) |
| POST `/consents` | `kind`, `expected_revision`, optional `scope_id`, `seconds`, `allow_extraction`; default1 hour session/30 days other classes, bounded by class cap |
| DELETE `/consents/{id}` | Idempotent own receipt revocation; foreign/missing404 |
| GET `/records?limit=50&after=<uuid>` | Own metadata page, limit1–100; no bulk text/provenance |
| POST `/records` | `consent_id`, literal `text`, optional shorter `seconds`; server derives identity/hash/provenance |
| GET `/records/{id}` | Inspect own bounded untrusted text/provenance, even when disabled |
| PATCH `/records/{id}` | `expected_version`, new literal `text`; requires live consent, creates exact manual provenance and increments version |
| DELETE `/records/{id}?expected_version=N` | Hard-delete own exact current version, even when disabled |

For episodic/preference, omitted scope is derived from principal. Session requires an actual owned active conversation; project scope is an owner-local UUID label. Owner-global and receipt quota caps apply as documented in the journal guide. Explicit record expiry cannot outlive receipt; default record expiry equals receipt expiry. Stale edits/settings return409; disabled capture403, full quotas429, private storage failure503. Invalid native scope/missing/foreign resource IDs return404 without disclosure. No arbitrary model, source hash, producer, owner or provenance override is accepted.

## Lifecycle and actual verification

Management transactions linearize at SQL completion. They are not long source-held model responses. Each service operation owns a shielded child SQL task; repeated parent cancellation cannot interrupt rollback cleanup. Shutdown cancels parents and joins child work before closing the app pool. No DB/model/file resources are allocated merely by importing or disabling the service.

Initial37 focused/1.63s and108 related/9.19s PASS preceded a new repeated-cancellation test. That test produced25 PASS/1 FAIL/.58s: an inline journal await let the second cancellation abort cleanup before tracking closed. The service now shields/joins an owned child via the accepted finish_task helper. Final26 unit cases PASS/.53s and final combined **109 PASS/9.11s,0 SKIP**, including all38 new T02 cases plus71 existing related cases. No separate38-case final invocation or1475-test full invocation is claimed.

Twelve actual HTTP/SQL cases cover four classes, explicit consent/disabled inspect-delete, foreign IDs, epochs/revocation, invalid Unicode-byte/NUL/metadata capture, actual cancellation after observing the owned PostgreSQL backend in `PgSleep`, pool checkout0 afterward and real ephemeral loopback TCP. TCP uses the fixture event loop, not production process/load certification. Existing file/conversation/default-off startup gates pass. No new-model quality claim; manual memory makes no inference call.

Final read-only audit: V005 unchanged; owned memory/settings/receipts, source/quota/probe DB/vector/worker/advisory-lock inventories0, old owners/ACLs unchanged. [Post-audit](evidence/d30-t02-final-post-audit.json). Original model/embedding/E5 rollback/dependencies unchanged. Disable/drain the operator feature to restore prior API behavior while retaining journal/data; never downgrade populated tables to roll back. Full-source archive `/tmp/local-assistant-d30-t02-complete-full-files.zip`.

T03 must implement actual source verification, bounded model selection, owner control cancellation/fences, explicit insufficiency and retention/orphan cleanup before D30 closes. Source deletion/export/injection propagation remains D31. Do not infer those capabilities from successful manual CRUD.


## D30-T03 implementation checkpoint

Source-literal extraction, periodic expiry and explicit owner export are now implemented; focused147 PASS/0 SKIP, whole-system acceptance pending. See [T03 guide](D30_MESSAGE_MEMORY_SELECTION.md) for actual route bodies, budgets, source/control fences and limits. Earlier T02-only statements describe that historical checkpoint, not current T03 capabilities. Production flag stays off; D31 source deletion/injection/export propagation is not yet accepted.


## D30 final acceptance

[D30 acceptance](evidence/d30-memory-acceptance.json): **1570 full-suite PASS/1357.69s,0 SKIP**, after147 focused PASS and clean post-audit. Explicit message selection, bounded retention and owner export are locally accepted; previous checkpoint descriptions above remain historical. Production flag off; no model/schema change in T03. D31 source deletion/injection/export propagation NEXT.
