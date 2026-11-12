# HAR-009-C summary v2 — development ledger

**Purpose:** One row per development run of the v2 summary contract under the [protocol v2](HAR009_C_SUMMARY_PROTOCOL_V2.md), failures included. Dev numbers tune the contract and are never evidence of gain. Private records: `data/evaluations/context-summary-c2-dev-20261112/`.

## Runs

| Run | Date | Knobs | Generations | Result |
|---|---|---|---:|---|
| S−1 | 2026-11-12 | (5, 1), (4, 1), (5, 0), (4, 0); v1 corpus, 14 cases | 0 | `MAX_SLOTS` 4; R 1,394 at (4, 1); `RESERVE_TOKENS` 1,024 → 1,408 |
| S−1 check | 2026-11-12 | committed defaults (4, 1, `last`); v1 corpus | 0 | DESIGN_VALID, 0 violations; output 1,393 ≤ 1,472; R 1,394 ≤ 1,408 |
| D87 (precondition) | 2026-11-12 | branch `058d09d`, tree `2995f65` | 0 | PASS: 6,738 passed, 0 failed, 0 errors, 0 skipped ([receipt](evidence/d87-20261112-branch-058d09d-acceptance.json)) |
| Dev design | 2026-11-12 | (4, 1), (4, 0) × `last`, `withheld`; dev set, 20 cases | 0 | DESIGN_VALID under every knob, 0 violations; oracle gold 18/18 |
| S0 | 2026-11-12 | defaults (4, 1, `last`) | 2 | COMPLETE: both example packets verified, declared key order kept, finish `stop` |
| R0 | 2026-11-12 | Amendment text as written: (4, 1, `last`), prompt `a5cace13…` | 20 | **gold 18/18** (EN 9/9, VI 9/9; dev-plus 6/6); hard gates passed; early stop met |
| A0 (refused) | 2026-11-12 | prompt-minimal v2a on the v1 contract | 0 | DESIGN_INVALID from a runner defect (R bounded over the fallback pair); fixed in `0df547f` |
| A0 | 2026-11-12 | prompt-minimal v2a (`e4106851…`) on the v1 contract; never frozen | 20 | gold 0/18; 64 `speaker_mismatch` drops, 47 assistant claims admitted |
| k=3 | 2026-11-12 | R0 configuration, 2 more draws | 40 | 18/18 and 18/18; gates passed; raw output identical to R0 in 20/20 cases |
| Freeze | 2026-11-12 | R0 configuration | 0 | `FROZEN_V2` filled; prompt and schema template hashes pinned by test |

## S−1 (tokenizer only)

- **What ran:** `benchmarks.context_summary_v2 --cases v1 --mode design` with `--max-slots`/`--max-claims` for each knob pair. CORE was started with the unchanged `scripts/start-core.py` on an idle host, used only through `/tokenize`, and stopped with SIGINT. No generation, no answer.
- **Maximal output** (native tokens; limit `MAX_TOKENS − 64` = 1,472):

  | Slots | With the claim | Without it |
  |---:|---:|---:|
  | 1 | 610 | 421 |
  | 2 | 880 | 691 |
  | 3 | 1,136 | 963 |
  | 4 | 1,393 | 1,220 |
  | 5 | 1,650 | 1,477 |

  By the ADR-192 A1.4 rule (largest value ≤ 5 within the limit), `MAX_SLOTS` is 4. No slot can be traded for the claim, so the allowed knob becomes (4, 1) or (4, 0).
- **R** (capsule of `MAX_SLOTS + MAX_CLAIMS` maximal rows over pairs 1–8): 1,664 at (5, 1), 1,394 at (4, 1), 1,124 at (4, 0), all above the expected 1,024. Decision 3 freezes R by the design check, so `RESERVE_TOKENS` is 1,408 (R rounded up to a multiple of 64). The v1 control copy keeps 1,024.
- **Per-case oracle checks:** no per-case violation under any knob; the only violations were `output_bound` and `reserve_bound`, which do not depend on the corpus.
- **Check with the committed defaults:** CORE was started again on 2026-11-12 for the held-out calibration. `--cases v1 --mode design`, run with no knob options, gives DESIGN_VALID with 0 violations: maximal output 1,393 ≤ 1,472 and R 1,394 ≤ 1,408. Records: `s-1/defaults-v1/`.
- **Change:** `history_summary.py` sets `MAX_SLOTS = 4` and `RESERVE_TOKENS = 1408` ([ADR-192 A1.12](ADR/192-proposed-opt-in-llm-summary-of-evicted-history.md#a112-s1-outcome-2026-11-12-tokenizer-only-0-generations)). The runner's `maximal_output()` no longer fails with `MAX_CLAIMS` 0.

## Dev-plus (written 2026-11-12, after the held-out hash)

`benchmarks/context_summary_dev_plus.py` holds 6 scored cases. Its `dev_plus()` digest is `2daa469bde1bed5c6973cfe483bc2622b43005304a64103342e853805c7b52f3` and its file SHA-256 is `9f7b689f35973b00c6baeed8f5146d638a7d126983136dfa1731c41c1c466eeb`. Together with the 14 v1 cases they form the 20-case dev set (18 scored).

| Case | Language | Protocol shape | Targets | Gold value |
|---|---|---|---|---|
| `dp-multi-quarrymoor` | EN | multi-fact; the asked identifier is third of three | 4 | `KX-82-TD` |
| `dp-multi-trangquyt` | VI | multi-fact; the asked number is third of three | 3 | `317` |
| `dp-late-tamarack` | EN | late target at pair 7 behind 4 value-bearing distractors, one a near-miss value | 7 | `4.85` |
| `dp-late-oqua` | VI | late target at pair 7 behind 4 value-bearing distractors, one an expired near-miss code | 7 | `OQR-8142-V` |
| `dp-fix-wexcombe` | EN | correction without the entity name (`replaces` = 3) | 3, 6 | `33` |
| `dp-neg-ngoive` | VI | negation inside a 528-character message; the answer must state the prohibited window | 4 | `20:15` |

- **Layout.** Each case follows the v1 layout:
  - pairs 1–7 hold the targets, value-bearing distractors and v1 short fillers;
  - pairs 8–16 are v1 `log_block` worker logs;
  - the question carries the v1 suffix.
- **Every case has:**
  - at least 2 value-bearing distractor user messages;
  - an authored non-target assistant reply with a digit-bearing value, sent under (4, 1);
  - exactly 4 listed rows under every knob, with every target listed and none clipped.
- **Disjointness.** `benchmarks/tests/test_context_summary_dev_plus.py` checks that dev-plus is disjoint from v1, the prompt and its example entities, and the hashed held-out set. For the held-out set it compares digests only. A failure reports a finite code (`HELDOUT_CHANGED`, `HELDOUT_FIXTURE_FAILED`).
- **First-draft collisions.** The first draft collided with the held-out set in 3 cases (value tokens) and then in 2 messages and one value (held-out test 3). Each was fixed by replacing the case's values or rewording the message, from counts and locations only. See the protocol's [exposure log](HAR009_C_SUMMARY_PROTOCOL_V2.md#held-out-manifest-recorded-2026-11-12-before-s0).
- **Review.** Three independent lenses reviewed dev-plus: protocol and tests, answer scoring, and listing/verifier/design. Two skeptics then tried to refute each finding (39 agents). 9 findings were confirmed, covering 5 distinct issues; 9 were refuted. Fixes:
  - `dp-neg-ngoive` used gold value `nv-app-31`, which also sits in a non-negated clause. A note that dropped the prohibition, or its window, therefore counted as gold. The value is now `20:15`, which occurs only inside the negated clause. The question now asks for the prohibited window, so required gains a second group (`20:15`, `20h15`) and evidence adds `20:15`. Bare "Không" and no-information answers no longer pass.
  - The held-out fixture could print a truncated repr of the corpus on a hash mismatch. It now returns digests or a code, and never raises with held-out data in a frame.
  - Test hardening:
    - values must carry a digit (the filler reply "sans-serif" no longer counts);
    - authored replies must be sent;
    - the multi-fact gold must not be the first value;
    - the correction must not name the entity in any position or case;
    - the negation quote must sit inside the message;
    - each gold value must occur once, inside its quote;
    - no required, forbidden or evidence string may occur in the retained pairs 9–16;
    - a guard keeps the dev-set test from seeing a loaded held-out module.
  - A mutation check confirms that each new assertion catches its defect.
- **Expected native design.** A reviewer used a native-equivalent tokenizer port, which matched `llama-tokenize` on 164 of 164 texts and reproduces the S−1 numbers. It found 0 violations for v1 plus dev-plus under all 4 knobs:
  - the budget arm keeps pairs 9–16 at 23,627–23,686 tokens, at least 506 under the 24,192 soft limit, so no pair is lost to the reserve;
  - pairs 1–8 are always evicted and covered;
  - `full` needs at most 27,025 tokens.

  The native design check runs before S0.
- **Proceed condition.** The runner does not split dev-plus gold from the rest, so the ledger computes the ≥ 4/6 dev-plus condition from the per-case rows.

## Dev rounds (2026-11-12)

- **Setup.** CORE was started with the unchanged `scripts/start-core.py` on an idle host. The run used the weights SHA-256 `073a9275…` and runtime pin `5c8854fd…`, and CORE was stopped with SIGINT afterwards. All runs are summary-only through `inference.prepare`, with temperature 0, a 120 s deadline per cell, no cache, no answers and no retries. Total: 82 generations of the 142 cap. Public counts are in [`evidence/context-summary-c2-dev-20261112.json`](evidence/context-summary-c2-dev-20261112.json).
- **R0 (Amendment text as written).**
  - Gold 18/18: the 12 v1 scored cases and the 6 dev-plus cases.
  - Funnel: listed 18, returned 18, admitted 18, gold 18.
  - Gates: 0 self-check defects, 0 `invalid_output`/`unfinished`, 0 example copies, 0 reverify mismatches, 0 approval overlap. Both authority gates gave `none_verified`.
  - Drops: 1 `quote_context_dropped` (neg-camau; another note at that pair was admitted) and 1 `authority_context` (auth-hoabinh).
  - Other counts: 6 assistant claims admitted (the dev-plus replies) and 2 log items.
  - Empty-slot rate: 1 of 23 target slots and 11 of 31 distractor slots.
  - Forbidden tokens were admitted in 13 of 20 cells. Most come from faithful notes that keep a near-miss or sibling value stated in the same message (for example "port 9446 is the retired exporter") or in a listed distractor slot. The metric is descriptive and only breaks ties.
- **Stopping and rounds not run.** R0 met the early stop (gold ≥ 16/18 with the gates passed), so R1–R3 were not run and no knob changed.
- **A0 ablation.**
  - The prompt-minimal v2a is the v1 prompt plus the v2 content rules in v1 schema terms (user statements first, whole-clause quotes, text only from quote words, claim restraint), with no examples. It ran on the v1 control copy and gave gold 0/18.
  - The model still quoted assistant text under user kinds: 64 `speaker_mismatch` drops, and 47 assistant claims were admitted. A prompt change alone does not fix the v1 failure. This supports the contract change of ADR-192 Amendment 1.
  - The first A0 attempt was refused before any generation because of a runner defect, fixed in `0df547f` with a regression test.
- **k=3.** Two more draws of the R0 configuration gave 18/18 each, with the gates passing in all three draws. Because summaries run at temperature 0, the raw output matched R0 byte for byte in 20/20 cases. The repeats show determinism, not variance.
- **Proceed to held-out:**
  - frozen round 18/18 (≥ 14/18 required);
  - dev-plus 6/6 (≥ 4/6);
  - k=3 median 18/18 (≥ 14/18);
  - gates hold in all draws.
- **Freeze.**
  - `history_summary.py` keeps the R0 values: `MAX_SLOTS` 4, `MAX_CLAIMS` 1, `CLIPPED_USER` `last`, prompt unchanged.
  - Tests pin `PROMPT_SHA256` `a5cace131e9f…` and `SCHEMA_TEMPLATE_SHA256` `2045be19c232…`.
  - `FROZEN_V2` in the runner records these with the `history_summary.py` SHA-256 `ab21586d3b3b…`, and the frozen guard refuses any other contract.
