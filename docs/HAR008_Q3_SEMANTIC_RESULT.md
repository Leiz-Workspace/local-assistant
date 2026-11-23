# HAR-008-Q3 — Finite semantic review and planned self-check

**Purpose:** Record supported counterexample correctness separately from source validity, first candidates and same-model self-checks.

**Date:** 2026-11-11. [ADR-186](ADR/186-native-only-finite-semantic-review-prototype.md), [predeclared protocol](HAR008_Q3_SEMANTIC_PROTOCOL.md), [public receipt](evidence/har008-q3-semantic-20261111.json).

**Bounded prototype measurement COMPLETE; semantic/adoption gate NOT_QUALIFIED. None of the four groups produced a fully correct proof on any of the five known-defect cases: 0/5 in every group. No production self-check workflow was enabled.**

## 1. What was evaluated

Twelve fresh opaque-ID registered-template cases: five defects, five conforming finite-probe controls and two unknown/conflicting caller contracts. Four fixed input probes per case. Sources cover falsey/None, UTF-8 byte quotas, inclusive ranges, integer caller attributes and cancellation; sources/model text are never executed. Registered trusted pure operations compute expected/observed values from the fixed inputs. Actual native source snapshots are matched byte/provenance-for-byte to registered gold before freezing; exact evidence, gold/tables and outbound native requests are retained privately.

The model must distinguish defect/no_defect/uncertain. A defect needs a supported claim category, an admissible original source location/quote and one divergent, correctly typed expected/observed probe result. All source lines/global claim/probe domains remain schema options, not just gold answers. Multiple supporting locations were declared before inference where appropriate. Title prose is bounded but **semantically ungraded**. No_defect is scoped to the four probes, not a proof over all possible inputs. Trusted registered semantics are authored by the same agent, not independent human labels or arbitrary repository verification.

Each case draws one candidate without skill and one with unchanged repo-review instructions. Each receives exactly one preplanned same-model self-check, sharing its original raw candidate and the same sources/probes, without gold/score feedback. This yields24 initial candidates plus24 checks:48 quality calls, same CORE/Q6_K/b11557/Fast512/strict. Skill-group order alternates; each check necessarily follows its candidate. Checked workflows have two512-token call caps versus one for single-stage. This is a **native-only research prototype**, not the product task API or a changed tool/trust lifecycle.

## 2. First outcomes and controlled proofs

| Arm | Overall finite criterion | Known defects, complete proof | Conforming controls | Correct uncertainty |
|---|---:|---:|---:|---:|
| Single baseline | **6/12** | **0/5** | 5/5 | 1/2 |
| Checked baseline | **5/12** | **0/5** | 4/5 | 1/2 |
| Single skill | **5/12** | **0/5** | 5/5 | 0/2 |
| Checked skill | **6/12** | **0/5** | 5/5 | 1/2 |

All48 outputs had valid finite JSON shape/source pairs; the semantic gate still rejected false proofs. Baseline self-check had one gain/two regressions; skill self-check one gain/zero regressions. These gains concern classification/uncertainty controls and do not repair any complete known-defect proof. No stable self-check or skill advantage is established. None of the stages claimed a defect on a known-safe control, but checked baseline changed one safe classification to uncertainty; defects were often missed instead. Initial baseline missed4/5 defect classifications, other stages3/5. Correctly recognizing a claim/line sometimes still failed its counterexample.

### Preserved examples

- Checked skill recognized `return value or fallback` and its truthiness claim but reversed expected and observed for the empty-string input. Correct finite outcomes are expected empty string, observed `backup`; its claimed reverse is not credited.
- It recognized the integer `.isdigit()` problem, but returned expected string `"0"` instead of integer0 and observed `ValueError` instead of `AttributeError`. Correct title/category alone does not pass the typed proof.
- UTF-8 character-count quota, inclusive-range and swallowed-cancellation defects were returned as no_defect in checked-skill outputs.
- On an unresolved unit contract, it invented a unit-conversion defect with equal string expected/observed values, not a divergent counterexample. Unknown contract is not a supported defect or a conformance proof.

The excluded development control validated native nested-schema/output types but selected a source header rather than the requested return line. It was never scored as a semantic success. No output, type, selected probe, expected value or old L1 location was repaired/regraded. Richer semantics and changed cases mean these scores are not a causal comparison to L1's narrow exact-line panels.

## 3. Real extra cost and resource observations

| Arm | Median call wall time | Median workflow wall time |
|---|---:|---:|
| Single baseline | 0.717933 s | 0.717933 s |
| Checked baseline | 0.630693 s for the check | **1.379087 s** including its candidate |
| Single skill | 0.759914 s | 0.759914 s |
| Checked skill | 0.648006 s for the check | **1.578827 s** including its candidate |

Checked workflow sums the actual two measured calls, not just the faster second call. Call time includes preparation/request retention and concurrent instrumentation; excludes one-time source-freeze/model load and baseline/final metric queries. Existing cache/residency and dependent candidate/check order affect timing. No TTFT/cold-load/concurrency or SLO was measured.

All48 resource observations complete:270 samples, pinned native PID/start ticks, sampled RSS maximum8,227,964KiB (about7.85GiB), GPU process allocation8018MiB (7.83GiB). These are warm native process observations, not request-only/tensor-only/absolute peaks; differing process/workload prevents treating the lower RSS than earlier trials as an optimization result.

## 4. Validation, traceability and lifecycle

**407 related PASS, 0 FAIL, 0 SKIP in4.50s**,34 product/history/auth/preset/benchmark files, no model calls in pytest. This is the32-file L1 invocation plus `benchmarks/tests/test_semantic_review.py` and `test_semantic_review_run.py`. Tests include trusted finite outcomes, predeclared alternative locations, false proof/type/probe/category rejection, uncertainty versus safe, source tampering/no execution, exact native source/gold binding, no oracle leakage, shared candidates, first partial HTTP/transport retention and no retry. Ruff check/format for five new Python files and offline lock check passed. No production source or package change in Q3; no new full D87 regression/release.

Recomputed all48 first scores from unmodified content, all24 shared-candidate hashes,12 complete source/provenance bindings and trusted tables. Frozen code/config/skill/source bytes remained unchanged. Raw requests include exact native messages/schema and no gold feedback. Private artifacts: `data/evaluations/20261111-har008-q3-semantic-v1`; public receipt retains their hashes. Total native calls49=48 quality+one excluded development control, not49 independent quality cases. All L1/Q2 and earlier scores remain unchanged.

CORE was initially absent: existing approved weights/checksum and runtime pin were verified, its unchanged launcher started the owned trial, and the owned process was stopped cleanly after capture. No app/product restart, model/skill/config/default/weights/SDK/provider/Docker/Vault/database/Qdrant change, source execution, commit or release. Product runs still have their previous single-completion contract.

## 5. Next assessed task

HAR-008-Q4: design a bounded **observation-assisted** verifier using approved deterministic probe/type evidence rather than another ungrounded self-check. Keep gold verdict/expected labels withheld, distinguish tool observations from authority, freeze new cases and report all first failures. Registered-template support must fail explicitly outside its domain; no arbitrary source/model code execution or production rollout from this pilot. ADR, authority/budget/latency analysis and fresh evaluation are required before new tool/workflow activation. Existing model choices and all broad specialist/release gates stay open.
