# ADR-040 — Separate batch4 reranker evaluation after batch1 CPU failure

**Purpose:** Record a distinct runtime experiment without relabeling failed batch1 measurements or relaxing frozen budgets.

**Date:** 2026-10-19
**Status:** Batch4 local measurement accepted after1096 PASS/0 SKIP; batch1 CPU failure retained, no adoption authorization.

P1; depends on original-candidate artifacts, unchanged T01 inputs and T02 batch1 failure. Effort one evaluation milestone; risks padded-input numerical differences, peak RAM, throughput assumptions and selective reporting. No application/model-selection/vector/schema change.

Both batch1 attempts failed to complete three repetitions. V2 safely logged exit152 (128+SIGXCPU24) and two completed rounds in242.76s; no complete candidate benchmark exists. Retain both failure logs/source manifests/archives. The original batch1/480s CPU contract is **FAILED/INCOMPLETE**, not silently increased or marked PASS.

Add a separate evaluation-only batch4 profile using the same pinned weights/tokenizer/runtime, CPU BF16/two threads/no KV cache and unchanged query/passage/prompt/labels/top10/order. Ten candidates are processed4+4+2 with left padding and exact attention masks. Count complete real input before padding and refuse overflow; padding never discards text. Keep4GiB actual RSS,60s/query,480/481s CPU and600s parent wall, original quality gates and three actual repetitions. No score replay between repetitions. Three attempted runtime implementations are reported, not selectively hidden.

Keep v2's exact singleton full-head/final-head reference probe, and independently require the first actual four-document padded batch to have exact pair token counts and finite scores/IDs. Batch padding/matmul shape may cause numeric differences from singleton execution; do not claim batch4 logits are bit-identical to batch1. Record batch size/masks/source hashes in the scoring contract and resource report. Use the same candidate cache ID (artifacts are identical) and a separate profile file; reranker fingerprints remain runtime-specific and never enter embedding collections.

This runtime variant is an evaluation implementation choice under the requested original-candidate comparison. It does not replace an agreed model or change production configuration. A successful measurement still leaves human-reviewed quality and adoption/rollback decisions open. If it fails, retain that failure and assess remaining work; do not tune labels/quality thresholds or automatically deploy.

## Observed batch4 acceptance — 2026-10-19

**Purpose:** Bind the distinct runtime to actual measurements and preserve the incomplete profiles.

Focused44 PASS/234.51s; full1096 PASS/540.75s,0 SKIP. All three actual batch4 repetitions stable and full/focused quality equal: R@3/R@5/R@10/MRR@10/nDCG@10 all1 on the frozen authored diagnostic corpus; baseline .972222/.972222/1/.949074/.961613. Diagnostic gates pass; descriptive paired nDCG-gain interval[0,.094657] includes0 and independent human quality remains unvalidated. Process peak RSS1596.055MiB, CPU-only GPU0, fresh session load2.300225s, warm ten-pair query p95≈2238.943ms; no end-to-end/production SLO claim. Actual singleton full/final-head class logits exactly[12.375,21.25]. Input/padding/ID/finite/protocol, actual512/513, cancel/timeout/parent-death and physical budget-kill tests pass.

Batch1 v1/v2 remain failed/incomplete; no original budget/quality gate/label/source change. Existing application/model selections/registry/E5 rollback/schema/dependencies untouched, candidate scoring no source/vector writes. Clean post-audit; no production flag/collection enabled. [Comparison](../evidence/d27-t02-reranker-comparison.json), [acceptance](../evidence/d27-t02-acceptance.json), [T03 proposal](../progress/D27_RERANKER_ADOPTION_REVIEW.md). D27 IN PROGRESS, T03 NEXT, D28 not started.
