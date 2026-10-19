# D27-T03 — Reranker adoption review proposal

**Purpose:** Make the original candidate's measured benefit, cost, migration/rollback and missing evidence reviewable without changing routing.

**Status:** Proposal only. D27-T02 local batch4 measurement accepted after1096 PASS/0 SKIP; T03 review/integration remains a proposal. No model selection, production integration or owner adoption approval.

## Concrete option under review

Preserve approved Qwen3-Embedding-0.6B CPU/1024 and the existing dense/source-revalidated path. Consider adding the original Qwen3-Reranker-0.6B as a separate optional stage only after review, using exact official revision e61197ed45024b0ed8a2d74b80b4d909f1255473 and the explicitly measured CPU BF16 batch4 profile. This is an additional ranking stage, not an embedding/vector-space replacement. Original batch1 configurations failed to complete within480s CPU over the full three-round benchmark; their failures are part of the evidence.

On the frozen24-document/36-query authored diagnostic corpus, full/focused batch4 reranking improved R@3 from.972222 to1.0, MRR@10 from.949074 to1.0, nDCG@10 from.961613 to1.0, with R@10 fixed1.0 and no group regression. Three old rank6/rank2 misses become rank1. The data is small/agent-authored/correlated; perfect scores do not establish production quality. Independent human-reviewed relevance and broader numeric/keyword/multiformat/noisy/ambiguous coverage remain unvalidated. The focused descriptive paired query-bootstrap95% interval for nDCG gain is[0,.094657], including0; correlated authored queries do not establish a statistically generalizable improvement. Do not relabel the current corpus after scores; new coverage needs a new version and paired rerun.

Final measured runtime cost: peak candidate RSS≈1596.055MiB RAM, no candidate GPU allocation; fresh-process artifact/model initialization≈2.300s (filesystem cache uncontrolled) and loaded-model ten-pair query p95≈2.239s. Timing excludes embedding/retrieval/HTTP and cold load. It cannot be added to cached T01 p95 and presented as a measured end-to-end SLO. Co-resident/persistent encoder+reranker RAM and sustained CORE contention, long-pair correctness/performance and production singleton request latency are not measured.512 is an input acceptance cap, not demonstrated quality at all512-token inputs.

## Proposed T03 gates and scope

P1; dependencies complete T02 evidence, independent relevance review and owner decision. Initial effort1–2 milestones if integration is authorized. Risks: synthetic overfitting, CPU/RAM latency, stale/foreign delivery during model delay, token overflow, lifecycle contention and misleading confidence.

1. Freeze a separate independently reviewed corpus/split and paired baseline/candidate plan before inference. Evaluate near-topic, absent-answer, exact numeric/version/identifier and mixed-document cases, retain misses and uncertainty. Keep current diagnostic artifacts immutable.
2. Measure actual singleton end-to-end query/admission/model/source/delivery and sustained concurrent-service costs, complete512/513 pair behavior and resource/cancel/death/shutdown; original profile/quality gates remain explicit. Separate model/runtime variants, cold/warm, mean/p95 and RAM/VRAM/disk definitions.
3. If integration is approved, write an ADR before source/API/worker changes. Keep a default-off ranking setting, no automatic routing/fallback/model choice. Use only trusted source-rehydrated candidates, bounded top10, exact hash/owner/root/active-generation before and after the ranking delay, complete pair accounting and retained source readers through delivery. Scores remain untrusted ranking signals, not confidence or instructions.
4. Model admission must prevent unwanted overlap with embedding, bound CPU slots/queue/deadline, and retain exact parent supervision/process cleanup. No broadening DB/Vault/Qdrant grants or adopting foreign collections. Existing file/journal/root/quota and source identity contracts remain authoritative.
5. Migration retains embedding fingerprint/dimensions, point/source/generation identity and current ownership; reranking does not require reindexing or destructive DB/vector migration. Before any enablement, retain exact baseline configuration and owned state. Disable/drain the optional ranking stage to restore dense ordering; do not delete model/data/source/journal/collections as rollback. Reindex only if a future separately approved embedding change requires it.

Possible decisions: defer for evidence, keep dense baseline, or authorize a separately scoped local opt-in integration after missing gates. Successful benchmark scores alone do not authorize adoption. D27 remains IN PROGRESS and D28 is not started; no candidate has replaced the registry model lineup or current selected configuration.

[Actual comparison](evidence/d27-t02-reranker-comparison.json) and [T02 acceptance](evidence/d27-t02-acceptance.json) retain raw class logits/counts/query timings/three repetitions, execution identities and failed batch1 attempts. No adoption decision is implied by the local test result.

## T03 review preparation follow-up

[Independent review packet and protocol](D27_INDEPENDENT_RELEVANCE_REVIEW.md) now make64 unlabeled pairs on a new8/8 authored challenge reviewable without model scores. Human judgments remain pending. A separately frozen resource-only probe uses original diagnostic inputs and meaningless512-token stress input, not this new challenge. These preparations do not authorize integration or satisfy HTTP/concurrent-service or independent quality gates. See T03 evidence and dev log for actual checks/results; original T02 measurements and failed attempts remain immutable.
