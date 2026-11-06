# ADR-036 — Source-held ingestion worker and repeat terminal cleanup

**Purpose:** Define D25-T03-B/C orchestration, late-write recovery and opt-in admission before service integration.

**Date:** 2026-10-19
**Status:** Accepted for local opt-in D25 lifecycle after979 PASS/0 SKIP on2026-10-19. D26 retrieval NEXT; production deployment/load/DR scope remains separate.

P1; depends on T01/T02 and verified T03-A. Effort additional local milestones. Risks: source drift during encoding, lost write/publication acknowledgements, cancelled leases, duplicate worker processes and late writes following a previously acknowledged delete.

## Worker decision

Use one asynchronous namespace/model worker, protected for its lifetime by a PostgreSQL session advisory lock on a dedicated connection (committed after lock acquisition; no long SQL transaction during parsing/model/HTTP). Another worker for the same namespace/model must fail, not compete. Keep actual source-reader/extraction context through exact plan/count reconstruction and joined encoding/write work. Rebuild using existing auto chunk operation/max_bytes from immutable manifest; compare complete admission fingerprint before writing. Explicit OCR/VLM options that cannot be reconstructed are not added to admission. No smaller chunks, altered text or label repair to force token acceptance.

Heartbeat a claimed job while encoding/writing; changed source/lease/desired generation interrupts and joins child/network work. Verify stored points before the journal's atomic final publication fence. Transient worker/vector failures schedule bounded journal retry; immutable reconstruction drift terminalizes the old attempt for cleanup. Lost publication acknowledgement is resolved by durable job/head state, never by reviving a cleared token. Shutdown disables admissions, cancels/joins worker work and source holders before releasing namespace lock/vector client/file service.

## Repeat terminal sweep

A delete can race an earlier uncertain network write even after its client was cancelled. A single zero count and cleanup acknowledgement cannot prove that no late request will arrive. Keep terminal journal tombstones indefinitely and repeatedly scan them in bounded keyset pages, including previously acknowledged cleanup. Delete only exact trusted generation filters and reverify zero; acknowledge the observation idempotently. Future sweeps repair a late write after a prior acknowledgement or process restart. Namespace/model worker exclusion prevents concurrent local writers/cleanup, but no distributed DB/Qdrant transaction or global network-partition fencing is claimed. D26 SQL active-generation/source revalidation hides stale/deleted sources immediately; physical vector deletion is eventually repaired by repeated durable sweeps. Retention/compaction needs separate evaluated scheduling, not automatic tombstone deletion.

## Admission/lifecycle

Add authenticated loopback POST file-index admission and owner-scoped job status, default disabled. Reuse existing FileService source/namespace/auth/root behavior; no caller chunks/vectors/access labels. Use approved config/actual counts; persist journal before background processing. Require ingestion schema0004/effective immutable-column grants, selected approval hash, private operator-delivered Qdrant key/ownership file and explicit feature enablement before startup. No Vault root lookup inside the API. Tests inject only a fresh removable physical probe; production config/collection stays undeployed unless operator explicitly enables it.

D25 acceptance requires real source upload/admission, Qwen/Qdrant writes, deterministic replay/new generation, wrong-owner/root rejection, delete/update races, partial/lost acknowledgement recovery, cancellation/lease/drain and late-write sweep after restart. Rollback disables/drains service, retains journals/source/generations/E5/config and uses forward repair. Never delete existing shared collections/source data or broaden grants to make tests pass.

## Process-death supervision decision

**Purpose:** Close the hard-parent-SIGKILL resource gate before accepting a background model worker.

The API passes only its PID and `/proc` start identity in the credential-free encoder environment. Before importing/loading Torch, the child opens a Linux pidfd for that exact parent and verifies its start identity, then a daemon watcher blocks on pidfd readiness and SIGKILLs the encoder if the API parent exits. This watches the API rather than uv's intermediate launcher. PID/start verification fails closed during launch gaps. Existing Linux-only filesystem/sandbox/runtime assumptions remain; no package/model change. Real tests must kill the encoder's API-side parent and verify no live process-group member remains. Async cancellation/timeout still kills and joins the full owned group through the normal path.

Source-slot429 conflicts defer a live claim without consuming a model attempt or extending the absolute deadline. This prevents normal bounded extraction contention from exhausting retry budget; permanent source/model drift remains fenced. Repeat sweeps acknowledge an initial clean observation but keep terminal jobs eligible for future deletion, without rewriting the original cleanup timestamp every cycle.

## Observed implementation — 2026-10-19

**Purpose:** Bind the implemented orchestration/admission to real lifecycle and resource tests.

B/C use retained auto source contexts, immutable projection/count reconstruction, guarded DB-time attempts, actual CPU encoder and owned stored-vector verification/activation before final SQL publication. Bounded repeat terminal scans include old cleanup acknowledgements. Private operator-file/approval validation and explicit default-off authenticated admission/status are integrated in lifespan; no Vault root use inside API or production collection created in acceptance. Busy-source429 defers without consuming model attempts. Source updates follow existing immutable replacement UUID/hash policy.

Final full **979 PASS/162.02s,0 SKIP**, including real upload/admission/Qwen/Qdrant publication/replay/replacement/delete, owner/default-off/Origin gates, uncertain vector/SQL acknowledgements, processor drift, heartbeat invalidation, shutdown/cancel, advisory duplicate-worker and shielded-check gates. Actual SIGKILL after stored upsert recovered same IDs on a new process/lease without duplication; actual encoder API-parent SIGKILL left no live encoder group. Prior focused B/C/encoder14 PASS/48.53s; two later boundary tests are included in the final full result. Fault-only model cases are explicitly injected unit vectors, not benchmark evidence.

No new schema/model/runtime package selection; original source service/journal remains intact. T02 repository gains only reject/defer/repeat-terminal methods using existing grants. [Final acceptance](../evidence/d25-ingestion-acceptance.json) and [post-audit](../evidence/d25-post-audit.json) retain clean state. D25 PASS local opt-in lifecycle; D26 retrieval NEXT. Production multiworker/load/long-input/paired SQL-source-Qdrant DR remain separate gates.
