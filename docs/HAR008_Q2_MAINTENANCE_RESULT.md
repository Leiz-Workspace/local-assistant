# HAR-008-Q2 — Controlled maintenance, resources and first-text timing

**Purpose:** Record first native semantic/localization outcomes and measured resources without changing models, product defaults or previous scores.

**Date:** 2026-11-10. [Protocol](HAR008_Q2_MAINTENANCE_PROTOCOL.md), [ADR-184](ADR/184-controlled-maintenance-and-observed-resource-evaluation.md), [public receipt](evidence/har008-q2-maintenance-20261110.json). **Bounded measurement COMPLETE; broad specialist promotion NOT_QUALIFIED.**

## 1. Measured scope

Twenty-four new controlled maintenance scenarios, twelve source tasks/twelve reviews, ten null controls and 34 actual source files. Four cases per category; four longer records include early/late approved facts, obsolete distractors and source directives. Review cases require quotas, boolean precedence, None/zero, boundary behavior, cancellation and caller contracts. Sources were read through existing native workspace tools, never executed. Same-author gold values and exact source/review-line quotes were frozen before answers; this is not independent human evaluation or a report of real repository bugs.

Ninety-six first calls through the authenticated product API: text/constrained × baseline/unchanged skill, cyclic order, same approved Qwen3.5-9B Q6_K CORE, b11557, Fast512, strict context. All required one/two sources were retained and exact skill bindings checked. Input range **778–12,970 tokens**; the pre-generation integration check used different fixture path lengths and reached 10,839 tokens, which is not substituted for actual measured inputs. No context increase, model replacement, SDK/weights, source execution or output repair/retry.

## 2. First quality results

| Arm | JSON shape | Typed value / line | Exact oracle quote | Strict conjunction |
|---|---:|---:|---:|---:|
| Text baseline | 22/24 | 21/24 | 11/24 | **11/24** |
| Text + skill | 19/24 | 18/24 | 11/24 | **11/24** |
| Constrained baseline | 24/24 | 21/24 | 21/24 | **21/24** |
| Constrained + skill | 24/24 | 23/24 | 24/24 | **23/24** |

Strict success requires exact JSON fields, exact typed value and exact declared quote. These bounded answers/localization oracles do not measure explanation quality, patch correctness or full semantic entailment. All 48 constrained outputs passed the independent structural/source contract; three baseline and one skill answer still failed gold semantics/localization. Source-valid JSON is therefore explicitly **not** model-quality PASS.

| Category, four cases each | Text baseline | Text skill | Constrained baseline | Constrained skill |
|---|---:|---:|---:|---:|
| Supported source | 3 | 2 | 3 | 4 |
| Unsupported/conflicting source | 0 | 0 | 4 | 4 |
| Longer source | 3 | 3 | 4 | 4 |
| Defective implementation | 0 | 0 | 3 | 4 |
| Safe implementation | 4 | 4 | 4 | 4 |
| Cross-file caller context | 1 | 2 | 3 | 3 |

Adding skill on the constrained path yielded two strict gains and zero regressions in this panel; text skill yielded one gain/one regression. Constrained baseline versus text had eleven gains and one regression; constrained skill versus text had twelve gains and zero regressions. Do not hide the baseline regression, infer a population advantage from two discordant pairs or compare different cohorts causally. One stochastic draw per case/arm and related same-author task families limit generalization.

### Retained constrained failures

- Baseline `invoice-before-tax`: returned null/null despite an explicitly verified Vietnamese subtotal of 116. Text baseline answered this correctly: the constrained treatment's observed regression is retained.
- Baseline `review-zero-timeout`: returned null/null for `return timeout or default`, missing the declared zero-preservation defect. Skill found it.
- Baseline `review-caller-integer-input`: selected line 6, `return int(raw)`, instead of the earlier `.isdigit()` call on an integer at line 4.
- Skill on that same caller case: quoted `if not raw.isdigit():` correctly, but returned value **5 instead of 4**. Its quote origin proves line 4; the generic value/quote schema does not bind numeric answers to origin line numbers. No post-hoc correction or new score was substituted.

Next remediation HAR-008-L1 assesses a separate opt-in review-line/quote binding with an explicit target source and fresh evaluation; ordinary numeric source answers must remain unaffected. This would address mechanical localization inconsistency, not prove general review reasoning or repair all baseline misses.

## 3. Runtime and resources

Quality campaign **109.779 s**, 96/96 first outcomes, 24 complete four-arm blocks, zero retries/cleanup failures/unidentified submissions. All 48 constrained catalog/schema/raw-content/origin checks match frozen inputs. **637 resource samples**, all complete, pinned to the same native PID/start ticks. Measured source/config hashes remained unchanged.

| Arm | Median observed task duration | Maximum |
|---|---:|---:|
| Text baseline | 0.749795 s | 3.175196 s |
| Text skill | 0.746984 s | 3.700610 s |
| Constrained baseline | 0.694991 s | 3.072821 s |
| Constrained skill | 0.746852 s | 3.177266 s |

Duration includes API submission/polling (0.1-second poll interval) and first-response receipt serialization/fsync; excludes baseline/final metric queries but includes concurrent sampling overhead. It is not pure native inference time or TTFT. Campaign wall additionally includes setup, metric queries, receipts and cleanup. Do not interpret tiny median differences as demonstrated speed gains.

- **Peak sampled CORE RSS RAM:** 10,013,460 KiB ≈ **9.55 GiB**. Request baseline RSS range 9,282,936–10,013,460 KiB; warmed process/cache residency changes across the campaign. This is the native process footprint, not total application RAM or request-only allocation.
- **Peak sampled CORE GPU process allocation:** 8018 MiB ≈ **7.83 GiB**, constant in these observations. Includes retained allocations such as weights/KV/workspace; it is not just weight size, all-device usage or a measured minimum VRAM requirement.
- Interval 0.2 seconds plus GPU-query overhead; baseline/final samples included. Raw observations and lifetime HWM are retained separately. Neither sampled maximum is an absolute peak; process lifetime HWM must not be reported as a request-specific peak. No cold load, uncached/isolated-host, load-concurrency, SLO or resource-headroom acceptance is established.

### Separate native streaming timing

Eight **predeclared replays**, no semantic scoring/retry of the quality outcomes. Each row is one warm request; baseline/skill order alternated by case. Full first SSE events retained, null/role-only deltas ignored, first nonempty text delta and final DONE observed. All eight streams completed stop, passed output-contract validation and had complete metrics (**58 samples**).

| Case | Prepared input tokens baseline / skill | First text baseline / skill | Total baseline / skill |
|---|---:|---:|---:|
| Approved retry delay | 1428 / 1477 | 0.443306 / 0.416774 s | 0.806727 / 0.738554 s |
| Longer maintenance record | 12315 / 12379 | 2.525117 / 2.371246 s | 2.860830 / 2.663984 s |
| Safe cancellation | 1785 / 1888 | 0.624449 / 0.491198 s | 0.806390 / 0.612825 s |
| Caller stale-token check | 1828 / 1924 | 0.468181 / 0.472165 s | 0.657471 / 0.679213 s |

This is request-to-first-text arrival at a native SSE client with existing cache/residency, not physical token-generation timing, a population percentile or **task-API TTFT**. Product task output remains nonstreaming; product streaming code was not changed. Streaming sampled RSS maximum 9,984,648 KiB, GPU allocation maximum 8018 MiB; do not merge different workloads with historical D14/D67 baselines.

## 4. Software, evidence and boundaries

Before native measurement: **349 passed, 0 failed, 0 skipped in 4.07 s**, 29 related product/history/auth/preset/benchmark test files, zero model calls in pytest. The prior 26-file invocation from [HAR-008-R1](HAR008_OUTPUT_CONTRACT_RESULT.md#4-software-verification), plus `benchmarks/tests/test_har008_maintenance.py`, `test_harness_resources.py` and `test_harness_stream_timing.py`, was run together. Tests cover path/oracle/budget validation, first-outcome/no-retry cleanup, real multi-source reads, PID reuse, GPU units/missing metrics, owned thread joining, null/role chunks and incomplete/length/tool streaming rejection. Ruff check/format for six new files and offline lock check passed. Not a full D87 regression.

Private first artifacts: `data/evaluations/20261110-har008-q2-maintenance-v1` and `20261110-har008-q2-streaming-v1`; the public receipt records every JSON artifact hash and exact source/skill/config scope. Total native calls **104 = 96 quality + 8 timing**, not 104 unique quality cases. A separate 24-case source/schema/tokenizer preparation made zero completion calls. All old v1/R1/R2/R3 outcomes and hashes are preserved.

Only benchmark/test/docs additions this follow-up. No production source/model/config/default/weights/SDK/Docker/Vault/database/Qdrant change, no commit/staging/promotion/release. Temporary runs/grants were empty before stopping owned probe7092. Primary7090 and CORE8080 were not restarted. HAR-008-Q2 bounded measurement is complete; HAR-008 overall, HAR-008-L1, broad specialist/resource qualification, advanced context/memory, durable execution/catalog, native installers, media adapters and prior release gates remain open.
