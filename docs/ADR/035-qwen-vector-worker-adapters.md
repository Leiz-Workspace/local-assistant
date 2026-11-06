# ADR-035 — Bounded Qwen encoding and owned generation vector adapters

**Purpose:** Define D25-T03-A adapter semantics before model execution/vector writes, preserving journal/source acceptance.

**Date:** 2026-10-19
**Status:** A accepted at952 PASS/0 SKIP; B/C subsequently accepted under ADR-036 after979 PASS/0 SKIP. D25 PASS local opt-in lifecycle; D26 NEXT.

P1; depends on approved Qwen CPU/1024 selection and accepted T01/T02. Split T03 into A (actual encoder/vector adapters), B (journal/source orchestration, lease/cancel/recovery), C (explicit admission/lifecycle integration and end-to-end acceptance). Multiple milestones are allowed; no automatic D26 advancement or model replacement. Risks include invalid/mixed vectors, source text in payloads, accidental adoption of foreign collections, partial/lost acknowledgements, late writes after cleanup and stale-generation publication.

## T03-A scope

Add an isolated offline encoder script using the already pinned official Qwen assets, preprocessing and locked CPU packages. No new model/download/precision/runtime choice. Count full unprefixed passages and refuse overflow, encode batches of four with the existing validated last-token/L2 implementation, verify model fingerprint/counts/dimensions/finite unit vectors in the parent. Limit request8MiB/text1MiB/1000 passages, response32MiB, one process-local admission,600-second parent wall/480-second child CPU/8GiB address-space. Credential-free environment, no GPU/network/remote code. Async cancellation kills and joins the owned process group before releasing the slot; hard parent SIGKILL/orphan process supervision remains a required B recovery gate, not implied by adapter tests.

Qdrant adapter requires an explicitly supplied installation ownership UUID and existing credential delivered in memory. Use approved full-fingerprint collection/schema, or a fresh uniquely named acceptance probe supplied only by trusted test/operator code. Collections carry application/owner/model metadata; collision or ownership/schema mismatch fails without adoption/deletion. Creation uses stable supplied ownership so a lost create acknowledgement can be reconciled through matching metadata. Create payload indexes idempotently only after ownership verification. Never delete a collection in production adapter code.

Upsert deterministic IDs in bounded batches with wait=true and strong ordering; retries may repeat identical writes. Bind every plan/encoded batch to approved model/owner/root/source/hash/generation/count identity. Vector payload is a minimal allowlist of trusted identity/filter fields plus text/provenance hashes and conservative quality presence, not D22 structured-row content. D22's in-memory payload can contain row data inside structure; do not copy it wholesale into Qdrant. Full provenance/uncertainty remains reconstructible from trusted source/chunk ID and bound digest, not trusted vector assertions.

Verify exact scoped point count, IDs, minimal payload and stored normalized vectors (Cosine may renormalize within tolerance) before reporting success; do not infer success from HTTP200 alone. Delete only the exact owner/namespace/file/source/model/generation filter with wait=true/strong ordering, then confirm zero scoped points. Never delete by source ID alone or mutate unrelated generations/collections. Error bodies/keys/text/vectors must not enter logs. Loopback-only Qdrant transport, redirects/proxies disabled, bounded replies/timeouts. No database publication or active routing is performed by A.

## B/C gates and rollback

B must retain the trusted source FD through reconstructed-plan/hash/token checks and joined work, heartbeat/fence leases, verify actual complete acknowledgements, activate only after latest desired/source checks and drain on shutdown. Serialize all writes and cleanup for a namespace/job across processes; a cleanup acknowledgement must not race an old writer's late request. Lost acknowledgement, process kill, retry/reclaim, source update/delete and late-write cleanup need real integration tests. Do not mark cleanup complete solely because a delete raced with an in-flight encoder/writer. PostgreSQL/Qdrant remain separate transactions; D26 requires SQL active-generation plus final source revalidation.

C adds explicit authenticated admission and default-off lifecycle integration after B, validating supported schema/grants and approved configuration. No automatic parser/chunk/source/model changes. Explicit OCR/VLM scheduling/rechunk contracts must be evaluated separately rather than guessed from an unreconstructible manifest. D25 PASS requires full real end-to-end incremental ingest/upsert/delete/recovery acceptance, not only A.

Rollback A removes unused adapters and stops joined child work; preserve source/config/E5/journal/data. Tests create and remove only a fresh acknowledged-owned probe; no production collection or points are created. Rollback B/C disables admission, fences/drains workers and retains additive metadata/old generations for reviewed forward repair.

Primary API contracts: [Qdrant collection metadata](https://qdrant.tech/documentation/manage-data/collections/), [v1.18 upsert](https://api.qdrant.tech/v-1-18-x/api-reference/points/upsert-points), [v1.18 delete](https://api.qdrant.tech/v-1-18-x/api-reference/points/delete-points). Local tests must verify actual installed-server behavior; upstream documentation is not benchmark evidence.

## Observed A checkpoint — 2026-10-19

**Purpose:** Accept adapter scope independently of yet-unimplemented orchestration/admission.

36 unit/negative and2 actual cases pass (38 focused in4.16s); final full **952 PASS in117.24s,0 SKIP**, actual PostgreSQL/CORE/Qdrant/Qwen. Actual CPU encoding produced10 distinct1024-dimensional vectors, stored with exact payload/vector verification and multi-page reads. Repeat upsert retained10 IDs; deleting one generation preserved20 points in a newer generation/foreign owner before exact cleanup. Probe removed; shared collection inventory/config/count fingerprints and selected config unchanged. A second real subprocess launch was cancelled and reaped with no live process-group member. Invalid vectors/model/response/ownership, private row exclusion, lost-create-ack reconciliation, bounded cyclic scroll and mock timeout/launch-cancellation/pipe-failure gates passed. No production collection or journal publication was performed.

T03-A PASS local adapter scope; T03-B/C and D25 remain open. Approved source/model/selection/E5 rollback/T01/T02 implementation remains unchanged in A.
