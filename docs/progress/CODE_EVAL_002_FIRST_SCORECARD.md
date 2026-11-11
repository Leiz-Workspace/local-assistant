# CODE-EVAL-002 — First fresh paired coding scorecard

**Purpose:** Report actual first functional outcomes, strict rejections and lack of observed prompt-hint benefit without changing original scores or approved models.

Date: 2026-10-24, Asia/Ho_Chi_Minh. **Status: MEASUREMENT COMPLETE / NOT QUALIFIED FOR BROADER PROMOTION.** [Frozen protocol](CODE_EVAL_002_FRESH_PROTOCOL.md), [pre-inference freeze](../evidence/ce002-pre-inference-freeze.json), [complete first results](../evidence/ce002-first-paired-result.json), [joined audit](../evidence/ce002-post-campaign-readonly-audit.json).

## Actual results

All 24 first measurements completed in 111.69 seconds at the protocol-test level, with one existing CORE attempt per case per arm, no retries or failed-score replacement. Both arms repair **7/12** cases. Baseline: seven functional passes, four functional failures and one source-review rejection. Concise hint: seven passes, three functional failures and two review rejections. The same seven cases pass in both conditions. The hint requested exactly one plan entry; actual concise replies all have two to five entries. No format/functional improvement or production adoption is established.

| Case | Baseline | Concise issue hint |
|---|---|---|
| suffix-mask | FAIL: masked prefix omitted, invalid boundary logic | FAIL: same functional family |
| prefix-mask | PASS | PASS |
| bounded-delay | PASS | PASS |
| remaining-attempts | PASS | PASS |
| parse-switch | PASS | PASS |
| parse-gate | PASS | PASS |
| take-tail | FAIL: zero count returns complete input; visible exit1, hidden exit0 | FAIL: same boundary |
| split-tail | FAIL: first separator retained and incompatible absent-result type | FAIL: same functional family |
| stable-unique | PASS | PASS |
| bounded-index | PASS | PASS |
| bytes-ceiling | REJECTED: new math import changes fixed module shape | REJECTED: same contract boundary |
| merge-defaults | FAIL: reversed precedence preserved | REJECTED: unreviewed recursive call |

All rejection/failure sources and first application-port replies remain untouched. A function that might work outside the declared import/review scope does not receive a fixture grant. Six-step plans remain rejected by the original parser; none were observed in this fresh paired sample, and no schema was relaxed. Two native check modules were selected before inference; neither was generated, changed or sent as hidden source to CORE. Model candidates never executed on the host.

21 admitted candidates receive 63 distinct exact typed fixture approvals and 42 actual native check capsules. Three rejected candidates receive no actions. Every measurement preserves tests and the host canary, joins actual native work and reports functional outcomes separately from generic native quality_evaluated=False. Original D46 7/10 remains unchanged; these different cases cannot be pooled into a new first-pass score or model superiority claim.

## Verification and limits

- 29 corpus/paired isolation controls and 12 actual buggy/reference oracle tests pass; 24 visible and 60 hidden examples, all frozen before inference. Each reference passes both suites; each buggy source fails at least one.
- 24 actual campaign protocol tests PASS/0FAIL/0SKIP, distinct from the 7/12 repair scores. Complete first application-port requests/replies retained, including source-review failures.
- 116 affected regression tests PASS/0FAIL/0SKIP in 26.74 seconds, including the 41 new public tests. Two private capture controls and 19 private auditor-policy controls pass separately; counts are not summed into a full run.
- All 723 current files remain byte-identical to the campaign freeze; every previous 719-file hash matches. The earlier 5596-test full result still covers its original snapshot, not a full run of these additions. Shared application prompts/parsers/security/configs and dependencies are unchanged; no architecture change needs an ADR here.
- Joined read-only audit confirms original services/CORE identity/ordinary text recovery, schema/security/data/zero quota/collections/restore targets, 917 protected files, 176 inputs and unlistened labels. The previously diagnosed quota timestamp delta remains explicit, not restored.

Same-agent authored utility cases are targeted diagnostics, with deliberate overlap in failure families and small sample size. No independent human coding-quality judgment, adversarial generality, framework/multifile capability, statistical superiority, cold latency/TTFT/TPS, peak RAM/VRAM or unattended production readiness is inferred. The explicit issue hint stays experimental and is not adopted. No model, provider, default, production feature flag, Vault/database or collection change occurred.

## Assessed follow-up

CODE-EVAL-003 is a P1 candidate before broader promotion: design a bounded visible-test feedback protocol on fresh data, with complete first/second outcomes separated and a fixed attempt/action budget. Dependencies are exact current source/test hashes, trusted action reviews, explicit handling of known applied versus uncertain edits and preservation of hidden oracles. Effort: one protocol/guard/control milestone followed by a separately frozen evaluation. Risks: leaking hidden answers, treating regeneration as first-pass success, replaying applied actions, weakening source reviews and escalating model authority. No new campaign, feedback loop, shared prompt change or model replacement is executed or scheduled by this scorecard. Current accepted one-attempt behavior remains intact.
