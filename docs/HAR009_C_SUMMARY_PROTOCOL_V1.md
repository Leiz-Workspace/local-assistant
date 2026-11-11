# HAR-009-C summary — frozen protocol v1

**Purpose:** Fix the first native measurement of the opt-in evicted-history summary ([ADR-192](ADR/192-proposed-opt-in-llm-summary-of-evicted-history.md)) **before any native completion**. It is a reduced version of the [draft protocol](HAR009_C_SUMMARY_PROTOCOL_DRAFT.md); every reduction is listed below. Date: 2026-11-11.

## Corpus (`benchmarks/context_summary.py`)

14 synthetic dialogues of 16 pairs plus a question. Pairs 1–7 are short (B2 short pools and the targets); pairs 8–16 carry 96-line synthetic worker logs, so `token-budget` evicts every target while `full` (`sliding-window`, window 120) keeps all pairs within the hard limit. No target is marked, so working state cannot hold it.

| Kind | Cases | Answer needs | Forbidden |
|---|---|---|---|
| `number` | Lynx (EN), Sơn La (VI) | 9464; 3.14 | 9446; 3.41 |
| `identifier` | Heron (EN), Cửu Long (VI) | rel-2026.11-B7; HĐ-CL-0928 | rel-2026.11-B1; HĐ-CL-0982 |
| `swap` | Osprey (EN), Thái Bình (VI) | the second entity's value | the first entity's value |
| `correction` | Mantis (EN), Bạch Đằng (VI) | the corrected value (both values evicted) | the old value |
| `negation` | Puffin (EN), Cà Mau (VI) | "No," / "Chưa," first | "Yes," / "Rồi," |
| `condition` | Falcon (EN), Phú Quốc (VI) | the condition | — |
| `authority_gate` | Atlas (EN), Hòa Bình (VI) | not scored; the capsule is checked | — |

Each case has a gold item: source pair, exact quote, grounded text and gold value. The tests check that gold quotes sit verbatim in their source pair and pass the production verifier, and that answers, forbidden tokens and evidence never occur in fillers. The tests also caught two corpus leaks before the freeze, both fixed: clock values that also occur as log timestamps, and a bare "no" that matches "unknown".

## Arms

CORE, preset `fast`, `max_tokens` 512, temperature 0.7, native streaming; each case once per arm, rotating order. Summaries use the ADR-192 settings with a deadline of 120 s from the start of each cell and no cache.

| Arm | `history_policy` |
|---|---|
| `full` | `sliding-window`, `window_turns` 120 (reference) |
| `legacy` | none |
| `budget` | `token-budget` |
| `budget_state` | `token-budget`, `working_state` |
| `budget_summary` | `token-budget`, `evicted_summary` |
| `budget_state_summary` | `token-budget`, `working_state`, `evicted_summary` |

## Design check and freeze

- **Design check.** Before the freeze, every cell is composed with the native tokenizer. Summary arms use an **oracle summarizer** that returns the gold item, so no model call is made. The run stops with `DESIGN_INVALID` in any of these cases:
  - `full` does not keep all 16 pairs;
  - `budget` or `budget_state` retains a target;
  - in a summary arm, the oracle capsule is not admitted, or a target is uncovered or clipped;
  - a gold quote is absent from its source.
- **Freeze.** `frozen-inputs.json` holds:
  - the corpus with the gold items;
  - the arms and the answer and summary options (prompt and schema SHA-256, generation settings, reserve);
  - the composition plan;
  - the native PID and start ticks;
  - the SHA-256 of 15 sources;
  - `retries=0`.

## Scoring

- **Answers.** The B1 rules apply: strict means every required group is present and no forbidden token; presence means every evidence token is in the input. Only the 12 non-authority cases are scored.
- **Primary measure** (descriptive, no pass threshold): strict for `budget_summary` against `budget`, with paired gains, regressions and new stale answers.
- **Secondary measures:**
  - per kind;
  - the reference check: `full` should reach at least 11 of 12;
  - the distribution of summary statuses;
  - faithfulness per summary cell: the gold value admitted, forbidden tokens admitted, and verifier self-check defects (value tokens outside the quotes, or authority-lexicon matches in admitted items). The self-check defect count must be 0.
  - the authority-gate capsules: no approval or consent wording may be admitted;
  - summary seconds and tokens, input tokens, preparation and first-text seconds, and sampled CORE peaks.
- **No adoption.** No default change and no quality claim; adoption stays with the owner.

## Reductions from the draft (and why)

- **Parts A, B and C dropped.** Part A (B1 flag-off identity) is covered by software tests. Parts B and C (the B2 and C1 corpora) are left for a later campaign.
- **A smaller Part D.** 12 scored cases instead of 30, so kinds have 2 cases each, not 5; window corrections are not included.
- **Authority gate.** 2 cases instead of 8; only capsule contents are checked, not answers.
- **Not run in this campaign:**
  - the route cell (`/chat` with a queued request);
  - k = 3 summary-only variance draws;
  - the blinded owner review of 30 admitted items.
- **Why.** These reductions keep one bounded campaign on the shared host. Each dropped element remains a follow-up item.

## Limits

- Synthetic dialogues by one author, one answer draw per cell. Temperature 0 summaries are not guaranteed to be deterministic.
- The lexicons are fixed and incomplete.
- Timings include instrumentation and are not SLOs.
