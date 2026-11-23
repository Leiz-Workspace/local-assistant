# ADR 184 — Controlled maintenance semantics and observed resources

**Purpose:** Extend HAR-008 beyond one-line output mechanics while preserving the approved model, product paths and all prior measurements.

**Date:** 2026-11-10. **Status:** Accepted for bounded evaluation under the owner's continuation request; no model, product-default or architecture replacement.

## Decision

Use a new, frozen 24-case controlled maintenance panel through the same authenticated product API and unchanged skills. Four arms per case remain text/constrained × baseline/skill, Fast512/strict, one first outcome each, cyclic order. Include multiple actual read snapshots, caller preconditions, safe controls, unavailable/conflicting facts, Vietnamese evidence and longer early/late evidence. Exact semantic value/quote oracles remain local and are frozen before generation; native grammar includes every retained admissible line, never just oracle quotes. Do not execute source snippets.

Add benchmark-only resource sampling, not product instrumentation. Require an explicit llama-server PID, pin its Linux process start ticks and read RSS/lifetime HWM with process GPU allocation from nvidia-smi. Take baseline/periodic/final observations with a joined bounded worker; preserve missing metrics as incomplete, never zero. Sample at 0.2-second intervals, GPU commands bounded to two seconds, and retain raw observations. RSS in KiB and GPU process allocations in MiB measure different things. Lifetime HWM is not a per-request peak; sampled values miss short spikes and do not attribute memory to individual tensors. No runtime limits, residency, context size or shared processes are changed.

The nonstreaming product task API cannot expose first-token arrival. Do not label prompt-time counters or full-response latency as TTFT. Separately replay four **predeclared** cases through native streaming, constrained baseline/skill, eight calls total, recording time from request start to the first nonempty text delta and final DONE. This is a warm benchmark transport replay, not a product streaming feature, new semantic score, retry or task-API TTFT. Ignore role/null chunks; incomplete/length/tool responses remain failed diagnostics. Preserve raw events and exact request/schema/source hashes.

## Gates and limits

Quality campaign bound: 96 calls, no retries, existing 120-second task deadline and 1,200-second campaign bound. Streaming replay bound: eight calls, no retries, 120 seconds each and 1,000 seconds total. Stop on transport/software/frozen-input drift, retaining all partial evidence; a completed native host contract rejection remains a first quality failure. Remove only campaign-owned grants/runs and stop only the owned probe. Primary desktop and CORE remain running.

Completion requires all first outcomes and resource observations accounted for, with format, typed-value correctness, source quote and strict success reported separately per category/arm. Valid source membership is not semantic entailment. These same-author controlled scenarios and one stochastic sample per arm/case cannot establish broad independent qualification or general skill advantage, even at saturation. Resource/latency data are observations, with no invented performance threshold or deployment acceptance. Do not change prior AC, model/adoption/release gates or original scores.

Rollback is to omit these optional benchmark commands and keep all evidence. No production source, SDK/weights, Docker, Vault, database or Qdrant changes are needed.

## Observed outcome

[Result](../HAR008_Q2_MAINTENANCE_RESULT.md): 96 first quality calls completed in109.779s, text11/24 each, constrained baseline21/24 and skill23/24. All48 source/schema contracts were valid; gold semantic/localization errors remain, including a correct quote with the wrong review line number. Two constrained skill gains in this controlled panel do not establish broad advantage. Sampled CORE RSS maximum9.55GiB, GPU process allocation7.83GiB, 637 complete quality samples. Eight separate warm streaming replays completed with58 samples; first-text0.42–0.62s short/2.37–2.53s long, not task-API TTFT. Final related349 PASS/4.07s, no model calls in pytest. Owned probe stopped; production source, primary desktop, CORE and all model/default/release decisions unchanged. HAR-008-L1 assessed for a separate opt-in review-target/line/quote contract; no retrospective correction of Q2 scores.
