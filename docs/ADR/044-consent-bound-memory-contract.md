# ADR-044 — Consent-bound memory classes and provenance

**Purpose:** Define D29 memory contracts and the proposed additive schema before D30 persistence, API or extraction work.

**Date:** 2026-10-19
**Status:** Design/contract implementation in progress after D28 commit `a2cc9c0`; acceptance pending tests.

## Context and assessment

The roadmap requires session, episodic, preference and project memory with consent/provenance in schema. Existing conversation history is not consent to long-term memory; legacy conversation ownership remains JSONB under ADR-018. Existing file/source/RAG and model choices are accepted separately. There is no implemented memory store, opt-in or memory injection today.

P1; depends D15 authenticated UUID ownership, D28 accepted source provenance and a reviewed policy/schema. Effort D29 contract/design milestone, then D30 implementation and D31 privacy acceptance. Risks are cross-owner/scope use, inferred consent, stale source proof, retained sensitive content, extraction prompt injection and claiming structural provenance is truth. No new model, embedding/index, service or dependency is needed.

## Decision

Define strict frozen executable schemas for settings, immutable consent receipts, provenance and memory records. Supply a proposed additive PostgreSQL schema outside the migration directory. D29 does not apply a migration, start memory services or modify existing source/history. Test proposed relational constraints only through the existing dedicated migrator in connection-private temporary tables on the existing PostgreSQL instance; do not create a second service/database or persistent application relation.

Memory is off by default; extraction is separately off. Every owner settings change increments an epoch. Receipts bind owner, class, scope, epoch, policy version and mandatory expiry. Revoked, expired, future or wrong-epoch consent never authorizes write/use. Turning off extraction prevents new extracted writes; it does not silently erase existing consented records. Disabling memory denies model use/write immediately; explicit owner inspection/export/deletion must remain available in D30. Automatic transcript/file learning and implicit consent are prohibited.

Session scope is one owned conversation, maximum24 hours; project scope is an owner-local project UUID, maximum365 days. Episodic/preference scopes are owner-wide with scope UUID equal to owner UUID, maximum365 days. All records require explicit expiry bounded by both class cap and receipt expiry; default requested retention in D30 is planned1 hour session/30 days other classes, never indefinite. A project UUID is a label within an owner, not an access capability or proof of a project workspace.

Provenance is a discriminated strict structure: manual content SHA-256, an exact user-message quote/hash/conversation/message/span, or an exact file quote/hash/native locator/field/span. Manual writes bind the stored text hash and have no model ID. Extracted writes require nonmanual provenance, explicit extraction consent/settings and verified producer model ID. Exact quote spans use Unicode code points and preserve bytes/normalization. Records and sources remain untrusted data, never system instructions, tools or inferred facts about the owner.

The pure authorization helper validates the supplied current snapshot and explicit server principal/time/action; it does not fetch authoritative state or prove source ownership. D30 must lock fresh owner settings/receipt/record, revalidate actual owned user message or retained file hash/native span before capture/use, and fence concurrent disable/revoke/delete. A self-asserted structurally valid provenance object is insufficient. Do not backfill/adopt legacy unowned conversations. Conversation history and memory deletion remain separate documented resources.

Proposed tables bind each record to an exact owner/class/scope receipt with a nonnullable composite FK. SQL checks class scope, retention, content size, provenance type and timestamps; runtime validation adds exact shape/hash/span semantics. Legacy conversation ownership cannot be represented by a false typed composite FK; D30 enforces its existing owner lock instead. Explicit grants must override inherited default privileges before deployment, following the D25 V004 lesson. No runtime grants or existing tables change in D29.

## Acceptance and rollout

D29 accepts only the four-class contract, explicit consent/provenance schema, negative owner/scope/epoch/revoke/expiry/extraction/hash/Unicode/budget tests and actual temporary-table relational tests, with unchanged accepted application/model/migration bytes. It does not claim memory APIs, persistence, extraction, retention cleanup or privacy propagation implemented; those remain D30/D31.

D30 needs its own additive migration/backup/restore/grant/startup compatibility review and actual authenticated CRUD/disable/consent/extraction/retention tests. D31 checks source deletion, injection, export and permanent purge scope. No model replacement or implicit memory-to-prompt integration is authorized by this design. Rollback D29 removes unused new contract imports/files only; there is no persistent memory state to migrate or erase.


## Observed pre-acceptance probe identity correction

Initial unit run40 PASS/6 FAIL exposed a fixture offset counting a combining/astral quote as five code points rather than four; correct only the fixture offsets, retain strict production validation. Revised46 unit cases PASS. Initial combined46 PASS/15 setup errors showed the runtime app identity intentionally lacks database TEMP privilege. Preserve its grants. Supply an explicit operator-only temporary-schema probe URL from the existing Vault migrator to these tests; do not put it in API configuration or change app privileges. The corrected tests still create only temporary relations and roll back, not migrate the application schema.
