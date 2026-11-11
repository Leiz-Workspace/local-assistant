# HAR-009-B2 — Token-budget history result

**Purpose:** Record the native outcomes of the frozen paired token-pressure benchmark for the new opt-in `token-budget` history policy, against the legacy composer and extractive compaction. [Protocol](HAR009_B2_TOKEN_BUDGET_PROTOCOL.md), [ADR-189](ADR/189-opt-in-token-budget-history-window.md), [public receipt](evidence/context-budget-b2-20261111.json). Date: 2026-11-11.

**Status:** measurement COMPLETE on the committed code. Campaign 2 ran 36 of 36 first native completions with no retries, 152 s from the freeze to the summary. Campaign 1 is retained below as history. Adoption is not decided here.

## Two campaigns

- **Campaign 1** (`data/evaluations/context-budget-b2-20261111`) ran the protocol on the first implementation.
- **The independent code review then found a selection bug.** Marked pairs right behind the anchor, which the recent run keeps anyway, used up the importance share and the 8 probes. As a result, an older marked rule was dropped as soon as recent pairs were marked too.
- **The fix.** The selection order was changed: recent share first, then marked pairs, then the recent extension ([ADR-189](ADR/189-opt-in-token-budget-history-window.md)). A regression test was added.
- **Campaign 2** (`data/evaluations/context-budget-b2-20261111-run2`) reran the unchanged protocol and benchmark on the fixed code. Only `src/application/services/context_reduction.py` differs between the two freezes.
- **The fix did not change this corpus.** The composition plan is identical in both campaigns, because no case marks a pair right behind the anchor.
- **The answers were stable.** All 36 cells had the same strict outcome in both draws (0 flips), although only 19 of 36 answer texts were identical at temperature 0.7.

## Run (campaign 2)

- **Model and runtime.** Approved CORE `qwen3.5-9b-core`. The weights SHA-256 `073a9275…` and the runtime pin `5c8854fd…` were checked before each start (command output, not stored in the receipt). CORE was started with the unchanged `scripts/start-core.py` as PID 980039; its log shows context 32,768 and one slot. It was stopped with SIGINT afterwards, and the launcher exited 0.
- **Parameters.** Preset `fast`, `max_tokens` 512, so the hard input limit was 32,000 and the soft target 25,600. Temperature 0.7, native streaming.
- **Design check and freeze.**
  - The composition-only design check passed with no violations.
  - `frozen-inputs.json`, including the composition plan, was written before the first completion.
  - After the run, its SHA-256, the source hashes and the corpus were checked again, and none had changed.
  - The retained pairs in every attempt matched the frozen plan.
- **Calibration.** The log length was chosen with a composition-only check, recorded in `data/evaluations/context-budget-b2-calibration-20261111/calibration.json`. It made no completions and was rerun on the final code.

## Results (strict first answers, 12 cases per arm, campaign 2)

| Arm | Strict | Stale | Facts in context | Strict when present | Long (8) | Short (4) |
|---|---:|---:|---:|---:|---:|---:|
| `legacy` | 3 | 0 | 2 | 2 | 3 | 0 |
| `budget` | 7 | **2** | 6 | 6 | 3 | **4** |
| `compact` | **11** | 0 | **12** | 11 | 7 | 4 |

Per kind (strict):

| Kind | `legacy` | `budget` | `compact` |
|---|---|---|---|
| `early_fact`, long (Kestrel, Sơn Ca) | 0/2 | 0/2 | 2/2 |
| `marked_constraint`, long (Heron, Bồ Câu) | 0/2 | **2/2** | 2/2 |
| `unmarked_constraint`, long (Osprey, Chim Sẻ) | 1/2 | 1/2 | 1/2 |
| `stale_marked_rule`, long (Hydra, Đại Bàng) | 2/2 | **0/2, both stale** | 2/2 |
| short regime: two facts, contradiction, unfinished | 0/4 | 4/4 | 4/4 |

Paired comparison against `legacy` (identical lists in both campaigns):

| Arm | Gains | Regressions |
|---|---|---|
| `budget` | 6: Heron, Bồ Câu, Lynx, Họa Mi, Mantis, Puffin | **2: Hydra, Đại Bàng** |
| `compact` | 8: Kestrel, Sơn Ca, Heron, Bồ Câu, Lynx, Họa Mi, Mantis, Puffin | 0 |

Cost per regime. These are upper medians, computed from the receipt rows over the 8 long or 4 short cases; maxima are in brackets.

| Arm | Input tokens long | Input tokens short | First text long / short | Total long / short | Preparation long |
|---|---:|---:|---:|---:|---:|
| `legacy` | 29,565 (29,599) | 418 (458) | 6.41 s / 0.29 s | 6.63 s / 0.52 s | 0.043 s (0.061) |
| `budget` | 23,711 (23,754) | 1,230 (1,382) | 5.24 s / 0.40 s | 5.45 s / 0.64 s | 0.182 s (0.191) |
| `compact` | 23,996 (24,081) | 1,466 (1,485) | 5.20 s / 0.54 s | 5.38 s / 0.78 s | 0.134 s (0.154) |

The sampled CORE peaks across all 36 calls were RSS 10,195,752 KiB (about 9.72 GiB) and GPU process allocation 8018 MiB, from 728 samples, all COMPLETE.

## Reading the results

- **Placements were fixed by design; the answers are the measurement.** The design check guaranteed where each arm's window falls:
  - `budget` keeps all 40 short pairs;
  - it keeps pair 1 only when marked;
  - it never reaches the pair-6 correction.

  What the run measured is how the model answered from those contexts:
  - short regime: `budget` 4/4 against `legacy` 0/4;
  - marked rules under pressure: 2/2 against 0/2;
  - **both stale cases: `budget` answered with the old value** (Tuesday, Hà Nội), while `legacy`, which kept the correction, was right.

  The two stale answers are the only regressions. They confirm that the predicted priority risk turns into wrong answers when it occurs.
- **Presence predicts success.** Every strict success except Osprey came from an arm that held the facts. When the facts were present, `budget` succeeded 6/6 and `compact` 11/12.
- **`compact` retained the most again,** with 12/12 presence, 0 stale answers and 0 regressions. It held both the old and the corrected value in each stale case, and the model chose the correction both times. Each question names a unique project, so lexical extraction was easy (see Limits); this is an upper bound.
- **Cost under pressure.** Both new arms kept long-history input at upper medians of 23.7k (`budget`) and 24.0k (`compact`) tokens, against 29.6k for `legacy`. Their first text arrived about 1.2 s earlier.
  - Preparation costs about 0.1 s more for both new arms, because of the extra native counts.
  - On short histories they use more tokens than `legacy` (1.2–1.5k against 0.4k), but this is small in absolute terms.
- **`budget` against `compact`.** `budget` does not retain more on this corpus. Its advantages are mechanical: no archive, no JSON capsule, and a per-pair *reason* in the receipt (every mode lists retained and evicted pairs). The calibration also showed a `compact` weakness. At 92 log lines, its window landed within about 50 tokens of the soft target (25,650 and 25,663 tokens). The archive capsule then left no room for extracts, so Kestrel and Hydra lost their facts. At 96 lines this did not occur.

## Notable first outcomes (kept as recorded)

- **Osprey:** in both campaigns, all three arms answered "2027-03-04", including `legacy` and `budget` without the rule in context. Here the model answered in ISO form even without the rule, so this case does not show rule retention.
- **Chim Sẻ:** `compact` held the rule but answered "MH-CS-315" instead of the four-digit "MH-CS-0315". `legacy` and `budget`, without the rule, answered with "315". Unmarked-rule retention therefore shows only in presence, not in strict scores.
- **`legacy` without the facts.**
  - It guessed in some cases: campaign 1 gave port 8080 for Lynx, "2.0" for Họa Mi and a generic MantisBT limit for Mantis; campaign 2 gave port 443 for Lynx and "100 requests per minute" for Mantis.
  - In the other cases it said it had no information.
  - None of these guesses contains a forbidden token, so none counts as stale.

## Campaign 1 (retained history)

Campaign 1 ran the first implementation from 16:47:37 to 16:50:08 (151 s from the freeze to the summary), with CORE as PID 936050.
- **Same outcomes.** It had the same strict, stale, presence and paired results as campaign 2: `legacy` 3/12, `budget` 7/12 with the same 2 stale answers, and `compact` 11/12.
- **Independent check.** Its own rescoring and presence check also found 0 mismatches.
- **Resources.** Upper-median first text was 6.35, 5.13 and 5.14 s over all 12 cases; sampled peaks were RSS 10,200,484 KiB and GPU 8018 MiB.
- **Record.** Its summary is embedded in the public receipt (`first_campaign`).

## Independent check (campaign 2)

- **Rescoring and plan.** All 36 rows were rescored from the raw answers, with 0 mismatches. Presence was recomputed from the saved request payloads, with 0 mismatches. The retained pairs matched the frozen composition plan in every row, also 0 mismatches.
- **Integrity.** The frozen hash, the source hashes and the corpus identity were confirmed after the run.
- **Independent reviews before this campaign.**
  - A code review found the selection bug that led to campaign 2.
  - A fact review of the campaign-1 documents led to these corrections: calibration evidence, hypothesis wording, the token range, the per-regime source and maxima, `legacy`'s guesses, and the receipt advantage.

## Limits

- **Corpus.** 12 synthetic dialogues by one author: 8 long-turn and 4 short-turn cases, two per long kind.
  - This is not general conversation quality and not independent human review.
  - Osprey and Chim Sẻ cannot show unmarked-rule retention in strict scores.
  - No case marks a pair right behind the anchor, so the fixed bug is covered by software tests only.
- **Placement by design.** The correction is deliberately placed outside `budget`'s window. The stale result therefore shows that the risk exists, not how often it occurs in real use.
- **Easy lexical retrieval.** Every question names its case's unique project, which favours `compact`'s extraction.
- **Sampling and timing.**
  - Two campaigns give two draws per cell at temperature 0.7, on different code for `budget`'s selection only.
  - Prompt caching across arms may shorten later timings.
  - Timings include instrumentation and are not SLOs.
  - Sampled memory is the warm process footprint.
- **Not measured.** Output tokens, explicit recall, LLM summaries, tool and task state, and durable offload.

## Consequences for HAR-009

- **B2 is implemented and measured** as an experimental opt-in mode, with these effects:
  - It removes the fixed 11-pair cutoff when the history fits.
  - It always gives the immediate conversation a share of the budget.
  - It honours explicit user markers under pressure.
  - Its measured cost is stale answers when a marked rule is later corrected without a marker.
- **Before any default use,** the marker rule needs a way to let later corrections win. Two options: give newer pairs that mention the same subject equal priority, or combine the mode with compaction's extracts. Any such change needs its own ADR and a rerun of this protocol.
- **C1 and D1 stay pending.**
- **No default change.** Choosing a default policy remains the owner's decision.
