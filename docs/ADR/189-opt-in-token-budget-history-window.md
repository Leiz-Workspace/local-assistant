# ADR-189: Opt-in token-budget history window with inspectable importance markers

**Purpose:** Record HAR-009-B2: a history policy that selects recent whole pairs by a native token budget instead of a fixed pair count, and gives user-marked rules priority by an inspectable rule. It changes no default, model, context size or approval decision.

**Date:** 2026-11-11. **Status:** Implemented as an experimental opt-in mode and measured once ([protocol](../HAR009_B2_TOKEN_BUDGET_PROTOCOL.md), [result](../HAR009_B2_TOKEN_BUDGET_RESULT.md)). Default adoption is not decided. Extends [ADR-187](187-opt-in-pinned-history-and-extractive-compaction.md); supersedes nothing.

## Context

- **B1 found that window size, not token cost, drives retention on short dialogues.** The legacy composer and `sliding-window` keep at most 11 pairs (or the configured count), even when 40 short pairs would fit in a fraction of the context. Once old facts and rules fell outside the window, they were lost. Pins keep only what the user pinned by number.
- **The backlog asks for more** ([HARNESS_PRODUCT_BACKLOG](../progress/HARNESS_PRODUCT_BACKLOG.md), HAR-009-B2):
  - recent whole pairs chosen within a token budget;
  - an importance rule that can be inspected;
  - token pressure kept separate from message and cache limits;
  - a receipt for every kept or dropped pair;
  - tests for long turns, short turns and mandatory overflow;
  - no automatic context-size increase.

## Decision

Add `mode="token-budget"` to the existing `HistoryPolicy`. Absence of `history_policy` still runs the legacy composer, and the other two modes are unchanged.

1. **Budget.** The policy's soft target is `int(hard_input_limit × trigger_ratio)`. The hard limit is unchanged: context size minus the output ceiling (or the 512-token minimum answer for dynamic Unlimited) minus the 256-token reserve. The default ratio is 0.8, and the allowed range stays 0.5–0.95. The native template and tokenizer count every candidate. `window_turns` is ignored, and the receipt shows it as `null`; the CLI refuses `--history-window` with this mode. `--history-budget-ratio` is an alias of `--compact-trigger`.
2. **If the whole history fits the soft target, keep all of it.** One count settles this common case, so 40 short pairs stay where the legacy composer keeps 11.
3. **Otherwise, select in this order:**
   1. **Mandatory content:** system messages, explicit pins and the current user message. If this exceeds the hard limit, the request fails with `context_overflow`; nothing is clipped. If it exceeds only the soft target, no optional pair is added, no further probe runs, and `soft_target_met` is false.
   2. **Anchor:** the newest pair that fits the soft target, scanning at most 8 newest pairs. One oversized newest pair therefore does not erase the older history. If all 8 newest pairs are oversized, no recent pair is kept; marked pairs can still be.
   3. **Recent share:** the longest contiguous run of pairs, from the anchor backwards, that stays within half of the headroom left after the anchor (`recent_share_token_cap`). The immediate conversation therefore always keeps this share, and marked pairs inside it cost nothing extra.
   4. **Importance:** marked pairs outside the kept set, newest first, are kept while the total stays within the soft target. At most 8 marked pairs are probed. A pair counts as marked when its **user** message opens with a listed marker. The match ignores case, leading spaces and Unicode normalisation form (NFC/NFD). Assistant text and markers in the middle of a message grant nothing. The markers are `rule:`, `constraint:`, `important:`, `decision:`, `remember:`, `quy tắc:`, `quy ước:`, `ràng buộc:`, `quan trọng:`, `quyết định:` and `ghi nhớ:`.
   5. **Recent extension:** the run from step 3 is extended backwards as far as the soft target allows.

   Steps 3 and 5 find the run length by binary search.
4. **Strict source priority** rejects any loss with `strict_context_would_trim`.
5. **Cost of counting.** At most about 1 + 1 + 8 + 2 × log2(128) + 8 native counts for the selection, plus the final count. This replaces one count per evicted pair.
6. **Receipt.** The receipt adds:
   - `selection`: one reason per pair (`pinned`, `recent`, `important`, `evicted_token_budget`, `evicted_importance_budget`, `evicted_importance_limit`);
   - `importance_markers` and `importance_turns` (pair number and marker, never text);
   - `recent_window_pairs`: the number of pairs whose reason is `recent`;
   - `mandatory_tokens` and `recent_share_token_cap`. Both are `null` when the whole history fits, because they are not measured then.

   It contains no dialogue text. The harness status lists the new mode in `context_policies`.
7. **Unchanged.** There is no archive, no recall, no LLM summary and no new inference call. Markers only change retention priority; they never grant authority, approval or consent. The request bound (256 messages, pins 1–127) and the archive limits are unchanged and play no part in the token selection.

## Alternatives and consequences

- **Considered and rejected:**
  - *Greedy newest-first selection that skips any pair that does not fit.* This keeps more bytes but leaves gaps inside the recent conversation.
  - *Importance first without a share cap.* Marked long pairs could crowd out the immediate conversation.
  - *Importance before the recent run, capped at half the headroom.* This was the first implementation. The independent review found that marked pairs right behind the anchor, which the recent run keeps anyway, used up the share and the 8 probes, so an older marked rule was dropped as soon as recent pairs were marked too. The order above fixes this; a regression test covers it.
  - *Learned or LLM importance scoring.* It cannot be inspected and needs its own evaluation.
  - *A bigger context.* Excluded by the backlog.
- **Known risk: wrong priority.** A marked old decision survives while a newer unmarked correction can be evicted under pressure, so the model may answer with the stale value. B2 measures this risk on purpose. Users can pin or mark the correction; there is no automatic resolution.
- **Unmarked rules are not protected.** Under pressure they disappear exactly as in the legacy composer.
- **Cost.** Keeping more short history costs more input tokens than an 11-pair window, which is still small in absolute terms (about 1.2k tokens for 40 short pairs in B2).

## Validation

- **Software tests.** `tests/test_context_token_budget.py` has 20 tests:
  - short-turn retention beyond 11 pairs;
  - a contiguous long-turn run within the soft target;
  - NFD, uppercase and leading-space Vietnamese markers;
  - marker position, and markers in assistant text;
  - the recent share, the probe limits, and marked recent pairs never costing an older marked rule;
  - an oversized newest pair;
  - pin overflow and soft-only pressure;
  - strict mode;
  - the composer receipt without text;
  - CLI forwarding and refusal.

  Existing policy, composer, harness and CLI tests are unchanged and pass.
- **Native measurement.** See the B2 [result](../HAR009_B2_TOKEN_BUDGET_RESULT.md). No default or adoption follows from it.

## Rollback

Omit `history_policy` or choose another mode. No data, storage, model, configuration or migration is involved. Removing the mode is a code revert of the selection function, the CLI choice and the status list.
