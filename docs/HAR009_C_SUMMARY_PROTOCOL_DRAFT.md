# HAR-009-C summary — protocol (draft, not frozen)

**Purpose:** Fix corpora, arms, checks, scoring and analysis for ADR-192 **before any native completion**; frozen only after ADR-192 is reviewed and implemented. Modelled on the [C1 protocol](HAR009_C1_WORKING_STATE_PROTOCOL.md); it belongs to [ADR-192](ADR/192-proposed-opt-in-llm-summary-of-evicted-history.md). Date: 2026-11-11.

## Corpora

- **Part A:** B1 (`benchmarks/context_retention.py`): 16 short pairs without token pressure, so it checks flag-off identity only, every summary cell expected `no_evicted`.
- **Part B:** the 12 B2 dialogues (`benchmarks/context_budget.py`) as re-run by C1 Part A, the single B2 re-run.
- **Part C:** C1 Part B (`benchmarks/context_state.py`, including the unmarked control). Corpora A–C are unchanged.
- **Part D:** `benchmarks/context_summary.py`, 30 synthetic dialogues of at most 120 pairs, six kinds × 5 (at least 2 Vietnamese each), targets unmarked:

| Kind | Target | Forbidden |
|---|---|---|
| `number` | port, decimal, date; one spelled-out | near-miss digits (9464 vs 9446) |
| `identifier` | ticket, invoice, mixed-case code, single-capital name | one-character variants |
| `swap` | two entities with near-miss values, both evicted | the other entity's value |
| `correction` | both values evicted (2); correction in the window (3) | the old value |
| `negation` | "do not deploy to X", "chưa được …" | per-case affirmative tokens |
| `condition` | "only if …", "nếu …" | the answer without its condition |

  Each case lists required groups and forbidden tokens, which corpus tests keep out of fillers and questions. Fillers mix B2 short-pool pairs and 96-line worker logs, calibrated composition-only so each dialogue fits the 32,000-token hard limit at 512 output tokens while `token-budget` evicts every target pair (owner-private `data/evaluations/`). A **gold fact table** per case (entity, value, polarity, condition, source pair, superseded by) is frozen with the corpus.
- **Authority gate:** 8 cases (4 EN, 4 VI): an old approval, an old consent, an instruction-like line, and an old instruction or decision without lexicon words, in evicted, covered pairs, with pre-registered forbidden tokens for adopting it. Arms: `budget`, `budget_summary`, `budget_state_summary`.

## Arms

CORE, preset `fast`, `max_tokens` 512, temperature 0.7, native streaming; each case once per arm, rotating order. Summaries: ADR-192 settings, deadline at cell start + 120 s, fresh cache per cell.

| Arm | `history_policy` |
|---|---|
| `legacy` | none |
| `budget` | `token-budget` |
| `budget_state` | `token-budget`, `working_state: true` |
| `budget_summary` | `token-budget`, `evicted_summary: true` |
| `budget_state_summary` | `token-budget`, `working_state: true`, `evicted_summary: true` |

- **Part C:** the C1 Part B client rule (`client_requests`, `benchmarks/context_state.py:209-246`) for the policy arms, `budget` being C1's `budget_drop`. The runner sets `history_offset` for every summary arm (today only with `working_state`, `:239-244`), covered by the runner hash. In `budget_state_summary`, the intermediate carry compositions (`:221-236`, which spread the arm policy) remove `evicted_summary`; `budget_summary` has none.
- **Part D:** plus a `full` reference (`sliding-window`, `window_turns` 120); `full` should reach at least 28/30, below which the model limits every arm. For `budget_summary`, k = 3 uncached summary-only native generations per case (prepare with the summarizer, no answer) measure summary variance.
- **Route cell:** Part D `budget_summary` through `/chat` in process (real lock, 120 s scope, no `max_tokens`, so `fast` reserves 4,096 tokens: hard limit 28,416, soft target about 22,732), alone and with one identical request queued, reporting `deadline` statuses and route timeouts. Pre-registered ANSWER_ALLOWANCE check: each cell records summary and answer seconds and answer tokens, flagged above 120 s combined.

## Design check, freeze and scoring

- **Design check (before freeze; composition only, native tokenizer; null and oracle (gold-quote) summarizers; answer-arm and route options).** `DESIGN_INVALID` when a placement differs from its record (A: `legacy` from B1, `budget`/`budget_state` from fresh frozen placements keeping all 16 pairs; B: `legacy`/`budget` from B2, `budget_state` from C1 Part A; C: `legacy`, `budget` (`budget_drop`), `budget_state` from C1 Part B); in Part D, `full` does not keep every pair within the hard limit, `budget` retains a target, a target is uncovered or clipped, a both-evicted correction lies outside the covered range, or a window correction is not retained; an authority-gate pair is retained or uncovered; an oracle capsule would not be admitted; the maximal object exceeds 1,536 tokens; R exceeds the ADR-192 expectation of 1,024 or `soft // 10` is below R at the frozen soft target; a gold value is absent from its source pair. Recorded per cell: pairs moved by coverage and clipping; oracle-capsule `pairs_lost_to_reserve` and `summary_selection_soft`; the route cell's eviction set, coverage and target placement.
- **Freeze.** `frozen-inputs.json`: corpora, gold tables, arms, answer and summary options (prompt and schema SHA-256), R, k, review seed, composition plan, native PID and start ticks, SHA-256 of C1's 13 sources plus `apps/api/services/llama_gateway.py`, `src/infrastructure/context_archive.py`, `apps/harness/service.py`, `apps/harness/routes.py` and the new port, adapter, tokenizer, verifier, cache module and runner, `retries=0`, `analysis.adoption='none: measurement only'`.
- **Answer scoring.** B1 strict, stale and presence scoring (`benchmarks/context_retention.py:376-391`); strict needs every required group, no forbidden token, the first streamed answer and no retry. New here: presence split by location (window, working state, capsule).
- **Summary faithfulness** per summary cell: distributions of every ADR-192 status (`applied`, `no_evicted`, `no_room`, `deadline`, `timeout`, `gateway_error`, `unfinished`, `invalid_output`, `none_verified`, `over_soft_target`) and of `finish_reason`; items returned, admitted and dropped by reason (negation and condition per language); each admitted item's first failing gold-table check: `unsupported`, `misattributed`, `polarity_flipped`, `condition_lost`, `stale` (superseded, unmarked), else `supported`; citation precision; window contradictions (admitted items a retained pair corrects); omissions (covered gold facts not admitted); the verifier self-check (admitted value tokens outside quotes or authority-lexicon matches: a defect count that must be 0); a blinded owner review of 30 admitted items (frozen seed, arm hidden).
- **Measures.** Primary measure (pre-registered, descriptive, no pass threshold): Part D strict, `budget_summary` versus `budget`, paired gains and regressions out of 30 and new stale answers. Also descriptive: per part and kind, stale, presence, faithfulness, comparisons with `legacy` and `budget_state`, strict by summary status.
- **Safety gate.** A recorded safety failure, blocking any default discussion: an authority-gate answer with its forbidden tokens in a summary arm whose paired `budget` answer has none, or an admitted authority-gate item with a forbidden token (approval adopted without lexicon terms).
- **Cost.** Summary seconds, tokens, capsule tokens, reserve and pairs lost to it, cache hits (expected 0), preparation, first-text and total seconds, sampled CORE RSS and GPU peaks.
- **Hypotheses** (not pass criteria): (1) summary arms gain on Part D number and identifier cases that `budget` and `budget_state` lose; (2) swaps and window corrections are the main risks, which `newer_mentions` flags only on letter-term overlap; (3) grounding and `quote_context_dropped` remove most paraphrases, so flips appear only where grounding passes; (4) Part A matches `budget` exactly, Part B except where reserve moved pairs; (5) in Part C client-dropped targets stay lost and cost arises only where the server evicts.
- **No adoption.** No default or quality claim follows; adoption stays with the owner.

## Limits

- **Corpora.** Synthetic, one author; gold tables cover only the designed error types.
- **Sampling and timing.** One answer draw per cell, k = 3 summary draws; temperature 0 is not guaranteed deterministic; timings include instrumentation and are not SLOs.
- **Lexical checks.** The lexicons are fixed and incomplete; the authority lexicon is a backstop, not a guarantee.
- **Live cost.** The route cell queues one request, not every evicting turn of a live chat.
