# HAR-009-C summary v2 — held-out result

**Purpose:** Record the held-out outcome of the v2 evicted-history summary contract ([ADR-192 Amendment 1](ADR/192-proposed-opt-in-llm-summary-of-evicted-history.md#amendment-1-v2-contract)) under the frozen [protocol v2](HAR009_C_SUMMARY_PROTOCOL_V2.md). [Public receipt](evidence/context-summary-c2-20261112.json). Date: 2026-11-12.

**Status:** measurement COMPLETE. 304 of 304 native calls (152 answers and 152 summaries), no retries, 1,478.6 s from the first native call to the last. **Pre-registered label: GAIN.** An independent check confirmed it. On the 24 scored held-out cases, `budget_summary_v2` answered 23/24 strictly, against 0/24 for `budget` and 2/24 for the v1 control. The flag stays experimental and opt-in; no default changes, and adoption is the owner's decision.

## Run

- **Model and runtime.** Approved CORE `qwen3.5-9b-core`. The weights SHA-256 `073a9275…` and the runtime pin `5c8854fd…` were checked before start. CORE was started with the unchanged `scripts/start-core.py` on an idle host and stopped with SIGINT afterwards.
- **Contract.** The frozen v2 contract (`FROZEN_V2`, commit `dc1a447`): `MAX_SLOTS` 4, `MAX_CLAIMS` 1, `CLIPPED_USER` `last`, prompt `a5cace13…`, schema template `2045be19…`, `RESERVE_TOKENS` 1,408. It was frozen after dev round R0 reached 18/18 ([dev ledger](HAR009_C_SUMMARY_V2_DEV.md)). The held-out corpus (`HELDOUT_SHA256` `100f2848…`) was hashed before the first v2 generation.
- **Corpus.** 38 held-out cases written by blind subagents from the protocol specification: 24 scored, 6 gates and 8 probes, 19 EN and 19 VI. The orchestrating session never opened the corpus. Before the run it saw only ids, counts and digests, plus the incidents recorded in the protocol's exposure log.
- **Answers:** preset `fast`, `max_tokens` 512, temperature 0.7, streaming, one draw, no retries.
- **Summaries:** ADR-192 settings (thinking off, temperature 0, `max_tokens` 1,536, JSON schema), a 120 s deadline per cell, no app cache. Two extra v2 summary draws per case give k = 3.
- **Freeze.** The design check was repeated at freeze and was valid (maximal output 1,393 ≤ 1,472; R 1,394 ≤ 1,408). `frozen-inputs.json` was written before the first completion. D87 passed at freeze ([receipt](evidence/d87-20261112-branch-ac9b9f2-acceptance.json)).
- **Owner-private records:** `data/evaluations/context-summary-c2-20261112/`, which Git ignores.

## Results (strict, 24 scored cases per arm)

| Arm | Strict | Stale | Facts present | 95% interval |
|---|---:|---:|---:|---|
| `full` (reference) | **23** | 1 | 24 (window) | 0.789–0.999 |
| `budget` | 0 | 0 | 0 | 0–0.142 |
| `budget_summary_v1` (control) | 2 | 0 | 3 (capsule) | 0.010–0.270 |
| `budget_summary_v2` (candidate) | **23** | 0 | 23 (capsule) | 0.789–0.999 |

- **Reference check passes:** `full` 23/24 strict, presence 24/24. Its one miss, `h-correction-vi-2`, is a stale answer even though the evidence was in the window; v2 answered that case correctly.
- **Primary measure, v2 against `budget`:** 23 gains, 0 regressions, net +23 (EN +11, VI +12), 0 new stale answers.
- **v2 against the v1 control:** 21 gains, 0 regressions, one-sided sign test p = 4.8·10⁻⁷.
- **v1 control against `budget`:** 2 gains, 0 regressions (p = 0.25).
- **Label GAIN.** Every pre-registered condition holds:
  - net ≥ 8, against an observed +23;
  - ≥ 3 per language, against +11 and +12;
  - 0 new stale answers;
  - p ≤ 0.01, against 4.8·10⁻⁷;
  - reference passed;
  - safety clean.
- **v2 among the cases `full` answers:** 22/23 (0.781–0.999).

### By kind, language and shape (`full` / `budget` / v1 / v2)

| Kind | Strict |
|---|---|
| number | 4/4 · 0/4 · 0/4 · 3/4 |
| identifier | 4/4 · 0/4 · 1/4 · 4/4 |
| swap | 4/4 · 0/4 · 0/4 · 4/4 |
| correction | 3/4 · 0/4 · 0/4 · 4/4 |
| negation | 4/4 · 0/4 · 1/4 · 4/4 |
| condition | 4/4 · 0/4 · 0/4 · 4/4 |
| EN | 12/12 · 0/12 · 1/12 · 11/12 |
| VI | 11/12 · 0/12 · 1/12 · 12/12 |
| basic shape | 12/12 · 0/12 · 2/12 · 12/12 |
| new shape | 11/12 · 0/12 · 0/12 · 11/12 |

### Funnel (v2, scored)

- **Steps:** 24 listed → 24 note returned → 23 admitted → 23 gold admitted → 23 strict. Strict given gold admitted: 23/23.
- **Corrections:** in all 4 correction cases the older target note was marked superseded, and 0 stale notes were left unflagged.
- **The one v2 miss:** `h-number-en-2` (number, EN, new shape). The model returned a note at the target slot, but the verifier dropped it as `content_free`, so the capsule lacked the evidence and the answer omitted the value. The result was the same in all 3 draws.
- **v1 control:** 0/24 scored target notes admitted. All 149 admitted v1 items across the 38 cells (107 in the 24 scored cells) were assistant claims, the same failure seen in v1. Summary statuses: v2 applied 108 and none_verified 6 over 114 summaries (the two `allow_wording` probes in each draw); v1 applied 33 and none_verified 5 over 38. Every summary finished with `stop`.

### Safety (all pass)

1. 0 self-check defects on 384 admitted v2 rows across the matrix and both extra draws.
2. Gates:
   - G1–G4: 0 summary-arm adoptions, so 0 violations;
   - G5–G6: 0 adoptions, so 0 violations and 0 recovered instructions;
   - `full` adopted in 3 of 6 gates; `budget`, v1 and v2 adopted in none;
   - the v2 capsule held no authority wording.
3. 0 admitted items cite an `allow_wording` target pair. Both probes were dropped by `authority_context` in all 3 draws.
4. 228 of 228 rows are COMPLETE, with no unknown status.
5. The runner log holds only INFO lines with numbers, mode and status names, and file names. Neither the runner log nor the CORE log contains any dialogue, prompt, answer or capsule text.

### Probes and other measures

- **Probes, v2 strict:**
  - `leading_condition` 2/2;
  - `allow_wording` 0/2 (dropped by design);
  - `cap_pressure` 0/2 (target over the cap by design);
  - value-less correction 0/2. The newer target is unlisted, so the older value was admitted unmarked and both answers were stale.

  These probes are outside the primary measure and show the known limits.
- **Forbidden values in admitted v2 notes:** 15 cells (13 scored, 2 probes). Most come from notes that faithfully keep a sibling or older value stated in the target message, or an older correction note marked superseded. None of the 13 scored cells gave a stale answer.
- **Drop reasons (v2):** 7 of 135 returned items were dropped:
  - `authority_context` 4, the gates and `allow_wording` as designed;
  - `content_free` 1;
  - `claim_without_value` 1;
  - `quote_not_in_source` 1.

  `speaker_mismatch`, which dominated v1, never fired.
- **k=3:** the three v2 draws are byte-identical in 38/38 cases, because summaries run at temperature 0. This shows determinism, not variance.
- **Dev-to-held-out gold gap:** 18/18 against 23/24, 4.2 points, under the 25-point overfitting flag.

### Cost

- **Summary inputs:** median 1,412 tokens for v2 and 979 for v1.
- **Summary outputs:** median 375 tokens for v2 and 520 for v1.
- **Capsule:** median 256 tokens for v2 and 330 for v1.
- **Pairs lost to the reserve:** 0.
- **Answer input:** median 21,196 tokens for v2, against 20,861 for `budget` and 28,798 for `full`.
- **Resources:** CORE RSS peak 9.8 GiB, GPU peak 8,018 MiB.
- **Timing is not comparable across arms.** CORE's prompt cache serves the shared prefix of the two summary arms to whichever runs second. The v2 median first text is 0.33 s after v1 but 4.12 s when v2 runs first. v2 summaries also reused about 1,287 cached prompt tokens. Neither first-text time nor summary seconds is a like-for-like latency comparison.

## Independent check

Separate agents reproduced every row from the private records and reported counts only, and a critic cross-checked them:

- **Results:**
  - 152 answers rescored, with 0 mismatches;
  - presence recomputed from the saved requests, with 0 mismatches;
  - `source_sha256` recomputed from the frozen corpus, with 0 mismatches on 152 summaries;
  - `reverify()` on 114 v2 exchanges and the v1 parser on 38, with 0 mismatches;
  - `compare()` and `heldout_outcome()` rebuilt, identical to the runner's;
  - the frozen, source and corpus hashes re-confirmed.
- **Critic:** confirmed GAIN with clean safety. It found no leak of held-out content in the reports. The only differences it found were in descriptive cost figures (median conventions) and are corrected above.

## Limits

- **Synthetic, controlled retention.** Each case has one evicted target fact and a fixed 16-pair layout. This is not general conversation quality, and other models, contexts or real dialogues may differ.
- **Small and narrow.** 24 scored cases, one held-out draw of answers and deterministic summaries.
- **Same author family.** The authoring agents were blind to v2 output but come from the same model family as the prompt author.
- **Known gaps, by design:**
  - targets past the 4-slot cap are lost;
  - value-less corrections keep the older value;
  - a whole note is dropped when its quote holds no value (the one scored miss).
- **Clipped-user path not exercised.** No held-out window listed a clipped user row: long blocks are withheld as `user_no_signal`. So `CLIPPED_USER` `last` and the clipped-quote check do not affect this measure, as the protocol's Limits pre-registered.
- **Runner-level only.** No route-level cell and no blinded owner review were run.
- **Exposure log.** Before the run, the orchestrating session saw held-out ids, target pair numbers of 3 cases and the locations of dev-plus collisions. From those locations it could narrow one colliding word down to two common Vietnamese words. All of this is recorded in the [protocol's exposure log](HAR009_C_SUMMARY_PROTOCOL_V2.md#held-out-manifest-recorded-2026-11-12-before-s0). No held-out message text, value or quote was displayed.

## Decision

- The pre-registered label is **GAIN** for the v2 contract on this held-out corpus.
- `/status` now reads `opt-in-experimental-v2-measured-gain`.
- `evicted_summary` stays opt-in and experimental. Making it a default, or widening its scope, needs the owner's approval and, per ADR-192, its own review.
- No model, default, flag-scope or context-size change.
