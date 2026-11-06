# ADR-037 — ACL-filtered retrieval with source rehydration

**Purpose:** Define D26 authorization, query encoding, delivery lifetime and bounded search before implementation.

**Date:** 2026-10-19
**Status:** Accepted for local opt-in D26 after1030 PASS/0 SKIP on2026-10-19. Production deployment and D27 evaluation remain separate.

P1; dependencies D17 immutable owned sources, D22 exact chunk/provenance identity, D25 active journal generations and approved Qwen/Qdrant contracts. Initial effort1–2 milestones. Risks: caller-filter injection, foreign/stale point delivery, processor drift, deletion/publication races and overlapping model memory. No model/precision/runtime/schema changes are proposed.

## Decision

Add read-only dense query against the existing owned collection using the Qdrant1.18 query-points API, `using=dense`, bounded limit and no returned vectors. Server builds conjunctive owner/namespace/model/private/untrusted/active filters; optional UUID file IDs narrow scope only. No arbitrary filters, owner/model/generation/vector input. Validate all returned IDs/scores/payload scope before use. Do not create/update collections or change grants for retrieval.

Encode exactly one query with the already approved profile's query instruction plus original query text, using the unchanged passage worker with its empty passage prefix. This is byte-identical to the existing benchmark's query formatting. Count complete instructed input before encoding, reject overflow without truncation, require identical encoding counts/fingerprint and reuse ingestion's encoder admission so search and indexing cannot load two model processes simultaneously. Separate tokenizer preflight retains existing shared admission. No download, fallback or reranker.

Vector candidates are untrusted hints. For each candidate file, read owner/root/source-ready/hash-bound SQL active generation, check deterministic point membership and generation, reconstruct the exact immutable source projection under existing chunk/source integrity, compare entire manifest and allowlisted vector payload, then return source text/provenance from reconstruction only. Never return text/metadata supplied by Qdrant. Rehydrate files sequentially through existing chunk slot; retain separately verified source readers until response completion. Recheck retained-reader integrity and all SQL active IDs/source fences immediately before response headers, with one final SQL snapshot covering every retained generation after integrity I/O. Deletion/supersession after this final check is ordered after delivery authorization; no distributed SQL/Qdrant/HTTP atomicity is claimed.

One nonqueued search admission remains held through response delivery; shutdown cancels/joins active operations before ingestion/files close. Track file-resource ownership as well as search tasks. Bound query4096 UTF-8 bytes, top_k1–10, optional file UUIDs1–16, candidate_limit=max(20,5*top_k) up to50, response1MiB. Stale/deleted/unpublished candidates are omitted, not refilled beyond the explicit candidate budget; fewer than top_k results does not certify corpus exhaustion. No score threshold/quality/recall claim. Scores are similarity, never confidence. Results remain untrusted source data, with exact source hash/chunk/provenance/quality.

Authenticated loopback POST `/api/v1/retrieval/search` uses strict JSON, private/no-store and nosniff, default-off `ASSISTANT_RETRIEVAL_ENABLED=1` requiring enabled ingestion/files/approved selection. No automatic conversation context or model routing. Shutdown retrieval before ingestion. Rollback disables/drains retrieval and retains all source/journal/collection/ownership state.

## Acceptance gates

Independent negative tests: filter intersection, malicious scope/payload/IDs/score/duplicate/oversized replies, input bounds, model/query-prefix/token behavior, SQL inactive/deleted/stale/root/owner/replacement, exact reconstructed text/provenance, final delivery source/generation races, admission/cancel/shutdown and safe errors. Actual CPU/Qdrant/SQL/HTTP tests must cover two principals and immutable replacement/delete; flags remain default off outside probes. Full existing regression without skips is required before D26 PASS. D27 reranker/model evaluation remains separate.

Reference: [Qdrant1.18 query-points API](https://api.qdrant.tech/v-1-18-x/api-reference/search/query-points). Existing approval/configuration and D24/D25 evidence remain unchanged.

## Observed acceptance — 2026-10-19

**Purpose:** Bind the implemented read path and delivery contract to actual verified gates.

Final full1030 PASS in216.32s,0 SKIP, exit0;51 new D26 tests (40 unit/policy/protocol/delivery and11 actual PostgreSQL/Qdrant/service/HTTP). Focused51 PASS/54.37s. Actual HTTP uses the unchanged CPU Qwen worker, approved query formatting and real source/vector/journal paths with two principals, file narrowing, immutable replacement/delete and instructed-token overflow. Fault tests use explicit unit vectors and are not model-quality measurements.

Actual source readers remain held through response completion; source deletion and generation replacement fence delivery. A legitimate publication injected during the final integrity I/O is caught by the final single SQL snapshot. Hostile scope/IDs/score/duplicate/vector/payload/hash/projection, default-off/auth/Origin, busy slot, cancellation/shutdown and failed send were verified. Earlier ASGI fixture failures omitted the HTTP scope type; two test assertions used an incorrect FileService tracking attribute; strict UUID JSON narrowing initially needed per-element parsing. All corrected before final acceptance; no model/corpus/threshold changes.

Readonly post-audit: schema0004, jobs/heads/files/quota0, collections0, restore probe DBs0, encoder processes0 and worker advisory locks0; immutable manifest grants and original owners/ACLs unchanged. No model/config/dependency/schema/Vault/Docker mutation; existing D25 worker unchanged. Only API router/lifespan registration changed among established code. [Evidence](../evidence/d26-retrieval-acceptance.json), [post-audit](../evidence/d26-post-audit.json), [guide](../RETRIEVAL.md). D26 PASS local opt-in; D27 evaluation planning NEXT.
