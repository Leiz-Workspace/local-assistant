# ADR-038 — Freeze retrieval judgments before measuring baseline or reranker

**Purpose:** Define D27-T01 evaluation identity, actual baseline replay and remaining candidate gates before scoring.

**Date:** 2026-10-19
**Status:** T01 accepted for local frozen diagnostic baseline after1052 PASS/0 SKIP. D27 IN PROGRESS; actual candidate comparison/adoption remains open.

P1; depends on accepted D26, approved Qwen embedding and source/generation/ACL fences. Initial effort1–2 evaluation milestones. Risks: author bias, small-corpus ceiling, inaccurate relevance labels, candidate changes, runtime/resource confounding and unsafe model cutover.

## Frozen T01 contract

Author a new24-document/36-query synthetic corpus before running inference, separate from D24's20/40 corpus. Twelve topic pairs have near-topic hard negatives, Vietnamese/English/cross-language groups and explicit binary relevance judgments. This is agent-authored diagnostic data, not human-blinded or a held-out production sample. Freeze exact UTF-8 bytes/labels/groups/input policy/thresholds and hash them into the plan before first score. Never edit labels/text/thresholds after seeing scores; revisions need a new version and paired rerun. Every document fits one unchanged256-byte source chunk; reject deviations rather than repair source.

Run the actual pinned CPU encoder once over the exact corpus passages plus fully instructed queries using the unchanged D25 worker. Validate complete tokenizer counts/fingerprint/unit vectors; reuse only those real vectors for deterministic source job processing and query replay. Reuse is confined to this evaluation harness, never production injection or invented vectors. Real immutable source upload/admission, actual Qdrant writes, D26 ACL query/SQL active generation/rehydration/final source checks still execute. Replay frozen query vectors twice and retain per-query complete top10 IDs/scores/source hashes/point identities and misses. A second private owner stores the same text as a relevant document, making ACL isolation necessary even for a perfect semantic match.

Report batch encoder wall time separately from cached-query retrieval/rehydration latency. These replay latencies exclude per-request model startup/tokenizer inference and HTTP serialization/network; they are not interactive end-to-end latency or production SLOs. Do not infer warm embedding p95/RAM/VRAM from parent timing or inherited RSS. Earlier actual model resource evidence remains historical; unmeasured T01 resource fields remain null. No model download, default routing, precision/schema/dependency/service configuration change.

Metrics: binary Recall@3/5/10, MRR@10, nDCG@10 (binary gain/log2 discount), per-group metrics and exact per-query ranks. Missing relevant documents are rank=null, reciprocal rank0; candidate duplicates/unknown IDs/nonfinite/unsorted scores fail protocol. Macro-average queries, deduplicate no source silently (one chunk per document required). Bootstrap95% percentile intervals use a fixed seed and2000 query resamples, descriptive only because the36 queries share12 intents.

T01 acceptance requires complete protocol/corpus/token/source/ACL/replay verification and truthful reporting; low quality is retained and does not authorize repair. Prespecified diagnostic warning gates are Recall@3>=0.90, MRR@10>=0.85 and each group's Recall@3>=0.80. A quality warning does not turn a valid measurement into an implementation failure. T01 PASS is not D27 PASS.

## Candidate comparison contract

The original Qwen3-Reranker-0.6B remains the candidate. T02 must pin exact official revision/artifact hashes/license/runtime, resource budget and a separate isolated environment before provisioning. Use documented model-specific instruction/chat formatting and yes/no logits; do not apply embedding pooling. Official examples truncate pairs; this project must count complete pair+prompt/suffix/special tokens and reject overflow instead. Initial comparison budget512 tokens/pair, CPU-only/batch1/two threads, max4GiB measured child RSS/zero GPU, max60s wall/query for ten candidates; these are proposed gates, not observations.

Compare the same frozen top10 candidates with original source bytes and relevance. Retain baseline order; reranker may only reorder that set, using stable document ID for exact score ties. Require no foreign/stale/source/hash leakage or missing/duplicated candidates, no Recall@10 loss, macro Recall@3 and MRR@10 nonregression, each group's Recall@3 loss<=0.05 and nDCG@10 improvement>=0.02 before recommending adoption. A perfect baseline or tiny/no gain means inconclusive/keep baseline; do not alter judgments to produce an improvement. Small synthetic results alone never justify production cutover; independent human-reviewed corpus and sustained latency/resource measurements remain gates.

Candidate provisioning/evaluation and any adoption are separate from this T01 baseline. No model has been downloaded or selected by this ADR. Any agreed-model/routing change still requires owner approval after evidence, performance/resources, compatibility, migration/rollback review. D28 stays later work until D27 acceptance actually completes.

Primary protocol reference: [official Qwen3-Reranker model card](https://huggingface.co/Qwen/Qwen3-Reranker-0.6B). Its published scores/context/license describe the model, not measurements on this host.

## Observed T01 acceptance — 2026-10-19

**Purpose:** Record verified baseline facts without promoting the unmeasured candidate.

Corpus/plan hashes stayed exact before/during both runs. Focused22 PASS/89.34s; final full1052 PASS/306.02s,0 SKIP, actual CPU/source/SQL/Qdrant path. R@3/R@5=.972222, R@10=1, MRR@10=.949074, nDCG@10=.961613; both replay orders stable, identical-text foreign source excluded, full/focused metrics equal. Retained query-q2 rank6, owner-q1 and vision-q1 rank2. Raw source bindings and every candidate hash match frozen corpus bytes. Diagnostic gates met; no baseline tuning, human-independent/general quality or model adoption claim.

Source code of D25/D26, selected model/registry/E5 rollback, project/runtime locks, schema0004 and existing grants/owners/ACLs unchanged. Post-audit jobs/heads/files/quota/probe DBs/collections/encoders/advisory locks0. Official public candidate metadata/config only reviewed; no weights/tokenizer assets downloaded/executed. The exact pinned config positions40960 and card32K discrepancy is retained; neither is a host-tested long-context result. Proposed T02 gates remain proposals, with no measured candidate RAM/VRAM/latency/scores. [Baseline](../evidence/d27-retrieval-baseline.json), [acceptance](../evidence/d27-t01-baseline-acceptance.json), [plan and remaining gates](../progress/D27_RETRIEVAL_EVALUATION.md).
