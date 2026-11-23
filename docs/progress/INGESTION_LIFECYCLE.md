# D25 — Incremental private ingestion lifecycle

**Purpose:** Track implementation and acceptance of source-bound Qwen ingestion without confusing a plan or token count with a durable index.

## Current implementation boundary

D25 is **PASS for local opt-in lifecycle** after979 PASS/0 SKIP. T01 planning/token admission, T02 journal/schema and T03 actual Qwen/Qdrant worker plus authenticated admission/status are accepted. Feature flags remain off and no production collection was created; approved selection remains `selected_not_deployed`. D26 retrieval is NEXT. [Operating guide](INCREMENTAL_INGESTION.md), [ADR-035](../ADR/035-qwen-vector-worker-adapters.md), [ADR-036](../ADR/036-ingestion-worker-and-terminal-sweeps.md) and [final evidence](../evidence/d25-ingestion-acceptance.json) define the current boundary; earlier checkpoint text below is historical.

[ADR-033](../ADR/033-incremental-ingestion-lifecycle.md) defines the lifecycle before persistence/API changes. Existing FileService/chunk extraction remains unchanged. Planner input is trusted source metadata and the result of D22 extraction retained under the service's source-reader/integrity contract, never a caller-provided upload of arbitrary chunks/ACL assertions. Recomputing a chunk digest establishes consistency, not authority over source bytes. A future caller must hold/revalidate the source and execute admission/publication fences in short locked database transactions.

## T01 — Source and token admission

`plan_ingestion(row, owner_id, namespace_id, view, selection)` validates owner/root/file/ready/deleted/hash and D22 access/version/byte policy. It recomputes each chunk ID from exact source/access/content/provenance metadata, rejects duplicated/tampered/foreign chunks and bounds projected text/count/metadata. It preserves Unicode, atomic structured rows, section/source spans and uncertain OCR/formula-cache flags. Text is not normalized, silently split by tokenizer or truncated. A wholly empty source may produce an explicit zero-point generation; whitespace-only nonempty chunks fail admission.

The plan contains immutable records and canonical serialized metadata. Generation SHA256 binds source identity, model fingerprint, collection and the complete ordered projection hash; UUIDv5 job/point IDs make retries deterministic. New source/hash/owner/namespace/processor/byte policy/content/metadata/order produces a new generation. The complete Qwen candidate/precision/pooling/runtime package contract must match its fingerprint. Payloads carry private trusted scope, provenance, `pending` state and uncertainty; raw source text is kept separately for embedding and is not placed in vector payloads or logs.

`validate_source_fence(plan, row)` rejects missing, foreign, moved-root, deleted, nonready or changed-hash metadata. This helper itself does not lock a database row; T02/T03 must call it inside the correct transactions. Passing a stale in-memory snapshot is not publication acceptance.

`preflight_plan(plan)` runs `scripts/qwen_ingestion_preflight.py` in a separately locked uv environment. One nonqueued slot per API process; busy429. The worker verifies the pinned artifacts, uses actual official local-only Qwen tokenizer/left-padding/unprefixed document formatting and refuses empty or>512 tokens including special tokens. It returns complete counts plus model fingerprint; replies with foreign identities, missing counts or unexpected fields fail closed. No weights are loaded into an embedding model; no GPU session or service is started. The isolated dependency environment includes the same CPU package versions as the approved model comparison and does not change project packages.

Request≤8 MiB, text≤1 MiB,≤1000 passages, response≤16 KiB,90-second parent wall timeout,60/61-second child CPU and4 GiB child virtual-address limit. Address-space limit is not measured resident RAM. Parent uses a new process group; timeout/interruption kills and joins the owned group before releasing the admission slot. Input uses stdin, not process arguments or logs. Environment excludes Vault/DB/API/Hub/proxy credentials and disables implicit Hub tokens/network downloads/GPU. Missing runtime/artifacts or unexpected worker failures return a fixed503; valid token overflow returns422. No partial counts authorize a subset.

Reprovision isolated dependencies only from the checked-in lock; cached execution is offline:

```sh
uv sync --offline --script scripts/qwen_ingestion_preflight.py --frozen
LOCAL_ASSISTANT_EMBEDDING_COMPARE_LIVE=1 uv run --no-sync pytest tests/test_ingestion_contract.py tests/integration/test_ingestion_preflight.py -q
```

Models were already explicitly provisioned under the owner's previous authorization; this command never downloads weights. The source-service caller must offload this synchronous subprocess operation through joined file work rather than block the event loop; that integration is now implemented in T03 through joined file work.

## Acceptance checkpoints

| Milestone | Dependency and concrete gate | State |
|---|---|---|
| D25-T01 | Deterministic trusted plans, source/model fences, actual512/513 token boundaries, process/admission/privacy tests | **PASS local scope**;58 new unit+3 actual tokenizer cases, full870 PASS/0 SKIP |
| D25-T02 | Reviewed V003/V004 journal, protected seven-/nine-table restores including column ACLs; source-locked admission/replay, bounded leases/retries, generation pointers, tombstones and real transaction/race tests | **PASS local repository/schema**;44 new cases, full914 PASS/0 SKIP; [journal specification](INGESTION_JOURNAL.md) |
| D25-T03 | Opt-in bounded Qwen embedding worker, isolated owned Qdrant generation, complete upsert acknowledgement/retry, final source fences, update/delete cleanup, cancellation/shutdown/crash recovery | **PASS local opt-in**;65 new cases across T03, full979 PASS/0 SKIP |
| D25 acceptance | Actual incremental ingest/update/delete and crash/retry consistency, token/resource/ACL/point/source/count/hash gates, production-path identity and full regression | **PASS local opt-in**; actual crash/reclaim, source replacement/delete, lost acknowledgements and repeat late-write cleanup; no production rollout |

T02/T03 priority P1; estimate multiple milestones. Main risks are distributed commit gaps, lease resurrection, stale/deleted publication, ACL leakage and destructive rollback. No new feature beyond existing D25 scope is being scheduled. Keep E5/source/auth/root identity intact and use the ADR-033 rollback policy: stop admission, drain/fence workers, retain journals/generations and use forward repair instead of dropping populated state.

Observed acceptance: [T01 evidence](../evidence/d25-t01-ingestion-admission.json), focused117 PASS/19.98s and full Vault-backed870 PASS/114.48s,0 SKIP. Original D24 and selected Qwen/E5 rollback/registry remain unchanged. This is the historical T01 checkpoint; T02 progress is documented in the journal specification. No whole-Day PASS is claimed.

## T02 follow-up

**Purpose:** Link the new durable repository without claiming vector-worker acceptance.

[ADR-034](../ADR/034-durable-ingestion-journal.md) and [journal specification](INGESTION_JOURNAL.md) describe applied V003/V004, fresh protected backup/restores and actual app-role transaction tests. Desired/active pointers, live-lease/latest-source publication, bounded retry and durable cleanup obligations now exist in PostgreSQL. They contain no source text/vectors. At the historical T02 checkpoint no worker drove them; T03 now supplies the default-disabled worker/API described in the operating guide.

T02 observed acceptance on2026-10-19: full914 PASS in120.13s,0 SKIP; revision0004, protected seven-/nine-table restore verified including column ACLs. [Acceptance](../evidence/d25-t02-journal-acceptance.json) and [post-audit](../evidence/d25-t02-post-audit.json) retain the result. T03 is NEXT; no whole-Day PASS or deployed vector worker.

## Final D25 checkpoint — 2026-10-19

**Purpose:** Supersede earlier incomplete milestone statuses with actual verified acceptance.

T03 implements source-held reconstruction/encoding, exact owned vector verification/activation, lease-fenced publication and repeated terminal repair including cleanup already acknowledged. API cancellation, shutdown and hard parent death join or reap owned work; real worker SIGKILL/reclaim retains deterministic IDs. Final979 PASS in162.02s,0 SKIP; clean SQL/source/vector/process/lock post-audit. D25 PASS locally; D26 NEXT. No production collection, model switch, source mutation or new schema after0004.
