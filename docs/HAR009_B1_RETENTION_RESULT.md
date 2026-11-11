# HAR-009-B1 — Context retention result

**Purpose:** Record the first native outcomes of the frozen paired retention benchmark: which history arm keeps old facts, constraints, corrections and unfinished work, and at what cost. [Protocol](HAR009_B1_RETENTION_PROTOCOL.md), [public receipt](evidence/context-retention-b1-20261111.json). Date: 2026-11-11.

**Status:** measurement COMPLETE. 60 of 60 first native completions, no retries, campaign wall time 36 s. Adoption is not decided here.

## Run

- **Model and runtime.** Approved CORE `qwen3.5-9b-core`. The weights SHA-256 `073a9275…` and the runtime pin `5c8854fd…` were verified before start. CORE was started with the unchanged `scripts/start-core.py` as PID 881894, then stopped with exit 0 afterwards.
- **Parameters.** Preset `fast`, `max_tokens` 512, temperature 0.7, native streaming.
- **Freeze.** `frozen-inputs.json` was written before the first preparation. Its SHA-256, the source hashes and the corpus were checked again after the run, and none had changed.
- **Owner-private records.** The raw request and result files are in `data/evaluations/context-retention-b1-20261111`, which Git ignores.

## Results (strict first answers, 12 cases per arm)

| Arm | Strict | Stale | Facts in context | Early fact | Constraint | Contradiction | Unfinished + ticket | Input tokens (upper median/max) | First text (upper median) |
|---|---:|---:|---:|---|---|---|---|---:|---:|
| `full` (reference) | **11** | 0 | 12 | 3/3 | 2/3 | 3/3 | 3/3 | 564 / 642 | 0.32 s |
| `legacy` | 3 | 1 | 3 | 0/3 | 0/3 | 3/3 | 0/3 | 415 / 475 | 0.28 s |
| `window3` | 1 | 1 | 0 | 0/3 | 1/3 | 0/3 | 0/3 | 204 / 230 | 0.22 s |
| `window3_pin1` | 3 | 0 | 3 | 0/3 | 3/3 | 0/3 | 0/3 | 233 / 283 | 0.22 s |
| `compact3` | **12** | 0 | 12 | 3/3 | 3/3 | 3/3 | 3/3 | 1210 / 1277 | 0.37 s |

Paired comparison against `legacy`:

| Arm | Gains | Regressions |
|---|---:|---:|
| `full` | 8 | 0 |
| `compact3` | 9 | 0 |
| `window3_pin1` | 3 | 3 |
| `window3` | 1 | 3 |

"Upper median" means the 7th of 12 sorted values; the conventional medians are slightly lower, for example 1188.5 input tokens for `compact3` against 564 for `full`.

Further measurements:
- Upper-median preparation time was 0.047 s for `compact3`, compared with 0.016–0.028 s for the other arms.
- Upper-median total time per call was 0.45–0.57 s across arms.
- The sampled CORE peaks across all 60 calls were RSS 10,023,732 KiB (about 9.56 GiB) and GPU process allocation 8018 MiB, from 240 samples, all COMPLETE.

## Reading the results

- **Reference check passes.** `full` reached 11/12, so most failures in the other arms come from missing context, not from model capability.
- **Presence predicts success.** Every arm that kept the source facts (`full`, `compact3`) answered almost every case correctly. `legacy` succeeded only on the corrections at pair 12, which lies inside its 11-pair window. `window3_pin1` succeeded only on the pinned rules.
- **`full` and `compact3` tie on retention.** Both kept every source fact (12/12 presence). The strict 12 vs 11 gap is `full`'s Vega answer written in words, a scorer artifact from a single draw, not a retention difference, and `full` did it with under half of `compact3`'s input tokens.
- **Among the reduced windows (3 recent pairs), `compact3` retained the most:** 12/12, with no stale answers and no regressions against `legacy`. Its lexical extracts brought back pairs 1 to 4 and both values of each contradiction, and the model chose the corrected value in all three contradiction cases. This corpus made lexical retrieval easy (see Limits), so this is an upper bound.
- **The cost is real.** `compact3` used about 2.1× the input tokens of `full`, because these dialogues are short (about 600 tokens) and each extract carries JSON and provenance overhead. Its first text arrived about 0.05 s later. This corpus puts no token-budget pressure on any arm, so the benefit compaction gives on long histories is not measured here.
- **Pinning works only for what was pinned.** `window3_pin1` kept the rule but lost every other old fact.

## Notable first outcomes (kept as recorded)

- **`full` / `constraint-vega`:** the answer was "one hundred fifty minutes". That is semantically correct, but the pre-registered rule requires the digits "150", so it counts as a failure. No post-hoc credit was given; the rule's limitation is noted here.
- **`window3` / `constraint-saomai`:** the answer was correct ("4.200.000 đồng") even though the VND rule was not in context. The model fell back on a Vietnamese default; this is not retention, and `window3`'s single paired gain is this default. Because the currency is the natural default in a Vietnamese dialogue, `constraint-saomai` cannot show rule retention in any arm. Constraint evidence therefore rests on Orion and Vega: `window3_pin1` 2/2, `compact3` 2/2, `full` 1/2 (the miss is the digit rule only).
- **`legacy` and `window3` / `constraint-vega`:** both answered in hours, the retired form, because the rule at pair 1 had been evicted.

## Independent check

All 60 rows were rescored from the raw answers, and presence was recomputed from the saved request payloads, with 0 mismatches. The frozen hash, the source hashes and the corpus identity were confirmed.

## Limits

- **Corpus.** 12 synthetic dialogues by one author, three per type. This is not general conversation quality and not independent human review.
- **Sampling and timing.** One draw per cell at temperature 0.7. Prompt caching across arms may shorten later timings. Timings include instrumentation and are not SLOs. Sampled memory is the warm process footprint.
- **Easy lexical retrieval.** Each question names its case's unique project (Atlas, Orion, Hải Âu and so on), and that name appears only in the target pairs; fillers are off-topic, and 8 extract slots cover most of the 12–13 evicted pairs. `compact3`'s result is therefore an upper bound. Paraphrased or anaphoric questions, on-topic distractor turns and lexical omission were not tested.
- **Not measured.** Token pressure on long histories, output tokens, explicit `recall_ids`, LLM summaries, tool and task state, and durable offload.

## Consequences for HAR-009

- **B1 measurement is done** on this short synthetic corpus. Without token pressure, a full window keeps everything at the lowest cost. Among 3-pair windows, `compact3` retained the most and `sliding-window` with pins kept only what was pinned.
- **HAR-009-B2** (token-budget and importance-aware recent window) is next and must be measured under real token pressure. Reducing extractive compaction's overhead on short histories would be a separate item.
- **C1 and D1 stay pending.**
- **No default change.** Choosing a default policy remains the owner's decision.
