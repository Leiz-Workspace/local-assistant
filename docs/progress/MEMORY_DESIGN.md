# D29 — Consent-bound memory design and executable schema

**Purpose:** Define four memory classes, explicit opt-in, provenance and retention contracts before D30 storage/API implementation.

**Status:** PASS for D29 design/contract scope:47 new pure policy/schema cases and16 actual temporary PostgreSQL cases,63 PASS/0.53s,0 SKIP. [Validation](../evidence/d29-contract-validation.json), [post-audit](../evidence/d29-final-post-audit.json), [ADR-044](../ADR/044-consent-bound-memory-contract.md). Memory storage, APIs, extraction and prompt injection are not enabled or implemented by D29.

## Classes and scope

| Class | Scope ID | Maximum lifetime | Planned D30 requested default |
|---|---|---:|---:|
| session | One owned conversation UUID |24 hours |1 hour |
| episodic | Owner UUID |365 days |30 days |
| preference | Owner UUID |365 days |30 days |
| project | Owner-local project UUID |365 days |30 days |

Every record and receipt requires an explicit expiry; the record cannot outlive its receipt. Defaults are proposed request policy, not an existing background retention service. Project UUIDs are scoped labels, not proof of a workspace or access capabilities. Memory is separate from persistent conversation history and uploaded source/index data.

## Executable and proposed schemas

[`memory_contract.py`](../../src/application/services/memory_contract.py) provides strict frozen models, a discriminated provenance union and pure `authorize_memory` write/use validation. [JSON schema](../proposals/d29-memory-contract.schema.json) is an exported structural contract. [SQL proposal](../proposals/d29-memory-schema.sql) defines three additive tables outside `migrations/`: owner settings/epoch, immutable receipt identity with revocation, and bounded untrusted records with a composite owner/class/scope receipt FK.

Settings default memory/extraction off. Epoch mismatch, revoked/expired/future consent, disabled memory, wrong owner/scope/receipt and expired records deny use/write. Disabling extraction denies new extracted writes while allowing existing records under still-live consent; turning memory off denies both use/write. D30 explicit owner inspection/export/deletion must remain available while disabled.

Manual records hash exact stored UTF-8 text and have no producer model. Extracted records require explicit settings/receipt permission, nonmanual provenance and verified producer model ID. User-message evidence includes owned conversation/message IDs, user role, complete source hash, literal quote and code-point offsets. File evidence includes immutable file hash and native field locator/span. Combining characters and astral code points are preserved. Text/quotes are nonblank, at most4096 UTF-8 bytes, and cannot contain NUL; producer/locator sizes are bounded. `content_trust` is always untrusted.

These schemas describe evidence, not its authenticity. The pure helper revalidates supplied snapshots but does not query current DB state, verify source ownership, resolve quotes against actual sources or confer capabilities. D30 must perform fresh owner-scoped transactions/locks and retained-source/native-span checks before capture/use; source revocation/delete and concurrent disable need final fences. No legacy conversation ownership backfill or history-to-memory learning is implied. A model ID string does not prove actual inference; D30 must obtain it from the existing verified adapter.

SQL adds relational/basic size/time/type defenses; application validation supplies exact JSON shape, hashes and Unicode span semantics. Cross-row consent expiry/epoch/revocation and source authenticity need service transactions. SQL checks do not establish PostgreSQL row-level tenant isolation. No proposed relation or grant is installed by D29.

## Observed verification and limitations

Initial40 PASS/6 FAIL found incorrect Unicode offsets in synthetic fixture data; strict production validation was retained and fixture lengths corrected. Initial combined46 PASS/15 setup errors found the app intentionally lacks TEMP permission. No grant was broadened: actual temporary schema tests use a separate explicit `LOCAL_ASSISTANT_MEMORY_SCHEMA_PROBE_URL` from the existing Vault migrator. This URL is test/operator-only and must never become API database configuration. A subsequent60 PASS/1 FAIL found raw synthetic UUID JSONB encoding;62 PASS/1 FAIL found the incorrect test exception namespace. Both fixture/adapter issues were corrected. Final63 PASS/0.53s,0 SKIP; actual SQL rejects null provenance kind rather than accepting a SQL NULL check result.

Each relational test creates three connection-private temporary tables, uses only synthetic records and rolls back. The source proposal remains unapplied. Read-only post-audit confirms application revision0004, permanent/temporary memory relations0, app TEMP false/migrator TEMP true, original owner/ACL fingerprint unchanged and source/index/quota/probes/workers/locks0. All254 tracked preexisting code/test/config/model/dependency/migration files from D28 commit `a2cc9c0` are byte-identical. No API imports the new module, inference runs, dependency/model download or application-memory runtime is introduced.

D28's full1334 PASS/1387.90s plus2 native-field PASS remain the unchanged system baseline. D29's63 new cases run separately:1399 unique tests across checkpoints, not a new1399-case full invocation. Tests establish this design/contract scope, not deployed retention, source-authenticated extraction, privacy propagation or model quality.

## D30 implementation gates

Review additive migration/grants/indexes/downgrade refusal, fresh protected backup/isolated restore, current schema compatibility and least-privilege startup before applying any migration. Explicit grants must override inherited defaults, following V004. Use the existing PostgreSQL/Vault identities; no new service or credential. Preserve every accepted source/model configuration.

Implement default-off authenticated owner APIs for settings/consent and inspect/create/edit/delete/disable; use expected revisions and fresh locked authorization. Implement separately opt-in bounded extraction through existing CORE and exact source proofs, without implicit model replacement or automatic history scanning. Define deterministic expiry/purge scheduling and reversible disable/drain rollback. D31 independently verifies injection, deletion, export and source propagation. Model-use injection and vector memory require their own actual acceptance, not merely this schema.


## D30-T01 implementation checkpoint — 2026-10-19

[D30 journal guide](D30_MEMORY_JOURNAL.md): V005 is now applied after protected pre/post backup/restore; old data/security preserved. Local repository/schema123 focused+113 related cases PASS/0 SKIP, clean audit. D29's earlier unapplied-schema statements describe its historical design checkpoint. Memory runtime/APIs/extraction remain disabled/unimplemented in T01; D30 stays open for T02/T03 and final whole-system acceptance. Original contract/model choices remain unchanged.


## D30-T02 management checkpoint — 2026-10-19

[Memory API](MEMORY_API.md) now implements default-off local authenticated manual settings/consent/record controls, accepted109 related cases/0 SKIP. Owner opt-in is separate from the operator flag; disabled owners retain inspect/delete. No extraction, automatic learning, prompt injection or retention worker is implemented yet; T03 remains open. Original D29 design-only statements remain historical.


## D30-T03 implementation checkpoint

[Message-memory selection](D30_MESSAGE_MEMORY_SELECTION.md) implements explicit existing-user-message CORE selection, bounded retention and read-only owner export under ADR-047/048. Focused147 PASS/0 SKIP; final regression/audit pending. File-to-memory and prompt/vector use remain assessed future backlog, not implemented adapters. Original D29/T01/T02 statuses above remain historical; D31 privacy/source propagation remains open.


## D30 final acceptance

[D30 acceptance](../evidence/d30-memory-acceptance.json): **1570 full-suite PASS/1357.69s,0 SKIP**, after147 focused PASS and clean post-audit. Explicit message selection, bounded retention and owner export are locally accepted; previous checkpoint descriptions above remain historical. Production flag off; no model/schema change in T03. D31 source deletion/injection/export propagation NEXT.


## D31 source privacy checkpoint

[Transactional source repair](D31_PRIVACY_AND_DELETION.md) is now locally accepted under ADR-049/V006:271 final related plus140 source-system PASS/0 SKIP and clean audit. Enabled memory now requires0006; files/ingestion admit reviewed0006 while keeping existing grant checks. Applied V005 and prior acceptance entries remain historical/unchanged. Source deletion/edit removes dependent extracted records atomically; independent explicit manual preferences remain. D31-T02 and final full-day acceptance remain open.
