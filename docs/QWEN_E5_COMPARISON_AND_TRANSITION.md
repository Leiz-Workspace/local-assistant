# MODEL-EVAL-001 — Qwen/E5 results and transition proposal

**Purpose:** Preserve measured Qwen/E5 results and the reviewed migration/rollback, then record the owner-approved selection separately from deployment.

**Historical preapproval state (superseded by the applied-selection record below):** Authorized offline benchmark completed; production/index-throughput work and cutover are pending separate approval/implementation. D24/commit `a88584b` remain unchanged; D25 durable ingestion is not implemented. The original registry Qwen nomination is preserved. The owner's latest “Làm đi” authorized Qwen download/comparison following the explicit benchmark proposal; it did not authorize an automatic cutover or changes to Docker/Vault/database/current collections.

## Actual comparison

**Purpose:** Report results without substituting upstream claims or hiding precision/resource differences.

[Retained six-run evidence](evidence/model-eval-001-qwen-e5-comparison.json): three fresh processes per candidate, identical frozen D24 corpus SHA and input manifest,20 exact passages/40 queries/relevance labels, cosine scores, deterministic ties and no reranker. Each passage is the same unchanged single source unit used in D24; this is not a new production chunk-ingestion run. Query/source inputs were not tuned after results. Per-query top10/relevant ranks and Vietnamese/English/cross-language metrics are retained; raw text/vectors/credentials are excluded.

| Metric | Preserved E5-base int8/ONNX CPU | Official Qwen3-Embedding-0.6B BF16/PyTorch CPU |
|---|---|---|
| Dimensions |768 |1024 |
| Recall@3, all three runs |92.5% |97.5% |
| Recall@5, all three runs |92.5% |100% |
| Recall@10, all three runs |97.5% |100% |
| MRR@10, all three runs |0.874404762 |0.96875 |
| Group R@3 cross/en/vi |87.5% /100% /87.5% |100% /100% /93.75% |
| Peak RSS across repetitions |802.688–803.305MiB |1317.816–1318.086MiB |
| Warm single-query p95, repetitions |6.290–6.744ms |97.222–113.928ms |
| Warm single-document p95 |10.406–13.358ms |98.027–100.061ms |
| Batched document encoding throughput |120.072–122.644 passages/s |14.983–15.771 passages/s |
| Cold local load including hash checks |921.824–958.977ms |2189.158–2211.451ms |
| Model/tokenizer/config artifact bytes |295769071 |1203020554 |
| GPU allocation |0, CPU-only provider |0, CPU-only PyTorch build |
| Flat20-vector float32 storage |61440 bytes |81920 bytes |
| Rankings stable / overflow rejected |Yes /yes |Yes /yes |

**Recommendation: propose Qwen as the selected embedding model**, consistent with its original registry nomination and improved quality on this local corpus. It improves R@3 by5 percentage points and MRR@10 by about0.09435, while using about515MiB more peak RAM and substantially more CPU time. Both meet the frozen D24 reference quality/resource gates in this drill; the MRR gap exceeds D24's0.05 quality tolerance. This is an evidence-backed proposal, not an applied replacement or a universal claim that Qwen is better. Qwen BF16/PyTorch and E5 int8/ONNX differ in precision/runtime; this is a deployment-configuration comparison, not a controlled same-precision model-only ablation.

E5 top3 misses remain `delete-en` rank6, `ocr-vi` rank7, `embedding-vi` rank11. Qwen still misses `embedding-vi` at rank4: its top3 is not perfect, despite R@5/10 reaching100% on this small corpus. No general multilingual/MTEB/production-load/long-context accuracy is certified. Expand independent retrieval evaluation at D26/D27.

Only flat in-memory index copy/matrix-product measurements were performed; the raw report retains their actual build/query times and bytes, explicitly labeled. **Qdrant ingestion throughput and on-disk index size are NOT MEASURED**, not0 or a guessed estimate. No Qdrant/Vault/DB/Docker operation was performed in this evaluation. Persistent vector payload/HNSW/generation overhead must be measured in separately authorized D25 integration. Raw vector byte growth768→1024 is33.3%; it is not an estimate of total Qdrant disk usage.

## Artifacts, preprocessing and resource isolation

**Purpose:** Make the comparison reproducible while preserving existing project/model state.

Qwen uses official `Qwen/Qwen3-Embedding-0.6B` revision `97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3`, Apache2.0, pinned safetensors/tokenizer/config hashes in [evaluation config](../configs/embedding-qwen-evaluation.json). Model SHA `0437e45c94563b09e13cb7a64478fc406947a93cb34a7e05870fc8dcd48e23fd`. Assets were downloaded explicitly and verified in ignored `models/embedding/qwen3-embedding-0.6b-bf16-cpu/`; E5 assets remain untouched. A community ONNX conversion was inspected as an option but was **not downloaded or benchmarked**; no results for that conversion are claimed.

The [official Qwen instructions](https://huggingface.co/Qwen/Qwen3-Embedding-0.6B/blob/97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3/README.md) require an instructed query and no document instruction. The exact upstream default is frozen as `Instruct: Given a web search query, retrieve relevant passages that answer the query\nQuery:` plus query. Qwen uses left padding and final attended-token pooling, converted to float32 and L2-normalized. E5 retains its own `query: `/`passage: ` prefixes and masked mean/L2 contract. Do not reuse E5 preprocessing for Qwen.

Both configurations run2 intra-op/1 inter-op threads, batch≤4 and common512-token input cap including prompts/special tokens. Preflight refuses overflow rather than truncating source text. Official Qwen model config declares32768 context tokens, while tokenizer metadata is not the model context authority; this short512-common-cap benchmark does not validate32K operation. CORE was not stopped/reconfigured and neither worker uses GPU. CPU usage/latency observations are local, not SLOs.

Qwen dependencies use a separate [uv script](../scripts/qwen_embedding_worker.py) and [script lock](../scripts/qwen_embedding_worker.py.lock): torch2.10.0+cpu, transformers4.57.6, numpy2.5.4, tokenizers0.22.2 and safetensors0.8.0. The lock includes exact transitive wheels/sources. Project pyproject.toml/uv.lock and the E5 runtime remain unchanged (onnxruntime1.31.0/tokenizers0.23.3/numpy2.5.4). An initial typing-extensions4.16 wheel failed metadata validation; the isolated script now pins4.15.0 and sync succeeds. That failed setup is not benchmark evidence.

Workers are launched offline/frozen with an explicit credential-free environment (no Vault/DB/API/Hub/proxy variables),600s wall/480–481s CPU/8GiB virtual-memory hard bounds. Models load from hash-verified local safetensors with remote code disabled/use_cache=false/eval/inference_mode/SDPA. The final retained resource run executes candidates sequentially after tests; an earlier run overlapping test activity is not used as the final timing artifact.

Reproduce only after explicitly provisioning the pinned Qwen assets and isolated dependencies:

```sh
uv sync --script scripts/qwen_embedding_worker.py --frozen
uv run --no-sync python -m scripts.qwen_embedding_comparison --output docs/evidence/model-eval-001-qwen-e5-comparison.json
```

The comparison command does not download missing models. Qwen provisioning reused the existing pinned public-artifact helper with the separate evaluation config; it does not add Qwen to the D24 E5 shortlist or change the selected profile.

## Historical proposal — superseded by approved selection below

**Purpose:** Give the owner a reviewable target instead of an implicit model switch.

[Configuration proposal](evidence/model-eval-001-transition-proposal.json) includes the full proposed Qwen selection and full original E5 rollback selection, guarded by the SHA256 of the current selected file. It has `approval_status: OWNER_APPROVAL_PENDING`, no approver, and is stored under documentation, not an active config path. The proposed model fingerprint is `77a5716028f187821f9e6aa198b5c5774b5d69b54d95093701a7f2dfaaa0bc9b`; proposed named-vector schema is dense1024/Cosine/on_disk in a **new** full-fingerprint collection generation. The old E5 fingerprint remains `e8e395bc1b54979c09466eab46e949c197b99abe2518793612bb0cdc582b02dc` and its768-dimensional space is preserved.

At the preapproval review, the selected file was E5 `selected_not_deployed`. Merely applying a proposed JSON file would not implement an embedding worker or switch a live RAG API; those require D25/D26 code and acceptance. This review approves no runtime model/profile/collection cutover by itself.

Proposed migration after explicit owner approval and separately reviewed D25 implementation:

1. Verify current selected-file SHA, E5 artifacts/runtime/fingerprint and actual collection inventory; take verified protected metadata/config/collection backups if data exists. This document does not claim a new live inventory or backup was taken.
2. Implement/accept the production Qwen adapter and durable ingestion lifecycle under the D25 ADR: bounded admission, cancellation/shutdown joins, source/owner/namespace/hash fences, retries/outbox/generations and model-specific tokenizer preflight. Preserve source/root/auth/registry identity and existing E5 artifacts.
3. Create only an explicitly owned new Qwen collection/generation after schema/fingerprint checks. Never overwrite an existing name or reinterpret E5 vectors. Even a future Qwen output reduced to768 dimensions remains a different embedding space and must not be mixed.
4. Reindex from trusted ready sources with the frozen tokenizer/chunker/model contract. Check complete source/point counts, hashes, UUID point identity, ACL/namespace isolation and token-overflow/error records before activating a generation. No partial, foreign, stale or deleted source may become visible.
5. Validate retrieval quality/latency/resource budgets and actual Qdrant throughput/disk costs; run approved DB/Qdrant lifecycle regression. Abort on incomplete reindex, source mismatch, ACL failure, resource exhaustion or unaccepted quality/latency regression.
6. With approval recorded and exact expected current SHA still matching, atomically update selection/routing to the validated Qwen generation and verify actual worker/API model identity. Retain E5 configuration/collection/generation/weights for rollback; no automatic old-data cleanup.

Rollback: stop new Qwen admissions, join/fence pending workers; restore the exact saved E5 selected configuration/fingerprint and prior collection/generation routing; verify source/owner/hash/ACL and E5 golden behavior. Keep source data/quota/auth unchanged. Retain Qwen partial/completed generations for scoped inspection; delete only explicitly owned resources after a separately approved retention/cleanup decision. Do not delete E5 collections or source files to roll back a model.

## Validation and remaining gate

**Purpose:** Separate offline evaluation evidence from deployment acceptance.

Tests cover exact model-specific prompts/passages,512/513 token preflight, padding-aware last-token pooling, invalid masks/vectors, independent Recall@3/5/10/MRR/group/rank oracles, repetition instability/failed workers, credential-free locked/offline commands, actual Qwen/E5 accuracy/overflow/unit vectors and preserved E5/D24 configuration/evidence. No stateful integration suite was rerun because it would create DB/Qdrant test state outside this evaluation scope; historical783 PASS remains the D24 result, not a new claim.

MODEL-EVAL-001 has completed its offline quality/resource comparison; Qdrant throughput/storage and deployment validation remain open, so it is not marked fully PASS. At the preapproval review, the recommendation and migration/rollback awaited owner approval; the later selection decision is recorded below. D24 remains PASS in its original E5-only scope. D25 remains NEXT, with the proposed Qwen target available for explicit selection approval before ingestion implementation.

Validation completed: **58 tests passed in11.34s,0 SKIP**, including real offline model inference and retained-report/proposal integrity checks. Ruff correctness/import checks and formatting passed on all five added Python files. No stateful service regression was run; D24's783 PASS is historical. The patch remains uncommitted for owner review.

## Owner-approved selection applied

**Purpose:** Record the later owner decision without rewriting the original proposal or benchmark.

The owner replied “Làm đi” after the measured recommendation, migration/rollback review and clarification that Qwen consumes system RAM with zero VRAM in this configuration. This authorizes the proposed Qwen selection. [Approval record](evidence/model-eval-001-selection-approval.json) captures scope, prior/new configuration SHA256 and the preserved rollback path. The original proposal JSON remains unchanged as historical review evidence.

[Selected config](../configs/embedding-selected.json) now pins the exact benchmarked Qwen profile/runtime/fingerprint and1024-dimensional collection design, with status **selected_not_deployed**. [E5 rollback config](../configs/embedding-e5-rollback.json) is byte-for-byte the original selected file; E5 weights and original D24 evidence remain intact. No existing collection, database, source data, Docker or Vault state was touched. There is no D25/D26 production worker/API to switch at this point.

For selection-only rollback, restore the exact E5 rollback file to `configs/embedding-selected.json` and record that decision. Once D25/D26 introduce workers/collections/routing, apply the full drain/fence/restore/validation sequence above instead of treating a JSON copy as live migration. D25 must implement and test the approved Qwen adapter/lifecycle; collection creation, reindex and live routing remain unexecuted.

Approved-selection validation: **59 PASS in11.44s,0 SKIP** including actual offline Qwen identity matching the selected packages/fingerprint/dimensions and exact E5 rollback checks. Ruff checks/format passed. This supersedes the earlier58-test preapproval validation count without rewriting its historical evidence.
