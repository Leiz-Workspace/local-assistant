# HAR-009-C1 — Frozen working-state benchmark

**Purpose:** Fix the corpora, arms, client rule, design checks, scoring and analysis plan **before any native completion** for the opt-in working state ([ADR-190](ADR/190-opt-in-source-bound-working-state.md)). [B2 protocol](HAR009_B2_TOKEN_BUDGET_PROTOCOL.md), [backlog](progress/HARNESS_PRODUCT_BACKLOG.md). Date: 2026-11-11.

## Part A — B2 corpus with and without state

The 12 frozen B2 dialogues (`benchmarks/context_budget.py`, unchanged) are re-run with three arms:

| Arm | `history_policy` |
|---|---|
| `legacy` | none |
| `budget` | `token-budget` (B2 behaviour) |
| `budget_state` | `token-budget` with `working_state: true` |

Question: does the freshness rule remove B2's stale answers (Hydra, Đại Bàng) without new regressions?

## Part B — multi-window dialogues above the request bound

`benchmarks/context_state.py` defines 6 dialogues of 199 short pairs plus a question as pair 200.
- **Fillers.** They come from the B2 short pools.
- **Target placement.** All targets lie in pairs that the client drops before the question. The only exception is the invoice detail at pair 199.

| Case | Kind | Targets |
|---|---|---|
| `mw-decision-region` (EN) | keyed decision update | `Decision[db-region]` Frankfurt at pair 3, Warsaw at pair 70 |
| `mw-rule-invoice` (EN) | early rule | `Rule:` prefix INV-ACME- at pair 2, detail "number 5521" at pair 199 |
| `mw-todo-open` (EN) | todo closed | `Todo[backup]` at 5, `Todo[cert]` at 40, `Done[backup]` at 90 |
| `mw-goal-vi` (VI) | goal | `Mục tiêu:` Postgres 17 at pair 1 |
| `mw-decision-vi` (VI) | keyed decision update | `Quyết định[máy-chủ]` Hà Nội at 4, Đà Nẵng at 80 |
| `mw-unmarked-control` (EN) | unmarked fact (negative control) | port 9464 stated without a marker at pair 3 |

**Client rule.** The runner replays the CLI exactly:
- before each request, if the local history already holds 256 messages, it drops the oldest 32 pairs;
- this happens before requests 129, 161 and 193, so the final `history_offset` is 96;
- the `legacy` arm keeps the last 22 messages, as the existing CLI does without a policy.

The state arm obtains its carried state from real native compositions (template and tokenizer only) of the request just before each drop. The arms are `legacy`, `budget_drop` (token-budget, client drops, no state) and `budget_state` (token-budget with carried working state).

## Design check, freeze and scoring

- **Design check (before the freeze).** The runner composes every attempt with the native tokenizer and stops with `DESIGN_INVALID` on any violation:
  - Part A: `legacy` and `budget` placements must be as in B2, and `budget_state` must keep pairs 1 and 6 in both stale cases.
  - Part B: the drop and state arms must end at offset 96. No target may remain in the final window; the invoice case is exempt from this check, because its detail is pair 199. The state arm must carry items, except in the unmarked control.
- **Freeze.** `frozen-inputs.json` holds:
  - both corpora, the arms and the client rule;
  - the options: preset `fast`, 512 tokens, temperature 0.7, native streaming, no retries;
  - the full composition plan;
  - the native PID and start ticks;
  - the SHA-256 of 13 source files.
- **Scoring.** These are the B1 rules: strict means every required group is present and no forbidden token appears; presence means every evidence token is in the composed input.
- **Measures:**
  - primary: strict per arm in each part;
  - secondary: stale answers, presence, results per kind, paired gains and regressions against `legacy`, input tokens, preparation, first-text and total seconds, and sampled CORE peaks.
- **Design-derived hypotheses** (not pass criteria):
  1. Part A: `budget_state` keeps the Hydra and Đại Bàng corrections, and the stale answers disappear; other cases match `budget`.
  2. Part B: `budget_state` answers the five marked cases from the carried state, while `budget_drop` and `legacy` cannot.
  3. The negative control fails in every arm, because the state carries only marked lines.
- **No adoption.** No default or adoption claim follows from this benchmark.

## Limits

- **The corpora.** These are synthetic dialogues by one author.
  - Part B checks that the mechanism carries marked lines end to end and that the model uses them. By design the other arms cannot know the answers there, so it does not measure semantic quality.
  - The freshness rule is tested only on corrections that share at least 3 terms with the item.
- **Sampling and timing.** One draw per cell, so results can differ between runs. Timings include instrumentation and are not SLOs.

## Corrections after the independent reviews (2026-11-11)

- **Campaign 2.** An independent code review after campaign 1 found defects in the working-state code: a crash on Turkish capitals, unretirable items failing closed, unreported malformed lines, repeated freshness work and CLI version skew. They were fixed (see ADR-190), and the unchanged protocol and benchmark were rerun on the fixed code. Both campaigns are reported in the [result](HAR009_C1_WORKING_STATE_RESULT.md).
- **Wording.** A fact review made the part B design-check wording above match the code, which exempts the invoice case and the unmarked control. No corpus, arm, scoring or analysis rule changed.
