# HAR-008-L1 — Target-bound review pairs and retained quality regressions

**Purpose:** Record delivered line/quote consistency, both first-outcome experiments and remaining quality limits without changing models or historical scores.

**Date:** 2026-11-11. [ADR-185](ADR/185-opt-in-target-bound-review-line-quote-contract.md), [protocol and second-stage amendment](HAR008_L1_REVIEW_PAIR_PROTOCOL.md), [public receipt](evidence/har008-l1-review-pairs-20261111.json).

**Disposition: bounded mechanics VERIFIED; semantic/adoption qualification NOT_QUALIFIED. Neither review variant is enabled by default.**

## 1. Implemented behavior

Two explicit readonly output contracts share the same eligible source pairs:

- `review-line-quote-v1`: generate integer line before canonical quote.
- `review-quote-line-v1`: generate quote before its paired integer line; a separately named ordering experiment, not an adopted improvement.

Both require a clean relative `review_target` also present in an explicit authorized workspace.read. Target selection never opens a path or grants access. Other reads stay available as caller context; only the actually retained target's original line numbers and quotes are schema alternatives. Missing/omitted/blank-only targets, conflicting snapshots/line contents and oversized schemas fail explicitly. Partial ranges retain original numbering; identical quotes at several target lines remain separate pairs. No oracle defect is used to construct the schema.

Native decoding uses the pinned nested JSON-schema format. Independent host validation checks the untouched reply's types, null/null pairing, source membership and selected original line. No number correction, trimming, fence extraction, coercion or retry. Diagnostics are owner-only/ephemeral on failed runs, signed history remains metadata/digest-only. The host accepts either JSON member order; the named native schema determines decoding order.

Default text, generic `source-value-quote-v1`, skill manifests, legacy gateway and browser streaming remain unchanged. CLI omits the new fields in default mode. A valid line/quote pair does not prove that the selected source is defective.

## 2. First cohort — value-first candidate

Twelve fresh controlled cases, four per category (defect/caller context/control), two null controls, two repeated-quote findings and three partial read ranges. Forty-eight first product-API calls, four cyclic arms, same CORE/Q6_K/b11557/Fast512/strict and repo-review bytes. Every requested source was retained.

| Arm | Exact typed gold line | Exact gold quote | Strict success | Invalid line/quote pairs |
|---|---:|---:|---:|---:|
| Generic baseline | 10/12 | 11/12 | **10/12** | 1/12 |
| Generic skill | 8/12 | 8/12 | **8/12** | 0/12 |
| Value-first baseline | 8/12 | 8/12 | **8/12** | 0/12 |
| Value-first skill | 8/12 | 9/12 | **8/12** | 0/12 |

All replies had exact JSON shape and passed their declared structural contract. All24 bound pairs were consistent, but value-first baseline versus generic produced one strict gain/three regressions. With skill, one gain/one regression. Repeated identical return lines could still be assigned to the wrong semantic occurrence; the safe Python cancellation control could still produce a false positive. Do not call eliminating one mechanical mismatch a quality improvement.

Campaign **38.269 s**, zero retries/cleanup failures/unidentified submissions. First outcomes, gold and exact measured source bytes remain preserved, including the source snapshot captured before the ordering variant was implemented. No scores were regraded.

## 3. Second cohort — six-arm ordering test

Hypothesis: choosing the integer before the quote might lock a wrong location; choosing the quote first might help. This was an inference to test, not a causal explanation established by the first sample.

Fresh opaque-ID corpus `har008-l1-order-v1.json`: twelve new controlled cases, same balanced categories and partial/duplicate/null coverage, no first-cohort source reuse. Six arms on each case; cyclic order puts each arm in each position twice. Same sources/questions/caps/skill bytes across arms. The paired schemas have identical admissible pairs/null semantics; property/required ordering and contract identifier differ. No new reasoning mode, model, skill or context increase.

| Arm | Exact typed gold line | Exact gold quote | Strict success | Invalid line/quote pairs |
|---|---:|---:|---:|---:|
| Generic baseline | 8/12 | 6/12 | **6/12** | 2/12 |
| Generic skill | 7/12 | 8/12 | **7/12** | 1/12 |
| Value-first baseline | 11/12 | 11/12 | **11/12** | 0/12 |
| Value-first skill | 9/12 | 9/12 | **9/12** | 0/12 |
| Quote-first baseline | 10/12 | 10/12 | **10/12** | 0/12 |
| Quote-first skill | 7/12 | 7/12 | **7/12** | 0/12 |

All72 replies had exact JSON shape and no host contract failures. All48 bound pairs were consistent and the first native member order matched each bound schema. Quote-first versus value-first had one gain/two regressions without skill, one gain/three regressions with skill. Its constrained-baseline result improved over generic in this cohort (five gains/one regression), while quote-first skill versus generic skill had three gains/three regressions. The hypothesis did **not** produce a consistent quality gain. Value-first also had different gains/regressions across cohorts; do not select a universal winner or pool changed cohorts to advertise an improvement.

Campaign **56.436 s**, zero retries/cleanup failures/unidentified submissions. Retained examples include quote-first skill selecting a function definition instead of an exhausted-count check, returning null for swallowed cancellation, and flagging correct `min(...)` and explicit-None implementations. It also selected a neighboring conditional where the oracle specifically requested the following repeated raise.

### Interpretation limits

These are exact predeclared localization tasks, not a complete semantic review rubric. Some neighboring lines can support a broader actionable finding even when they fail the requested exact occurrence; no post-hoc alternate location was credited. Future semantic work should declare accepted locations/claims/counterexamples before generation. These same-author related synthetic cases, descriptive first-cohort names, one draw per arm and small category counts do not establish independent generalization, patch correctness, skill advantage or larger-model parity. Both null and an incorrect admitted finding can have perfectly valid mechanics.

## 4. Verification, resources and lifecycle

Independently recomputed all120 contract/catalog/schema/raw-content/origin bindings and all72 bound line pairs from the frozen sources/ranges. Checked the72 bound native property orders. The first source snapshot matches its original frozen hashes; final current sources match the second frozen scope.

Resource observations were complete: **241 samples** in the first cohort and **356** in the second, pinned to the same native PID/start ticks. Sampled CORE RSS maxima were9,929,108KiB and10,048,876KiB (about9.47/9.58GiB); process GPU allocation maximum8018MiB (7.83GiB) in both. Sampling interval0.2seconds plus query overhead, warm resident process, not absolute/tensor-only/request-only peaks. Task duration includes polling/receipt persistence and concurrent instrumentation. No L1 TTFT, cold-load, concurrency or SLO acceptance was measured; do not relabel Q2 streaming timing as L1 evidence.

Final related verification: **389 PASS, 0 FAIL, 0 SKIP in4.63s**,32 product/history/auth/preset/benchmark test files, no model calls in pytest. This is the29-file Q2 invocation plus `tests/test_review_output_contract.py`, `benchmarks/tests/test_har008_review_pairs.py` and `benchmarks/tests/test_har008_review_order.py`. Covers exact native schemas/order/budgets, target authority, duplicate/partial/conflicting/size/type/null cases, owner/history privacy, CLI compatibility and first-outcome cleanup. The prior382/4.59s invocation is retained separately, not added to the final count. Ruff check/format19files, offline lock check and offline wheel build passed; six packaged implementation files match current source. Not a new full D87 regression.

Total native calls **124 = 48 first-cohort + 72 ordering-cohort + four excluded development controls**. The contradictory first value-first control picked another valid source pair; quote-first picked the requested quote with its actual line. These are mechanics observations, not extra quality successes. All raw first outputs, source/config/skill hashes and artifact hashes remain in separate owner-private evaluation directories.

CORE was absent at the start. Existing approved weights checksum and runtime pin were verified; the unchanged local launcher started that model for this trial. Owned app7092 and CORE were stopped cleanly after confirming empty campaign runs/grants, restoring their initially absent state. No active primary desktop restart, model/config/weights/SDK/provider/Docker/Vault/database/Qdrant change, commit or release. Original v1/R1/R2/R3/Q2 receipts and scores remain unchanged.

## 5. Remaining gate

Use either new mode only as an explicit mechanics/research option; neither is qualified for automatic adoption. L1 implementation and bounded measurements are complete, quality gates remain open. Next assessed task **HAR-008-Q3**: a fresh semantic review rubric/verification workflow with predeclared admissible locations and counterexamples, preserving these scores and the approved model. It must separate false positives from narrow exact-location mismatches and avoid treating model self-review as independent proof. Any new multi-call architecture, budget/skill/output change needs its ADR and controlled evaluation before activation. Do not keep tuning published cohorts or jump to a model replacement.
