# ADR-047 — Explicit user-message memory selection and bounded retention

**Purpose:** Complete D30-T03 opt-in extraction/retention with actual source and consent fences before whole-day acceptance.

**Date:** 2026-10-19
**Status:** Accepted locally after focused147 PASS/0 SKIP, full1570 PASS/1357.69s,0 SKIP and clean post-audit; see [D30 acceptance](../evidence/d30-memory-acceptance.json).

## Scope and priority

P1; depends accepted four-class consent contract, V005 repository and owner management APIs. Effort one or more T03 implementation milestones. Risks: fabricated source quotes, stale/deleted/foreign message capture, epoch/revoke races, repeated cancellation, retention backlog and conflating verbatim evidence with semantic truth. No model/download/precision/profile/routing/schema change.

Initial extraction accepts only one explicit existing **user** message in an active owned conversation. There is no automatic history scan and no learning from assistant/system messages. Existing files remain in source-revalidated RAG instead of duplicating their contents into long-term memory. The D29 file-evidence schema is a structural future contract, not an implemented file adapter. File-to-memory is P2 backlog: depends D30/D31 consent/deletion/export acceptance and native source span/root handling, effort at least one milestone, risks duplicate retention and source-delete propagation; not required to claim an adapter exists in D30.

## Selection and source authority

Default operator and owner opt-in remain unchanged; additionally require both extraction settings and receipt permission. The request supplies receipt/conversation/message UUIDs only, never owner/text/hash/model/provenance overrides. Read fresh owner settings/receipt and actual owned active conversation/user message under existing locks; cap complete source at8192 UTF-8 bytes without truncation. Release short SQL locks before model inference.

Use only existing verified CORE/fast, temperature0/output512/model wall60s. Fixed system instructions treat message text as untrusted data. Output is strict JSON selecting one **unique exact literal quote** or explicit insufficient_evidence. Reject duplicate/extra keys, nonfinite values, missing/ambiguous/normalized/foreign quotes, raw output over8192 bytes and quotes over2048 UTF-8 bytes. Store the selected quote itself as the memory text, not an unverified generated summary. Exact selection establishes source provenance, not durable truth, user intent classification or independent model quality.

Before capture, acquire global quota admission then owner/receipt/source locks in that order. Re-read actual user message ownership/active conversation/complete content hash; stale/deleted/changed source or disabled/revoked/expired/old-epoch consent prevents insertion. Server derives exact source IDs/hash/Unicode code-point offsets and actual verified producer model ID. Mandatory record expiry cannot outlive the receipt. No inferred ownership/backfill of legacy conversations.

Retain tracked extraction ownership through response delivery; validate current record version, source and consent again before headers. Owner controls commit before cancelling/joining matching in-flight extraction tasks. One nonqueued extraction, owned shielded model/SQL child work, and cancellation-resistant joins prevent cleanup from being interrupted before ownership closes. Shutdown drains extraction/retention before manual work and pool resources. The shared CORE server is not killed; backend prompt/KV-cache erasure or immediate compute cancellation is not certified. Changes after the final authorization point are ordered after it, not a distributed transaction with socket delivery.

## Retention

When the operator feature is enabled, start one bounded periodic retention task on the existing app pool: at most10 owner IDs/cycle and100 expired records plus100 orphan inactive receipts per owner, default30-second interval and rotating UUID cursor. Expiry is independent of owner enablement. Never delete active referenced receipts or source/history/vector data merely to free quota. Orphan receipt cleanup covers expired/revoked/old-epoch receipts with no referenced records. Data/source deletion propagation and export/injection testing remain D31; no invented vector memory exists here.

The worker owns/joins each database child operation, stops on shutdown and logs only counts/stable error codes. No startup model call or extraction job is scheduled. Retention is bounded eventual cleanup, not a deadline guarantee under arbitrary downtime/load; expired records cannot authorize memory use or edit while awaiting purge. Management inspection can still show its own stored record until actual purge.

## Acceptance and rollback

Require exact quote/Unicode/JSON/source-budget tests; actual user-message/CORE selection and insufficiency; foreign/assistant/unowned refusal before inference; real source delete/change/model-delay and owner disable/revoke/final-response fences; repeated cancel/timeout/shutdown joins; actual expiry/orphan cleanup bounds and worker drain; actual authenticated HTTP/TCP; full V005 system regression and clean inventories. Record failures and same-agent synthetic-data limits. D30 stays open until all gates pass; D31 is not started early.

Disable/drain feature to retain existing journal safely; no model/index/source migration or populated downgrade. Preserve agreed model lineup and exact E5 rollback. Any later memory source, vector embedding or model replacement needs separate scope/benchmark/ADR/approval as applicable.


## Observed pre-acceptance JSONB codec correction

First combined source/contract/management checkpoint108 PASS/1 FAIL/4.81s. Actual extracted message provenance serializes UUIDs as JSON strings; reading the persisted row through Python-strict MemoryRecord rejected those strings during owner edit. Add an explicit database decoder for only tagged message/file provenance UUID fields, preserving strict outer SQL types, unknown-field rejection and the original D29 schema. Update only the accepted base journal read/edit decoding points because the newly implemented extracted source path requires it; manual semantics and applied V005 remain unchanged. Add exact JSONB-shape round-trip and malformed-identity tests. No model inference/quality result has yet been accepted.

## Measured final acceptance

Final full1570 PASS/1357.69s (22:37),0 SKIP, exit0. Python source matches pre-regression freeze; model/config/dependencies/applied V005 unchanged. Actual owner SQL/CORE/HTTP/TCP, export and retention gates accepted within documented local synthetic scope. Final inventories0 and original owners/ACLs/grants preserved. Earlier failed attempts retained; D31 source deletion/injection/export propagation remains separate.
