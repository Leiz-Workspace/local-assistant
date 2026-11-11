# CODE-EVAL-004 — First bounded reasoning repairs

**Purpose:** Retain all first coding outcomes separately from software/protocol tests and later remediation.

**Status: measurement complete, quality FAIL — 9/12; required12/12.** Existing CORE, explicit coding_reasoning_v1,512reasoning/1024total;12first generations/no feedback/no neural retry. Twelve protocol tests PASS135.33s only certify executed measurement, not perfect repairs. [Exact first results](../evidence/ce004-first-result.json), [frozen protocol](D46_D60_REMEDIATION_PROTOCOL.md).

| Fresh case | First outcome | Visible / held-out exits |
|---|---|---|
| ce004-final-segment | FUNCTIONAL_FAIL | 1 / 1 |
| ce004-first-nonblank | FUNCTIONAL_PASS | 0 / 0 |
| ce004-folded-same | FUNCTIONAL_PASS | 0 / 0 |
| ce004-inclusive-total | FUNCTIONAL_PASS | 0 / 0 |
| ce004-ordered-distinct | FUNCTIONAL_PASS | 0 / 0 |
| ce004-overlay-config | FUNCTIONAL_PASS | 0 / 0 |
| ce004-recent-values | FUNCTIONAL_FAIL | 1 / 0 |
| ce004-required-groups | FUNCTIONAL_PASS | 0 / 0 |
| ce004-safe-position | FUNCTIONAL_PASS | 0 / 0 |
| ce004-shield-token | FUNCTIONAL_FAIL | 0 / 1 |
| ce004-viet-toggle | FUNCTIONAL_PASS | 0 / 0 |
| ce004-wait-seconds | FUNCTIONAL_PASS | 0 / 0 |

Retained errors: masking returns a hardcoded visible-example length on some boundaries; last-separator utility still uses first split; zero-length tail remains the entire list. Original imports/signatures/audit calls and structured reply shape pass fixture review; correct shape is not correct semantics. The native reasoning prefixes mostly enumerate administrative constraints before their512-token cap. That observation motivates a separately evaluated larger bounded budget and generic reasoning-focus instruction; it does not prove causality or authorize rescoring these cases.

Original D46first7/10, CE0027/12perarm and CE003first/eventual4/6 remain unchanged. These are new authored instances of known failure families, not a broad independent benchmark or statistical comparison. Broader promotion remains NOT QUALIFIED; no model/default/API/provider/release change. The first742-file full is a separate source/software checkpoint; its terminal status must be read from its own receipt.
