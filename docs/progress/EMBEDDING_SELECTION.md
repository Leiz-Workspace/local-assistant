# D24 embedding selection and private vector design

**Purpose:** Record the reproducible local embedding tradeoff, pinned choice and collection lifecycle boundary from ADR-031.

Priority P1 depends on D22 source-bound chunks/access metadata and D23 pipeline evidence. Effort one or more milestones; reviewed risks are weak Vietnamese/cross-language retrieval, byte/token mismatch, silent truncation, runtime/model drift, CORE GPU contention, stale vectors and mixed-owner data. [ADR-031](../ADR/031-cpu-embedding-selection-and-vector-schema.md) was recorded before dependency/model/probe changes. No production API, ingestion worker, permanent collection or source schema is added in this milestone.

## Frozen evaluation and measured choice

**Purpose:** Compare real local quality/resources without changing relevance labels after seeing scores.

[The handwritten synthetic corpus](../../tests/fixtures/embedding/retrieval.json) contains20 related passages and40 Vietnamese/English/cross-language queries with exact independent relevance. It is separate from D23 reconstruction fixtures. Gates were frozen before measurement: Recall@3≥0.90, MRR@10≥0.80, group Recall@3≥0.80, peak child RSS≤2048MiB and warm single-query p95≤500ms. Among eligible candidates choose minimum measured RSS within0.05 MRR of the best eligible model. The [retained report](../evidence/d24-embedding-selection.json) records all query ranks/top3/misses, corpus hash, candidate/artifact/runtime identities and resource metrics, without passage/query text or vectors.

| Official pinned ONNX int8 AVX512-VNNI candidate | Recall@3 / MRR@10 | Group Recall@3 cross/en/vi | Peak child RSS | Warm query p50/p95 | Cold local load | Gate |
|---|---|---|---|---|---|---|
| multilingual-e5-small,384 dimensions |0.750 /0.655377 |0.500 /0.9375 /0.6875 |558.156MiB |2.051/2.409ms |648.092ms | Ineligible: quality |
| multilingual-e5-base,768 dimensions |0.925 /0.874405 |0.875 /1.000 /0.875 |802.863MiB |6.321/7.378ms |888.308ms | Eligible; selected |

The historical D24 choice was **intfloat/multilingual-e5-base**, revision `d128750597153bb5987e10b1c3493a34e5a4502a`, official ONNX qint8 AVX512-VNNI artifact SHA256 `2523551878658b305550d8759443822dbfda9ed9c8012ef2c354ba2c5b9de503`, tokenizer SHA256 `62c24cdc13d4c9952d63718d6c9fa4c287974249e16b7ade6d5a85e7bbb75626`. Model+tokenizer bytes295769071; smaller candidate135429554 bytes. Full asset pins and source revisions are in [candidates](../../configs/embedding-candidates.json); [preserved D24/E5 rollback config](../../configs/embedding-e5-rollback.json) is `selected_not_deployed`. The current [selected config](../../configs/embedding-selected.json) now pins owner-approved Qwen after the separate MODEL-EVAL-001 comparison; neither is an enabled service. The fingerprint also binds exact installed ONNX Runtime/tokenizers/NumPy versions, preprocessing and runtime format. No upstream remote Python code, Torch/CUDA stack or private Hub credential is used.

Base still misses top3 on `delete-en` (rank6), `ocr-vi` (rank7) and `embedding-vi` (rank11); these remain in the report. Small's lower RAM/latency does not compensate for failing frozen quality gates. This20/40 synthetic corpus is a local selection gate, not a general Vietnamese/MTEB accuracy claim or proof that the selected model is globally best. Int8 quality is measured directly, not inferred from full-precision upstream benchmarks. Expand independent retrieval coverage during D26/D27; do not relabel observed misses as success.

## Runtime, token policy and reproducibility

**Purpose:** Specify exact embedding semantics and resource observations for later ingestion work.

The existing Ryzen7 7700 has AVX512-VNNI/16 logical CPUs and approximately30GiB RAM; existing RTX4070Ti SUPER/CORE leaves approximately5GiB free VRAM at initial inspection. Benchmark each candidate in a fresh credential-free process, CPUExecutionProvider only,2 intra-op threads/1 inter-op thread/sequential execution, batch≤4. This keeps CORE's GPU workload in place; no inference service/container is started or restarted. Child wall180s/CPU120–121s/virtual memory4GiB are bounds for this trusted synthetic drill; measured peak RSS is per child, not parent/cumulative RSS. Latencies are observed on short queries after warmup, not load SLOs or long-context throughput. Passage encoding20 records took60.812/167.112ms for small/base; network download time is excluded from cold local load.

[Official E5 instructions](https://huggingface.co/intfloat/multilingual-e5-base) specify `query: ` and `passage: ` prefixes even for non-English text, attention-mask mean pooling and L2 normalization. Use Cosine distance and512 total tokens including prefixes/special tokens. The benchmark uses the actual pinned [tokenizer API](https://huggingface.co/docs/tokenizers/api/tokenizer), explicitly disables truncation/padding and builds attention masks itself. Empty/over32768-byte lexical input and over512-token input are refused. Both candidates reject the measured overflow probe, repeat identical vectors for the same query and have unit-norm max error about5.96e-8. Maximum corpus passage/query lengths45/24 tokens are short; long-context accuracy/performance is not certified. [ONNX Runtime](https://onnxruntime.ai/docs/api/python/api_summary.html) uses only the explicit CPU provider; runtime dependencies are dev/benchmark-only uv-locked onnxruntime1.31.0/tokenizers0.23.3 plus flatbuffers25.12.19/protobuf7.36.2.

D22's256–8192 UTF-8-byte chunk budget does not guarantee512 tokens. D25 must count the actual prefixed token input before submitting work; overlong text/atomic rows fail closed until a separately versioned source-preserving fragment policy is designed. Do not silently truncate or mark a partially embedded generation active. Existing nested-table422, row-size413, stale-cache and OCR/VLM review limits stay in effect.

Provision explicitly, then measure from `ai/`:

```sh
uv run python -m scripts.embedding_acceptance --download --output benchmarks/results/d24-embedding-selection.json
uv run python -m scripts.embedding_acceptance --output docs/evidence/d24-embedding-selection.json
```

Without `--download`, missing/mismatched artifacts fail safely; tests never silently download. Public assets are stored in ignored `models/embedding/<candidate>/`, pinned by size/SHA and atomically published only after verification; partial downloads are removed. Reuse of valid cache rechecks exact hash. A runtime/package/model/tokenizer change invalidates the fingerprint and requires a new measured collection generation. Upstream cards [small](https://huggingface.co/intfloat/multilingual-e5-small)/[base](https://huggingface.co/intfloat/multilingual-e5-base) declare MIT; retain their attribution/license provenance for any future distribution. This milestone keeps weights outside Git/source archive.

## Existing Qdrant design probe

**Purpose:** Prove proposed schema/index compatibility while preserving shared instance data.

The selected plan uses named vector `dense`,768 dimensions/Cosine/on_disk=true,1 shard/replica and full model fingerprint in the proposed collection name. Ten indexes cover owner UUID with `is_tenant=true`, namespace/file UUIDs and source SHA/chunk/chunker/processor/model/generation/state keywords. Native visibility/untrusted/locators/spans/section/quality metadata is described in ADR-031; source text, secret keys and caller ACL assertions are excluded. Qdrant keys protect the shared instance, not individual tenants; trusted owner/namespace/generation filters and final PostgreSQL source/ready/hash revalidation remain mandatory. These choices follow [Qdrant collection](https://qdrant.tech/documentation/manage-data/collections/) and [multitenancy](https://qdrant.tech/documentation/manage-data/multitenancy/) contracts.

[Retained probe evidence](../evidence/d24-qdrant-design.json) records actual Qdrant1.18.2 accepting vector schema and all10 indexes including UUID tenant params. It created only a fresh random `la_d24_probe_...` empty collection, verified zero points/schema/indexes, then removed that exact acknowledged-owned probe. Existing collection count was0 and inventory fingerprints before/after are identical. No permanent user/index collection or vector point was created. The probe refuses name collision and never mutates/deletes existing names; creation errors are not treated as ownership. If a create acknowledgement is lost, fail the probe and audit the explicit probe namespace before any manual cleanup; do not infer ownership of unrelated collections. No automatic destructive repair.

`probe_design()` accepts a key delivered from existing Vault `secret/server/qdrant/admin` in parent memory; tests use `LOCAL_ASSISTANT_QDRANT_PROBE_KEY` supplied by the Vault regression wrapper. No key is passed in arguments/printed/retained; loopback6333, environment proxies/redirects disabled, bounded replies/timeouts and sanitized error bodies. Unit tests prove cleanup after acknowledged create/index/schema failure, collision refusal and unchanged shared inventory. Full live tests run an actual owned empty probe. Rollback removes only owned probes/dev tooling and preserves source/auth/root/shared services.

## D25 handoff

**Purpose:** Separate measured model/design acceptance from unimplemented durable ingestion and authorization.

D25 must record an ADR for durable journal/outbox/schema/worker changes before implementation. Job idempotency binds trusted owner/namespace/file/source SHA/chunker/model/index generation; point UUIDv5 includes the same scope. Verify ready/hash before embedding and before publication. Pending generations are invisible until all required points are written and final source checks pass. PostgreSQL and Qdrant have no shared atomic transaction: track crash/retry/reconciliation explicitly, hide deleted sources immediately in PostgreSQL, and revalidate every future retrieval against it while vector cleanup retries. Immutable source replacement/reindex builds a new generation, then switches and retires old points without cross-owner adoption.

Design still needs durable lifecycle acceptance for cancellation/shutdown/backpressure, token overflow/error reporting, quota/resource cleanup, stale update/delete, idempotent retries and rollback. D26 search adapter/ACL filtering and D27 retrieval/reranking evaluation remain separate gates. This milestone does not add automatic indexing/model-context, public vector access or generated-output persistence.

## Observed acceptance — 2026-10-18

**Purpose:** Record actual validation without equating design acceptance with production ingestion.

Final Vault-backed regression **783 passed in95.11s**,0 skips/exclusions, real PostgreSQL/CORE/Qdrant.35 new cases:33 independent scoring/pooling/token/artifact/selection/probe-ownership negatives and2 actual pinned CPU/owned-Qdrant drills. Focused35 passed in3.03s. Ruff correctness/import/format6 Python files,44 function/class descriptions, uv lock, artifact/corpus/report/config fingerprint/privacy and diff checks pass. Post-test file quota `(0,0,0)`, restore probes0, Qdrant collections0/remaining D24 probes0; shared services remain running. D24 PASS only for this measured local selection/design scope. D25 remains NEXT.

## Subsequent owner-approved selection — MODEL-EVAL-001

**Purpose:** Preserve D24 history while accurately identifying the current selected model.

The subsequent [Qwen/E5 comparison and transition review](QWEN_E5_COMPARISON_AND_TRANSITION.md) measured Qwen R@3/MRR@10=0.975/0.968750 versus E5=0.925/0.874405 with higher CPU latency/RAM. The owner approved Qwen selection. Current configuration uses official pinned Qwen3-Embedding-0.6B BF16 CPU,1024 dimensions, instructed query/plain documents/last-token L2,512-token cap, and status `selected_not_deployed`. Exact pins and [approval audit](../evidence/model-eval-001-selection-approval.json) are recorded separately from original D24 evidence. CPU RAM, not VRAM, was measured. E5 rollback configuration/artifacts remain preserved. D25 must implement and validate the Qwen ingestion adapter/lifecycle; D26 retrieval remains future work.

## D25 final local lifecycle — 2026-10-19

**Purpose:** Record the accepted T03 integration and supersede earlier open-worker status without rewriting historical results.

D25 now passes the local opt-in source/Qwen/Qdrant lifecycle with979 PASS/0 SKIP. The approved selected JSON/hash, model profile/runtime, exact E5 rollback and original D24 evidence are unchanged by T03. Separate frozen offline encoder, owned vector adapter and source-held journal worker are implemented; flags remain disabled, no production collection or model routing enabled. Selection status remains `selected_not_deployed`. D26 retrieval is NEXT; no automatic fallback/replacement. See [acceptance](../evidence/d25-ingestion-acceptance.json) and [operating guide](INCREMENTAL_INGESTION.md).

## D26 local retrieval checkpoint — 2026-10-19

**Purpose:** Record separately verified source-revalidated retrieval while preserving earlier model/indexing acceptance.

D26 local opt-in dense retrieval now passes1030 PASS/0 SKIP. Query instruction and complete token budget come from the unchanged approved Qwen profile; original query bytes enter the existing empty-prefix passage worker through shared encoder admission. No second model/runtime, download, dtype, fallback or selected-configuration edit. Actual source/SQL/Qdrant/HTTP tests are lifecycle acceptance, not an expanded model-quality benchmark. D27 original reranker candidate remains planned; [guide](RETRIEVAL.md).

## D27-T01 diagnostic baseline — 2026-10-19

**Purpose:** Record new evaluation of the existing model without changing model selection or evidence scope.

Frozen24-document/36-query agent-authored corpus: R@3=.972222/MRR@10=.949074/nDCG@10=.961613; actual existing CPU encoder plus evaluation-only vector replay through source/SQL/Qdrant/D26. Full1052 PASS/0 SKIP; candidate/label/source hashes and misses retained. Batch/cache scores/timing are not singleton API latency or independent production quality. No selected-config/profile/runtime/dependency/vector-space change, new RAM/VRAM measurement or model download/adoption. D27-T01 PASS local measurement; D27 open, T02 original reranker NOT EVALUATED. [Plan](D27_RETRIEVAL_EVALUATION.md), [evidence](../evidence/d27-retrieval-baseline.json).

## D27-T02 original reranker comparison — 2026-10-19

**Purpose:** Distinguish evaluation of the agreed ranking candidate from unchanged embedding selection.

Original Qwen3-Reranker-0.6B provisioned/evaluated offline; batch1 CPU attempts incomplete, explicit batch4 variant completed three diagnostic rounds, full1096 PASS/0 SKIP. [Comparison/resource definitions/failed profiles](D27_RERANKER_COMPARISON.md) and [review proposal](D27_RERANKER_ADOPTION_REVIEW.md). No embedding/profile/precision/fingerprint/vector-space/collection/data change or ranking integration; approved embedding and byte-exact E5 rollback retained. Diagnostic scores do not authorize model/routing changes. D27 open, T03 independent/adoption review NEXT.

## D27 final local evaluation follow-up — 2026-10-19

**Purpose:** Link final actual evaluation while preserving this document's original frozen measurements.

[Final decision](D27_RERANKER_EVALUATION_DECISION.md) retains approved dense retrieval and the original reranker nomination without adoption/model/routing changes. Owner delegated relevance tasks to AI; no human review fabricated. Three new actual paired rounds show equal answerable quality on the separately frozen limited v2 diagnostic. ASGI/CORE and actual loopback TCP/source/lifecycle/rollback pass;1234 full+16 new AI-focused+1 TCP PASS/0 SKIP (1251 unique tests across checkpoints, not one full invocation). Original gains, failed runtimes, inputs/profiles/thresholds and exact E5 rollback unchanged. D27 local evaluation PASS; D28 NEXT.
