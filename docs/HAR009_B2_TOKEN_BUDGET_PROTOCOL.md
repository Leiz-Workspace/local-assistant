# HAR-009-B2 — Frozen paired token-pressure benchmark

**Purpose:** Fix the corpus, the arms, the design checks, the scoring and the analysis plan **before any native completion**. This measures the new opt-in `token-budget` history policy ([ADR-189](ADR/189-opt-in-token-budget-history-window.md)) under real token pressure, against the legacy composer and extractive compaction. [B1 protocol](HAR009_B1_RETENTION_PROTOCOL.md), [strategy guide](CONTEXT_MANAGEMENT_STRATEGIES.md), [backlog](progress/HARNESS_PRODUCT_BACKLOG.md). Date: 2026-11-11.

## Corpus

`benchmarks/context_budget.py` defines 12 synthetic dialogues in two regimes. Every question ends with a one-line answer instruction.

**Long regime (token pressure), 8 cases.** 16 pairs. Each filler pair carries a deterministic synthetic worker log of 96 lines (about 2,900 native tokens per pair), so the full history exceeds the hard input limit and every arm must drop pairs. Target pairs are short.

| Kind | Cases | Placement | Correct answer needs |
|---|---|---|---|
| `early_fact` | Kestrel (EN), Sơn Ca (VI) | Unmarked fact at pair 2 or 3 | The right code, never the distractor |
| `marked_constraint` | Heron (EN), Bồ Câu (VI) | Rule at pair 1 whose user message opens with `Rule:` / `Quy tắc:`; detail at pair 15 | The rule applied to the detail (`HRN-8812`, `150 phút`) |
| `unmarked_constraint` | Osprey (EN), Chim Sẻ (VI) | The same kind of rule at pair 1 without a marker; detail at pair 15 | The rule applied (`2027-03-04`, `MH-CS-0315`) |
| `stale_marked_rule` | Hydra (EN), Đại Bàng (VI) | Marked decision at pair 1 (`Decision:` / `Quyết định:`), unmarked correction at pair 6 | The corrected value, never the old one |

**Short regime (many short turns, no token pressure), 4 cases.** 40 short pairs from fixed filler pools: `early_fact` at pair 2 (Lynx EN, Họa Mi VI), `contradiction` with the old value at pair 3 and the correction at pair 25 (Mantis), and `unfinished_citation` at pair 4 (Puffin).

The tests check that evidence and stated answers occur only in target pairs, never in fillers or the question; that stale and distractor tokens never occur in fillers or the question; and that only the declared pair-1 rules carry an importance marker.

## Arms

All arms use the same CORE model and configuration, preset `fast`, `max_tokens` 512 (hard input limit 32,000 tokens, soft target 25,600 at the default ratio 0.8), temperature 0.7 and native streaming. Each case runs once per arm, and the arm order rotates cyclically across cases.

| Arm | `history_policy` |
|---|---|
| `legacy` | none: the existing composer (11 recent pairs, then hard-limit trimming) |
| `budget` | `token-budget` with defaults |
| `compact` | `extractive-compact` with defaults (window 11, soft target 25,600, up to 8 extracts), using the actual owner-bound RAM archive |

## Design check (before the freeze)

Before the freeze, the runner composes every case under every arm with the native template and tokenizer only (no completion). It stops with `DESIGN_INVALID` if a placement of `legacy` or `budget` differs from the design; `compact`'s placements are recorded but not checked:
- **Short regime:** `legacy` keeps exactly pairs 30–40, and `budget` keeps all 40 pairs.
- **Long regime:**
  - `legacy` never reaches pairs 1–4, and it keeps the pair-6 correction in the stale cases;
  - `budget` never reaches pair 6, and it keeps pair 1 only when its user message is marked.

The composition plan (retained pairs, input tokens and fact presence per case and arm) is part of the freeze.

**Calibration.** The log length was chosen with this composition-only check, and no completion was made. The output of the first calibration was not saved. It was rerun on the final code and recorded in `data/evaluations/context-budget-b2-calibration-20261111/calibration.json`, which supports the figures below. At 92 lines, `budget` kept 11 pairs for Heron, which met the soft target within 5 tokens; this is a knife-edge placement. At 96 lines, every check passes with margin: `legacy` stays at least 2,400 tokens under the hard limit.

The 92-line calibration also showed a compaction property worth recording. When the compaction window landed within about 50 tokens of the soft target, the archive capsule pushed the input over it, and no extract was admitted (Kestrel and Hydra lost their facts). At 96 lines this did not occur.

## Scoring and analysis (pre-registered)

- **Strict success and presence.** These are the B1 rules. Every required group must appear in the first streamed answer and no forbidden token may appear. Presence means every evidence token appears in the composed native input. There is no repair, resampling, retry or alternative credit.
- **Primary measure:** strict successes per arm, out of 12.
- **Secondary measures:**
  - stale answers;
  - presence, and strict success when the facts were present;
  - results per kind and per regime;
  - paired gains and regressions against `legacy`, by case;
  - upper-median and maximum input tokens;
  - preparation, first-text and total seconds;
  - sampled CORE RSS and GPU process peaks.
- **Design-derived hypotheses** (stated before the run, not pass criteria):
  1. `budget` keeps all four short-regime facts, while `legacy` keeps none of them.
  2. Under token pressure, `budget` keeps marked rules and loses unmarked early facts and unmarked rules, like `legacy`.
  3. The risk case: in `stale_marked_rule`, `budget` keeps the marked old decision and drops the newer unmarked correction, while `legacy` keeps the correction. This is where wrong priority would show as stale answers.
- **No adoption.** No default, adoption or quality claim follows from this benchmark; that decision stays with the owner.

## Freeze and limits

- **Freeze.** `frozen-inputs.json` is written after the design check and before the first completion. It holds:
  - the corpus, the arms and the options;
  - the hard and soft budgets;
  - the composition plan;
  - the native PID and start ticks;
  - the SHA-256 of the benchmark, B1 helper, composer, reduction, archive, inference, presets and model configuration files.
- **Bounds.** There are 36 planned native completions and no retries. A preparation or stream failure stays in the record as a failed first outcome. Raw requests and results go to an owner-private directory under `data/evaluations/`.
- **What this is not.** These are controlled synthetic dialogues by one author, with one draw per cell at temperature 0.7.
  - The questions name each case's unique project, so lexical extraction is again favoured.
  - The marker hypothesis depends on users actually marking rules.
  - Timings include instrumentation and are not SLOs.
  - Prompt caching across arms may shorten later timings.
  - Sampled memory is the warm process footprint.

## Corrections after the independent review (2026-11-11)

- **Campaign 2.** An independent code review of campaign 1 found a selection bug in `token-budget`. Marked pairs right behind the anchor used up the importance share and the probes. The selection order was fixed ([ADR-189](ADR/189-opt-in-token-budget-history-window.md)), and the protocol and benchmark were rerun unchanged on the fixed code. Both campaigns are reported in the [result](HAR009_B2_TOKEN_BUDGET_RESULT.md).
- **Wording and tests.** The design-check scope and the calibration source above were stated more precisely. The corpus test now also asserts that evidence never appears in the question; the corpus already satisfied this. No corpus, arm, scoring or analysis rule changed.
