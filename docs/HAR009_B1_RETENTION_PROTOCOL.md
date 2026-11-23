# HAR-009-B1 — Frozen paired context retention benchmark

**Purpose:** Fix the corpus, the arms, the scoring and the analysis plan **before any native completion**. This measures how the existing explicit history policies retain old facts, constraints, corrected values and unfinished work, and at what cost. [Strategy guide](CONTEXT_MANAGEMENT_STRATEGIES.md), [ADR-187](ADR/187-opt-in-pinned-history-and-extractive-compaction.md), [backlog](progress/HARNESS_PRODUCT_BACKLOG.md). Date: 2026-11-11.

## Corpus

`benchmarks/context_retention.py` defines 12 synthetic dialogues. Each has 16 complete user/assistant pairs followed by one current question. Fillers come from fixed English and Vietnamese pools; the tests check that no filler contains an answer token, a distractor token or an evidence token. There are four item types with three cases each, and each type has one Vietnamese case.

| Type | Placement | What a correct answer needs |
|---|---|---|
| `early_fact` | Fact at pair 2, distractor in the same pair | The right code (for example G-17), never the distractor (G-18) |
| `pinned_constraint` | Rule at pair 1, detail at pair 15 | Apply the old rule to the recent detail (for example `OPS-4471`, 150 minutes, an amount in VND) and never use the retired form |
| `contradiction` | Old value at pair 3, correction at pair 12 | The corrected value, never the old one |
| `unfinished_citation` | Status at pair 4 | The remaining work and its ticket ID |

By design, the legacy composer keeps the 11 most recent pairs (6 to 16) and `window3` keeps pairs 14 to 16. Pairs 1 to 4 therefore fall outside both, while the correction at pair 12 falls inside legacy only.

## Arms

All arms use the same CORE model, configuration, preset `fast`, `max_tokens` 512, temperature 0.7 (the product gateway default) and native streaming. Each case runs once per arm, and the arm order rotates cyclically from case to case.

| Arm | `history_policy` |
|---|---|
| `full` | `sliding-window`, `window_turns` 16: all pairs, the reference ceiling |
| `legacy` | none: the existing composer branch |
| `window3` | `window_turns` 3 |
| `window3_pin1` | `window_turns` 3, `pinned_turns` [1] (the user pins the project brief) |
| `compact3` | `extractive-compact`, `window_turns` 3, using the actual owner-bound RAM archive |

Explicit recall (`recall_ids`) needs a second user step and is not measured here.

## Scoring and analysis (pre-registered)

- **Strict success.** Every required group appears in the first streamed answer (case-insensitive; alternatives within a group are interchangeable), and no forbidden (stale or distractor) token appears. There is no repair, resampling, retry or alternative credit.
- **Presence.** Every source-fact token of the case appears in the composed native input. This separates context retention from answer correctness.
- **Primary measure:** strict successes per arm, out of 12.
- **Secondary measures:**
  - stale answers;
  - presence;
  - per-type results;
  - paired gains and regressions of each arm against `legacy`;
  - median and maximum input tokens;
  - preparation seconds, first-text and total seconds (native stream);
  - sampled CORE RSS and GPU process peaks from the existing pinned-PID sampler.
- **Reference check:** `full` should reach at least 11/12. Below that, model capability limits every arm.
- **Engineering signal, not adoption:** an arm "improves retention" when it gains on cases that `legacy` loses, has no regression against `legacy`, and has no more stale answers than `legacy`. No default, adoption or quality claim follows from this benchmark; that decision stays with the owner.

## Freeze and limits

- **Freeze.** `frozen-inputs.json` is written before the first preparation. It holds the corpus, arms, options, the primary and secondary measures and the reference check, the native PID and start ticks, and the SHA-256 of the benchmark, composer, reduction, archive, inference, presets and model configuration files. The "improves retention" engineering signal is recorded only in this protocol file, which the freeze does not hash (it was written 43 s before the freeze).
- **Owner-private records.** Each attempt saves its request payload and result to an owner-private directory under `data/evaluations/`.
- **Bounds.** There are 60 planned native completions and no retries. A preparation or stream failure stays in the record as a failed first outcome.
- **Easy lexical retrieval by construction.** Each question names its case's unique project, which appears only in the target pairs, and fillers are off-topic, so `compact3`'s lexical extraction is favoured. Medians in the runner are upper medians (7th of 12).
- **What this is not.** These are controlled synthetic dialogues written by the same author, so the benchmark measures retention mechanics on such dialogues, not general conversation quality. Temperature 0.7 matches product behaviour but means one draw per cell. Prompt caching across arms may shorten later timings. Timings include instrumentation and are not SLOs. Sampled RSS and GPU values are warm process observations, not request-only memory.
