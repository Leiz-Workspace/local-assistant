# HAR-008-L1 — Target line/quote pairing protocol

**Purpose:** Freeze a new controlled review cohort and scoring before measuring the optional line-paired contract. [ADR-185](ADR/185-opt-in-target-bound-review-line-quote-contract.md).

**Date:** 2026-11-11. No model, skill or prior score change. Q2's 21/24 baseline and23/24 skill remain attached to their original first outcomes.

## Frozen cohort

`benchmarks/fixtures/har008-l1-review-v1.json`:12 fresh same-author controlled review cases, four defective implementations/four caller-context/four controls, including two null controls and two repeated-quote findings. Three cases read the target from a non-one original line. Source fixtures include blank/header lines and have explicit original line numbers; source text is never executed. Gold typed line and exact canonical quote are local and frozen before generation; no original Q2 ID/source is reused. These are related controlled task families, not independent human labels or actual repository findings.

Each case uses one target read and optionally a caller policy read, same paths/ranges across arms, unchanged CORE/Q6_K/b11557/Fast512/strict and unchanged repo-review skill bytes. Four arms: generic baseline, generic skill, bound baseline, bound skill. Generic uses the existing source-value-quote-v1; bound uses review-line-quote-v1 plus the explicit target path. Cyclic order makes each arm occupy each position three times. Host instructions and schema differ together; this does not isolate their individual effects.

Freeze actual source/skill/config/product/runner hashes, corpus/oracles, native PID/start ticks and options before the first cohort completion. Include all retained target lines as eligible schema pairs, not only a gold finding. Reject missing/conflicting/omitted targets or schema overflow; do not silently choose another file or schema. Other reads remain model-visible caller context but never become alternative output targets.

## First outcomes and resources

Forty-eight first product-API calls, no retry/repair/extraction or favorable response selection, 600-second campaign bound, existing120-second task deadline. Save each request/first response/score/resource observation exclusively in a new owner-private directory. Native contract rejection is a counted first quality failure; transport/software/context-binding/drift stops the campaign with partial receipts. Keep any active-run uncertainty explicit and clean only owned temporary grants/runs.

Grade exact JSON, typed gold line, exact gold quote and strict conjunction separately. Also independently grade **line-pair membership** against actual retained target lines/ranges, without consulting the gold finding. A source-valid wrong finding or null on defective code can have valid mechanics and still fail quality. Duplicate text at different lines remains multiple valid mechanical pairs, but the semantic oracle selects the specific contract-violating occurrence. Do not fix a model's line from quote provenance after generation.

Reuse benchmark-only explicit-PID RSS/GPU sampling at0.2seconds, preserving KiB/MiB, lifetime HWM distinction, missing samples and process-start identity. Descriptive warm task duration includes polling/receipt persistence and concurrent instrumentation, not pure inference/TTFT. No new streaming replay is required for this mechanical comparison; Q2 timing evidence stays historical, not re-labelled as L1 timing.

## Development checks and disposition

Before the cohort, two excluded native development controls used unrelated marker source: an intentionally inconsistent requested number/quote and a safe no-defect question. Both were mechanically valid; the first selected a different valid source pair rather than the requested inconsistent combination, so it is **not** a semantic-success example. Preserve both raw replies and never add them to quality scores.

On this date CORE was initially absent. Verify existing approved weights checksum and runtime pin, start only that configuration for the trial; do not download/change weights, raise context/caps or replace models. Use an owned isolated app7092, leaving unrelated services untouched. Stop owned trial processes after evidence capture and retain all data. Model/skill/default adoption and broad specialist/release gates remain unchanged regardless of saturation. Report gains/regressions and uncertainties without cross-cohort causal claims.


## Second-stage amendment — frozen before ordering-cohort generation

First trial48 outcomes are retained: strict generic10/12 baseline/8/12 skill versus value-first8/12 each, one generic pair mismatch and zero bound mismatches. This does not meet a quality-promotion claim. The exact measured sources are archived privately before implementing the next variant; no outcome is regraded.

New corpus `benchmarks/fixtures/har008-l1-order-v1.json` has12 fresh opaque-ID cases, same three balanced categories, three partial ranges/two null controls/two repeated-quote findings, no first-cohort source reuse. Six arms: generic baseline/skill, value-first baseline/skill, quote-first baseline/skill. All use the same frozen sources/questions/caps/skill bytes and target ranges. Cyclic order puts each arm in each position twice. Generic uses source-value-quote-v1; value-first uses review-line-quote-v1; quote-first uses review-quote-line-v1. Only the bound property order and contract identifier differ between the two paired schemas; semantic/source domains remain identical.

Seventy-two first calls,900s campaign/120s task, no retries. Same scoring/resource/privacy/partial-stop rules as the first trial. Two excluded quote-first development controls verify full API/native wire behavior before cohort inference, without revisiting gold cases. Report every original failure, variant regression and limited same-author generalization. No comparison across different cohorts is causal evidence, no model/skill/default change follows automatically, and first/generic modes remain available for rollback.
