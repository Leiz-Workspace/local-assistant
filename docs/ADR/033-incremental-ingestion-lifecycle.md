# ADR-033 — Incremental ingestion identity, admission and durable lifecycle

**Purpose:** Define D25 boundaries and acceptance before introducing ingestion code or persistence.

**Date:** 2026-10-18
**Status:** Accepted for T01 local planner/token admission after observed tests; durable lifecycle remains a proposed T02/T03 contract. D25 remains IN PROGRESS, not PASS.

## Scope and dependencies

P1; depends on accepted D17 source ownership/namespace/ready/hash, D22 deterministic exact chunks and owner-approved Qwen selection in ADR-032. Effort: multiple independently tested milestones. Risks include source deletion during encoding, byte/token mismatch, unstable retry identity, cross-owner reuse, lost upsert acknowledgements, stale-generation publication and resource contention. Preserve accepted D15–D24 behavior and E5 rollback. No new model selection, service/container, Vault secret or automatic model download.

T01 establishes a pure server-side ingestion plan and an isolated offline Qwen tokenizer preflight. T02 adds reviewed additive PostgreSQL journal/migration, optimistic source fencing, leases and recovery. T03 adds bounded embedding/Qdrant worker, explicit admission and upsert/delete reconciliation. Final acceptance requires real crash/retry/update/delete tests and full regression; passing T01 alone cannot advance to D26.

## T01 decision

Only trusted FileService/D22 results may enter the planner; no HTTP endpoint accepts arbitrary chunks, owner or ACL labels. Compare source owner/file/namespace/ready/deleted/hash with trusted metadata and recompute every D22 chunk ID from exact metadata/content. D22 descriptive access labels are consistency checks, not capabilities or proof of original source bytes. Source reader/integrity checks remain the service's responsibility. Reject malformed, duplicated, foreign or tampered chunks before tokenization. Preserve exact Unicode, rows, provenance and uncertainty; never normalize or truncate.

Bind deterministic manifest/generation/job/point identities to owner, storage namespace, source file/hash, chunker/processor/byte policy, exact ordered chunk content and selected model fingerprint. Store only immutable canonical JSON in plan records. A retry of identical input yields identical IDs; any source/options/model/content change yields a separate generation. UUIDv5 point identities include generation and chunk identity. Qwen vectors are1024/Cosine and cannot share the preserved E5 space.

Use the pinned official Qwen tokenizer in a separate frozen uv script process, local-only/remote code disabled/left padding, same unprefixed documents and512-total-token cap as the approved comparison. Reject the entire batch on empty/overlong input; return counts only, not source content or tokens. Verify artifact hashes and runtime/tokenizer/model fingerprint identity. Credential-free environment, bounded input/output, wall/CPU/address-space limits, no GPU/network/download. No embedding session/model weights need be loaded for token counting. A byte cap alone never authorizes embedding. Keep this isolated environment separate from existing API/E5 packages.

## Durable implementation contract for T02/T03

Admission must lock and recheck the source owner/namespace/ready/hash before recording immutable model/manifest/generation identity. Jobs have bounded lease/attempt/backoff/deadline, explicit pending/running/ready/failed/stale/tombstone states and exactly-once publication through an active-generation pointer. Expired workers cannot publish or acknowledge another worker's lease. Worker input is reconstructed from trusted source/chunk contract; private extracted content is not put into logs. No long database transaction spans parsing, tokenization, embedding or HTTP.

Upserts use deterministic point IDs with wait-for-acknowledgement semantics. Retry may repeat the same upsert after a lost acknowledgement. Stage a full generation, verify expected point/source/count/hash identity, then publish only after a final locked source/owner/namespace/ready/hash fence. A generation is not visible merely because points exist. New input builds a new generation; source deletion hides immediately through PostgreSQL state, then durable tombstone cleanup retries Qdrant deletion. Source revalidation remains mandatory for D26 retrieval, even after payload filtering. PostgreSQL/Qdrant have no shared transaction.

Create only a separately owned collection with approved fingerprint/schema. Refuse to adopt or overwrite colliding names. Retain E5 configuration/weights/collections and user sources. No generic admin cleanup or automatic deletion of old generations. New schema requires offline DDL review and protected backup/restore verification before migration, then real independent-connection races. Do not mutate schema in T01.

## Rollback and acceptance

T01 rollback removes unused planner/tokenizer tooling; existing API/source/config/database/collections are unchanged. Later rollout is opt-in: disable admission, join/fence workers, retain journal/source/vector generations, restore exact E5 selection/routing only if separately rolling back selection, verify source/ACL/golden behavior. Never drop populated journal tables or delete source data to roll back code.

T01 tests must cover independent UUID/hash reconstruction, retry stability, owner/namespace/hash/model/content/metadata/options drift, duplicate/foreign/tampered chunks, empty documents, Unicode/row/quality preservation, bounded token-process protocol,512/513 boundaries with actual Qwen tokenizer and unchanged approved selection/D24 evidence. Remaining T02/T03 gates stay explicitly open.

## Observed T01 acceptance

**Purpose:** Bind the narrow accepted scope to actual tests without accepting unimplemented journal/worker behavior.

58 new unit cases and3 actual Qwen tokenizer cases passed. Focused related suite117 PASS in19.98s; final Vault-backed full regression **870 PASS in114.48s,0 SKIP**, real PostgreSQL/CORE/Qdrant and offline Qwen. An initial boundary fixture correctly failed:512 repetitions of ` x` counted513 total tokens; corrected511 repetitions count512, preserving special-token and no-truncation behavior. No model/tokenizer/corpus/gate change was used to force success.

Ruff correctness/import/format and description audit passed; frozen tokenizer script lock resolves offline. [Retained acceptance](../evidence/d25-t01-ingestion-admission.json) includes source hashes and boundaries. Existing selected Qwen/configuration approval, exact E5 rollback, registry and original D24 source/evidence remain unchanged. Existing application/source/schema/service configuration is untouched. No D25 schema/collection/upsert/delete was deployed; existing full-suite probes retain their own cleanup scope. T01 PASS only; T02 durable journal NEXT, T03 worker and D25 final acceptance open.

## Subsequent T02 checkpoint — 2026-10-19

**Purpose:** Preserve T01 evidence while linking accepted durable journal work.

ADR-034/T02 now passes local journal/schema scope with applied V003/V004, protected pre/post restores and final914 PASS/0 SKIP. Source/lease/revision publication fences and cleanup obligations are durable; actual vector worker is not implemented. T03 NEXT, D25 remains IN PROGRESS.
