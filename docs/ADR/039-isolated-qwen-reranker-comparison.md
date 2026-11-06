# ADR-039 — Isolated original-candidate reranker comparison

**Purpose:** Define D27-T02 provisioning, yes/no scoring, resource supervision and paired comparison before execution.

**Date:** 2026-10-19
**Status:** Local batch4 measurement accepted after1096 PASS/0 SKIP; batch1 failed/incomplete, no adoption or production integration authorized.

P1; depends on T01 frozen corpus/plan/baseline. Effort1–2 evaluation milestones. The owner's latest request to continue follows the concrete T02 proposal and authorizes executing this original-candidate comparison. This scope permits evaluation-only artifact/environment provisioning and inference, preserves all agreed selections/configuration/source data, and does not authorize deployment or model replacement.

## Artifact and runtime contract

Use original Qwen/Qwen3-Reranker-0.6B revision e61197ed45024b0ed8a2d74b80b4d909f1255473, official BF16 CPU, two intra-op/one inter-op threads, batch1, SDPA, use_cache=False. Separate frozen uv script environment uses already reviewed CPU torch2.10.0+cpu, transformers4.57.6, numpy2.5.4/httpx0.28.1/typing-extensions4.15.0; project/embedding environments stay unchanged. Pin every required artifact size/SHA256 before model inference; verify upstream Git blob/LFS identities from T01. Store only in a separate ignored evaluation cache. No credentials/proxies or implicit Hub token/downloads inside inference, trust_remote_code=False, CPU-only Torch and all parameters verified CPU/BF16. The config's40960 position field is not a validated context claim; complete comparison inputs remain capped512 tokens.

Freeze execution manifest/profile/runtime/source/baseline/corpus/plan hashes before first scoring. Pass only exact36-query fixed top10 candidate text/IDs/source hashes reconstructed from the unchanged synthetic corpus and T01 evidence. Verify every source and candidate binding against frozen hashes. No new vector/source writes, DB or Vault calls are needed for candidate scoring. Existing T01/D24/D26 evidence is never overwritten.

## Pair scoring and measurement

Use the pinned official Transformers chat/instruction format and final-position yes/no logits. Validate distinct, single-token yes/no identities against tokenizer vocabulary. Count the full chat prefix, pair instruction/query/document and assistant suffix before tensor creation; reject513+ tokens without truncation. Compute softmax over no/yes logits in float32; finite scores in[0,1] are relative ranking values, not calibrated confidence. Reorder exactly the same ten candidates by descending score and stable document ID for ties, never add/remove/relabel a candidate. Three measured repetitions use the same loaded session; retain every pair count/score/query wall time/ranking and metrics per repetition. Record cold model/artifact load separately.

Preserve ADR-038/plan quality gates: no R@10 loss, macro R@3/MRR nonregression, each group's R@3 loss<=.05, nDCG@10 gain>=.02. Report paired fixed-seed query-bootstrap deltas as descriptive only; the authored36 queries share12 intents. Keep all regressions/misses and do not retune corpus/prompt/labels/thresholds after results.

## Resources and failure ownership

Child enforces4GiB actual process RSS with a50ms resident-page watchdog and records Linux RUSAGE_SELF high-water RAM; no parent/child cumulative RSS substitution. GPU use is0 by verified CPU-only runtime/device, not an inferred GPU benchmark. Eight-GiB RLIMIT_AS is only a virtual-address ceiling. Each ten-pair query has a60s wall timer that terminates the isolated child; overall parent timeout600s, CPU480/481s. Child is supervised with existing exact API PID/start/pidfd handling before importing Torch; normal cancellation/timeout kills and joins the owned process group. Evaluation adapter has one nonqueued slot and a whitelisted environment. Response<=2MiB, input<=1MiB; fixed sanitized errors. Tests require token boundary, fake-logit oracle, tamper/incomplete/nonfinite/no-leak failures and real cancel/timeout/parent-death cleanup.

T02 acceptance is a truthful complete comparison with resource/protocol/reproducibility results, not an obligation for the candidate to win. Failed quality/resource gates remain failed and cannot be hidden by a pytest PASS. D27 remains open for independent human-reviewed quality and an explicit decision/adoption stage. No ranking stage is added to live retrieval. Rollback keeps the original default-disabled dense path and embedding/vector/source identities; no source/collection deletion or migration occurs in this evaluation. Any later integration needs its own ADR and owner-approved scope.

Reference: [pinned official model card](https://huggingface.co/Qwen/Qwen3-Reranker-0.6B/blob/e61197ed45024b0ed8a2d74b80b4d909f1255473/README.md).

## Execution implementation amendment before v2

**Purpose:** Retain the incomplete attempt and correct unnecessary computation without changing experimental thresholds.

First focused run41 PASS/1 failure in244.05s; no accepted candidate result. It failed near the480s CPU budget (last observed413 CPU seconds, RSS1654616KiB); exact exit code was not logged, so CPU-limit diagnosis remains inferred. Initial source archive/log hashes and manifest v1 are retained. The pinned Transformers4.57.6 Qwen3 forward supports `logits_to_keep`: its source applies the vocabulary head only to the requested final hidden-state positions. Use1 instead of computing unused logits for every input token, preserving the same complete input, weights, dtype and final-position scoring. Require exact actual no/yes logits versus the original full-head computation on the first frozen pair before accepting any v2 comparison. Record this parity result, the changed scoring contract/fingerprint and source manifest v2. Add only safe numeric exit-code/completed-round diagnostics. No corpus, prompt, label, candidate, resource/quality threshold or model selection change. [Pinned framework implementation](https://github.com/huggingface/transformers/blob/v4.57.6/src/transformers/models/qwen3/modeling_qwen3.py).

## Observed batch4 acceptance — 2026-10-19

**Purpose:** Bind the distinct runtime to actual measurements and preserve the incomplete profiles.

Focused44 PASS/234.51s; full1096 PASS/540.75s,0 SKIP. All three actual batch4 repetitions stable and full/focused quality equal: R@3/R@5/R@10/MRR@10/nDCG@10 all1 on the frozen authored diagnostic corpus; baseline .972222/.972222/1/.949074/.961613. Diagnostic gates pass; descriptive paired nDCG-gain interval[0,.094657] includes0 and independent human quality remains unvalidated. Process peak RSS1596.055MiB, CPU-only GPU0, fresh session load2.300225s, warm ten-pair query p95≈2238.943ms; no end-to-end/production SLO claim. Actual singleton full/final-head class logits exactly[12.375,21.25]. Input/padding/ID/finite/protocol, actual512/513, cancel/timeout/parent-death and physical budget-kill tests pass.

Batch1 v1/v2 remain failed/incomplete; no original budget/quality gate/label/source change. Existing application/model selections/registry/E5 rollback/schema/dependencies untouched, candidate scoring no source/vector writes. Clean post-audit; no production flag/collection enabled. [Comparison](../evidence/d27-t02-reranker-comparison.json), [acceptance](../evidence/d27-t02-acceptance.json), [T03 proposal](../D27_RERANKER_ADOPTION_REVIEW.md). D27 IN PROGRESS, T03 NEXT, D28 not started.
