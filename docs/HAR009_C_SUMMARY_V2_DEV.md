# HAR-009-C summary v2 — development ledger

**Purpose:** One row per development run of the v2 summary contract under the [protocol v2](HAR009_C_SUMMARY_PROTOCOL_V2.md), failures included. Dev numbers tune the contract and are never evidence of gain. Private records: `data/evaluations/context-summary-c2-dev-20261112/`.

## Runs

| Run | Date | Knobs | Generations | Result |
|---|---|---|---:|---|
| S−1 | 2026-11-12 | (5, 1), (4, 1), (5, 0), (4, 0); v1 corpus, 14 cases | 0 | `MAX_SLOTS` 4; R 1,394 at (4, 1); `RESERVE_TOKENS` 1,024 → 1,408 |

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
- **Change:** `history_summary.py` sets `MAX_SLOTS = 4` and `RESERVE_TOKENS = 1408` ([ADR-192 A1.12](ADR/192-proposed-opt-in-llm-summary-of-evicted-history.md#a112-s1-outcome-2026-11-12-tokenizer-only-0-generations)). The runner's `maximal_output()` no longer fails with `MAX_CLAIMS` 0.
