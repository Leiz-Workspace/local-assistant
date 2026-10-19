# ADR-049 — Transactional message-memory source invalidation

**Purpose:** Repair the actual D31 source-change/export privacy failures without changing accepted models or source API semantics.

**Date:** 2026-10-19
**Status:** Accepted locally for D31-T01 after271 final related/140 source-system PASS,0 SKIP and clean audit; whole D31 privacy acceptance remains open.

## Evidence and scope

D30 commit `478bec0` is accepted with1570 full PASS/0 SKIP. D31 baseline has3 actual SQL/HTTP failures/.84s: soft-deleting a conversation, editing a source message or deleting it leaves its previously extracted quote in inspection/export. Same-agent controlled inference isolates persistence/privacy rather than claiming real model quality. Manual independent memory must remain.

P1 D31-T01, depends accepted V005/source provenance and fresh cluster/app backup plus isolated restore. Effort one or more implementation/check milestones. Risks: lock ordering, accidental deletion of independent manual/foreign records, partial source mutation, restoring old copies and startup schema incompatibility. No model, dependency, Vault policy, Docker or vector configuration change.

## Decision before implementation

Add V006 invoker-security PostgreSQL row triggers on the existing message/conversation tables. Source mutation and dependent-memory removal must share one transaction, including when the memory feature or owner is disabled. An application-only callback or periodic sweeper would leave gaps for alternate mutation paths, failed callbacks, restart or disabled startup. No owner/global lock is added by the trigger after a conversation/message lock; existing capture order remains global admission, owner/receipt, conversation, message. SQL timeout/deadlock failure must roll back the entire source mutation, never acknowledge partial invalidation.

Before deleting a conversation or making its deleted_at nonnull, remove exact message-provenance records for that globally unique conversation ID, plus session-scoped memories and now-orphan session receipts for it. Ownership changes also invalidate these copies. Preserve unrelated owner/project/manual records. Archiving alone retains explicit memory; it still prevents new source capture under existing active-source rules. This does not convert the accepted soft-delete transcript API into permanent source erasure.

Before message deletion or a change of content/role/conversation/id, delete only exact conversation-message provenance for the previous globally unique message/conversation pair. No-op or sequence-only updates retain valid evidence. An explicitly edited manual record is independent and has manual provenance; it is retained. Add partial provenance lookup indexes. Functions use fixed search_path, qualified tables, no dynamic SQL or definer privileges, and content-free server count logs. No new app grants, existing-column/data rewrite, model call or memory vector index.

Do not retroactively delete existing rows at rollout. Require empty current memory inventory before applying this local V006; if populated, stop the rollout and produce a separate audited backfill/retention plan. Preserve all old migrations byte-for-byte and all current source data/ACLs. Compatibility guards admit reviewed0006 for files/ingestion; enabled memory requires0006 rather than silently serving known0005 privacy gaps. Unknown later revisions remain refused.

## Verification and rollback

Before application: actual connection-private temporary SQL tables/functions exercise mutation/no-op/manual/foreign/session/rollback behavior, followed by reviewed offline migration SQL and fresh protected backup/isolated restore. Apply only through existing migrator; verify exact old rows, schema/table/column permissions and version, then post-migration isolated restore. No shared restart. Actual app-role HTTP/SQL tests must prove source changes remove dependent export/inspect data atomically and retained sources/manual records remain. Add concurrent model/capture/control and rollback tests; run related and final full regression. Do not advance D31 until its remaining injection/export/purge gates pass.

Rollback removes only these triggers/functions/indexes after disabling/draining source mutation/extraction; never restore deleted private memories from backups as an automatic rollback. Populated schema downgrade remains separately controlled. Backups, WAL, already-delivered exports/model context and secure disk erasure are distinct retention domains, not erased by SQL DELETE. D31-T02 must separately assess explicit permanent source/memory purge and negative injection/export tests; this source-invalidation task does not claim those capabilities.

## Measured source-task acceptance

[Acceptance](../evidence/d31-t01-source-acceptance.json):271 final related PASS/11.00s and140 source-system PASS/216.58s,0 SKIP; actual CORE/HTTP/TCP existing behavior, PostgreSQL lock ordering/rollback and1000-row SQL fixture invalidation. Initial3 failures preserved. Clean V006 post-audit; old migrations/model/config/dependencies unchanged, no production flag enabled.29 new cases,1599 unique across checkpoints, not a new1599-case full invocation. D31-T02 injection/export/purge and final full regression remain mandatory.
