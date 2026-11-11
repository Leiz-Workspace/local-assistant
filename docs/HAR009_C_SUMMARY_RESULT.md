# HAR-009-C summary v1 — result

**Purpose:** Record the first native outcomes of the opt-in evicted-history summary ([ADR-192](ADR/192-proposed-opt-in-llm-summary-of-evicted-history.md)) under the frozen [v1 protocol](HAR009_C_SUMMARY_PROTOCOL_V1.md). [Public receipt](evidence/context-summary-c-20261111.json). Date: 2026-11-11.

**Status:** measurement COMPLETE. 84 of 84 first native answer completions plus 28 summary generations, no retries, 610.4 s from the freeze to the summary. **Result: no gain.** The v1 summary did not recover any evicted target. Adoption is not decided here, and the flag stays experimental and opt-in.

## Run

- **Model and runtime.** Approved CORE `qwen3.5-9b-core`. The weights SHA-256 `073a9275…` and the runtime pin `5c8854fd…` were checked before start. CORE was started with the unchanged `scripts/start-core.py` as PID 498456 and stopped with SIGINT afterwards; port 8080 was free.
- **Answers:** preset `fast`, `max_tokens` 512, temperature 0.7, native streaming.
- **Summaries:** ADR-192 settings (thinking off, temperature 0, `max_tokens` 1,536, JSON schema), with a deadline of 120 s per cell and no cache.
- **Design check and freeze.**
  - The design check passed with an oracle summarizer and no model call. In every summary cell the oracle capsule was admitted, pairs 1–8 were covered (all targets included) and no target was clipped. The reserve cost no pair on this corpus (`pairs_lost_to_reserve` 0).
  - `frozen-inputs.json` was written before the first completion. After the run, the source hashes and the corpus were checked again, and none had changed.
- **Owner-private records.** The raw files are in `data/evaluations/context-summary-c-20261111`, which Git ignores.

## Results (strict, 12 scored cases per arm)

| Arm | Strict | Stale | Facts in context | Summary statuses |
|---|---:|---:|---:|---|
| `full` (reference) | **11** | 0 | 12 | — |
| `legacy` | 0 | 0 | 0 | — |
| `budget` | 0 | 0 | 0 | — |
| `budget_state` | 0 | 0 | 0 | — |
| `budget_summary` | **0** | 0 | 0 | 7 applied, 7 none_verified |
| `budget_state_summary` | **0** | 0 | 0 | 7 applied, 7 none_verified |

- **The reference check passes.** `full` reached 11/12. The only miss is Puffin, answered "No" without punctuation. The pre-registered rule needs "No," or "No.", so it counts as a failure; no post-hoc credit is given.
- **No arm without the full history answered any target.** All targets were evicted by design, and unmarked facts carry no working state.
- **The summary arms gained nothing.** Paired against `budget`: 0 gains and 0 regressions, and no new stale answers.

## What the summarizer did

- **It copied acknowledgements, not facts.** Every admitted item (26 across 14 cells) is an `assistant_claim` that copies a short assistant reply from a filler or target pair, such as "Noted as a personal reminder." or "Try 'Hello again, everyone!'". No gold value reached any capsule (gold value admitted: 0 of 28 summary cells). The user's statements, which hold every target fact, were never summarized.
- **The verifier dropped the rest:** 18 `invalid_supersession`, 18 `quote_not_in_source` (mostly one-word acknowledgements such as "Noted."), 16 `speaker_mismatch` and 2 `quote_too_short` across both summary arms.
- **The output was deterministic.** Both summary arms produced the same items at temperature 0.
- **Safety held.**
  - Verifier self-check defects: 0. No admitted value token sat outside its quotes, and no admitted item matched the authority lexicon.
  - In both authority-gate cases, no approval or consent wording was admitted. Atlas admitted only acknowledgements, and Hòa Bình admitted nothing.
- **Cost.**
  - Summary generation took an upper median of 6.6 s (maximum 8.2 s), with 432 output tokens (maximum 557).
  - Summary arms had a slightly earlier first text than `budget` (4.7 against 5.0 s, upper medians), because their input carried a small capsule while the reserve cost no pair.
  - Sampled CORE peaks: RSS 10,242,836 KiB and GPU 8018 MiB, from 2,202 samples, all COMPLETE.

## Independent check

All 84 rows were rescored with 0 mismatches. Presence was recomputed from the saved requests, and faithfulness from the saved summaries, also with 0 mismatches. The frozen hash, the source hashes and the corpus identity were confirmed after the run.

## Reading the result

- **The mechanism works; the content does not.** Coverage, the deadline, verification, admission, the reserve, the capsule and the statuses all behaved as specified. The design check showed that a gold item would have been admitted.
- **The failure is the v1 prompt and output contract with this model.** Given whole pairs with `user` and `assistant` fields and a free choice of kind, the model preferred short assistant replies as `assistant_claim`s, the easiest items to quote exactly, over user-stated facts.
- **Next step: a prompt and contract revision.** Examples: summarize user statements first; disallow acknowledgements; require at least one item per value-bearing user message; or present user messages only. Each needs an ADR-192 amendment and a measurement on a **held-out** corpus, because tuning on this corpus would inflate the result.
- **Until then, the flag has no measured benefit.** The harness `/status` now says so.

## Limits

- 12 scored synthetic cases by one author, with one answer draw per cell.
- The reductions from the draft protocol are listed in the v1 protocol. Window corrections, the route cell, the summary variance draws and the owner's blinded review were not run.
- Timings include instrumentation and are not SLOs.
