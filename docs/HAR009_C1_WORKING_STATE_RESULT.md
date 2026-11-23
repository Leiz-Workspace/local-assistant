# HAR-009-C1 — Working-state result

**Purpose:** Record the native outcomes of the frozen working-state benchmark for the opt-in source-bound working state ([ADR-190](ADR/190-opt-in-source-bound-working-state.md)). [Protocol](HAR009_C1_WORKING_STATE_PROTOCOL.md), [public receipt](evidence/context-state-c1-20261111.json). Date: 2026-11-11.

**Status:** measurement COMPLETE on the code in this change (source hashes in the receipt). Campaign 2 ran 54 of 54 first native completions with no retries, 165.8 s from the freeze to the summary. Campaign 1 is retained as history. Adoption is not decided here.

## Two campaigns

- **Campaign 1** (`data/evaluations/context-state-c1-20261111`) ran the protocol on the first implementation.
- **The independent code review then found:**
  - Turkish `İ`/`ı` in a marked line crashed the request (KeyError, 502);
  - unkeyed items could never be retired, so failing closed above 64 items or 32 KiB could leave a CLI session unusable;
  - malformed marker lines were skipped without a report;
  - freshness repeated work for every item;
  - the CLI sent the new fields even without `--working-state`.
- **The fixes:**
  - parsing on the case-folded line;
  - over-limit items dropped with a report (notes and corrections first, then oldest);
  - `skipped_lines` with reasons;
  - cached terms;
  - the new fields sent only with working state.

  ADR-190 records the changes.
- **Campaign 2** (`…-run2`) reran the unchanged protocol and benchmark on the fixed code. Of the 13 hashed sources, only `src/application/services/working_state.py`, `context_reduction.py` and `apps/cli/main.py` differ between the two freezes.
- **The composition plan is identical** in both campaigns: every arm saw the same context.
- **Two strict outcomes differed,** both in `budget_state`:
  - Osprey, a sampling difference with no rule in context;
  - Đại Bàng, see below.

  Only 18 of 54 answer texts were identical at temperature 0.7.

## Run (campaign 2)

- **Model and runtime.** Approved CORE `qwen3.5-9b-core`. The weights SHA-256 `073a9275…` and the runtime pin `5c8854fd…` were checked before each start (command output). CORE was started with the unchanged `scripts/start-core.py` as PID 1184292 and stopped with SIGINT afterwards; port 8080 was free.
- **Rejected first attempt.** The first rerun attempt passed a wrong PID, which was the shell. The preflight rejected it (`explicit_llama_server_pid_required`) before any directory, composition or completion.
- **Parameters.** Preset `fast`, `max_tokens` 512, temperature 0.7, native streaming.
- **Design check and freeze.**
  - The composition-only design check passed with no violations.
  - `frozen-inputs.json`, including the composition plan and the carried states, was written before the first completion.
  - After the run, the source hashes and both corpora were checked again, and none had changed.
  - Every attempt's input tokens and presence matched the plan.
- **Owner-private records.** All raw files are under `data/evaluations/`, which Git ignores.

## Part A — B2 corpus with and without state (strict, 12 cases per arm)

| Arm | Campaign 2 strict | Stale | Facts in context | Campaign 1 strict (stale) |
|---|---:|---:|---:|---:|
| `legacy` | 3 | 1 | 2 | 3 (1) |
| `budget` | 6 | 3 | 6 | 6 (3) |
| `budget_state` | 7 | 2 | **8** | 9 (0) |

Stale cases (Hydra, Đại Bàng) in both campaigns:

| Arm | Facts in context | Strict, campaign 1 | Strict, campaign 2 |
|---|---|---|---|
| `budget` | 0/2 (correction dropped) | 0/2, both old value | 0/2, both old value |
| `budget_state` | **2/2** (pair 6 kept as `newer_related`) | 2/2 | 1/2 |

- **The mechanism worked in every attempt.** In all four `budget_state` stale attempts across the two campaigns, the freshness rule kept the unmarked correction beside the marked decision. Hydra was answered correctly both times.
- **Campaign 2 Đại Bàng.** The answer was correct but also named the old value: "hiện đang đặt ở Đà Nẵng (đã được cập nhật từ Hà Nội…)". The pre-registered rule forbids the old token, so it is scored stale, as recorded. No post-hoc credit was given. Without state, `budget` answered with the old value in all four attempts.
- **Osprey is sampling, not state.** No arm had the date rule in context. `budget` answered "March 4, 2027" in both campaigns. `budget_state` answered "2027-03-04" in campaign 1 and "March 4, 2027" in campaign 2. This case cannot show retention.
- **Everything else matched `budget`,** as designed. Unmarked facts and rules carry no state.
- **Against `legacy` (campaign 2):** `budget_state` had 6 gains and 2 regressions (Osprey, Đại Bàng); `budget` had 6 gains and 3 regressions (Osprey, Hydra, Đại Bàng). In campaign 1, `budget_state` had 0 regressions.

## Part B — 200-pair dialogues above the request bound (strict, 6 cases per arm)

| Arm | Strict (both campaigns) | Facts in context | Marked cases (5) | Unmarked control |
|---|---:|---:|---:|---|
| `legacy` (last 11 pairs) | 0 | 0 | 0/5 | fail |
| `budget_drop` (3 client drops, no state) | 0 | 0 | 0/5 | fail |
| `budget_state` (3 drops, carried state) | **5** | 5 | **5/5** | fail |

- **The carried state worked end to end in both campaigns** after three client drops (final offset 96):
  - the keyed updates (Warsaw, Đà Nẵng): the superseded Frankfurt and Hà Nội items were carried but not rendered;
  - the early invoice rule (INV-ACME-5521);
  - the open task after a keyed `done` closed the other one (portal TLS certificate);
  - the Vietnamese goal (Postgres 17).
- **Without state,** the other arms mostly said they had no information, or named filler items or invented tasks. For the invoice, they answered "5521" without the prefix. In campaign 2, `legacy` also guessed "Hà Nội" for the Vietnamese server question, which is scored stale.
- **The negative control behaved as designed.** An unmarked fact is not carried, and every arm invented a port. The state covers only lines the user marked.

## Cost (campaign 2)

These are upper medians computed from the receipt rows; maxima are in brackets. Token counts are identical in both campaigns because the plans are identical.

| Part / arm | Input tokens | First text | Preparation |
|---|---:|---:|---:|
| A long, `budget` | 23,711 (23,754) | 5.17 s | 0.179 s |
| A long, `budget_state` | 23,841 (23,899) | 5.10 s | 0.188 s |
| A long, `legacy` | 29,565 (29,599) | 6.34 s | 0.043 s |
| A short, `budget` / `budget_state` | 1,230 / 1,308 | 0.39 / 0.54 s | 0.048 / 0.049 s |
| B `budget_drop` / `budget_state` / `legacy` | 2,920 / 3,049 / 421 | 0.74 / 0.84 / 0.28 s | 0.103 / 0.100 / 0.017 s |

- **Token cost of the state.** Enabling working state costs 78 input tokens for the host policy line alone, which applies even when no item exists. With items it costs 139–140 tokens in part A (Heron, Bồ Câu) and 126–134 tokens in part B. In the stale cases, where the newer-related pair is also kept, it costs 169–181 tokens. The capsule itself was 185–267 bytes per case.
- **Resources.** The sampled CORE peaks across all 54 calls were RSS 10,172,132 KiB and GPU 8018 MiB, from 811 samples, all COMPLETE.

## Independent check (campaign 2)

- **Rescoring and plan.** All 54 rows were rescored with 0 mismatches. Presence was recomputed from the saved requests with 0 mismatches. Input tokens and presence matched the frozen composition plan in every row.
- **Integrity.** The frozen hash, the source hashes and both corpora (corpus B compared after JSON round trip) were confirmed after the run. Campaign 1's own check also found 0 mismatches.

## Limits

- **Corpus and sampling.** Synthetic dialogues by one author, with one draw per cell per campaign; Osprey and Đại Bàng flipped between draws. The strict rule penalises answers that mention the old value even when they state the new one.
- **Part B is a mechanism check.** The other arms cannot know the answers by design. The freshness rule was exercised natively only on corrections that share at least 3 terms with the marked item. A correction worded differently, or an unrelated pair sharing terms, is covered by unit tests only.
- **Carried state is client data** whose source hashes cannot be re-verified once the pairs are gone.
- **Not measured.** LLM summaries, tool output compaction, durable server-side state and UI controls.

## Consequences for HAR-009

- **C1 first slice is implemented and measured** as an experimental opt-in.
  - The freshness rule kept the correction next to the marked decision in every stale attempt. Answers were right in 3 of 4 attempts, and the fourth named both values.
  - The carried state lets a CLI conversation continue past the request bound without losing marked goals, rules, keyed decisions and open tasks: 5/5 in both campaigns, against 0/5 without state.
- **Still open.**
  - Unmarked information is lost once its pairs are dropped.
  - Automatic LLM summaries, tool-output compaction and durable or server-side state remain (C remainder, D1).
- **No default change.** Choosing a default policy remains the owner's decision.
