# ADR 186 — Native-only finite semantic review prototype

**Purpose:** Separate source/line consistency from supported semantic claims and finite counterexamples after L1's mixed exact-localization results.

**Date:** 2026-11-11. **Status:** Accepted for bounded research under the owner's continuation request. No production multi-call workflow, model/skill/default adoption or permission change.

## Decision

Create a benchmark-only native prototype, reusing the approved CORE/Fast512, real owner-scoped source snapshots and unchanged optional repo-review instruction bytes. Define twelve new opaque-ID registered-template cases before inference: five defects, five finite-probe conformance controls and two unresolved caller contracts. Sources are inert text. Trusted reference functions calculate expected/observed results only for registered operations on four fixed inputs; never eval/exec/import a snippet or model-generated counterexample. Exact snippet registration and frozen hashes prevent substituting arbitrary source as a trusted operation.

The response distinguishes defect, no_defect and uncertain. A defect requires an admitted source line/quote, global claim category, one probe ID and typed expected/observed values. The native schema admits every target source line and all global claim/probe domains, not only oracle findings. Predeclare multiple supporting source locations where meaningful. Grade the claim category, location and actual divergent finite outputs independently of model prose; title text remains explicitly ungraded. No_defect means conformance within the finite declared probes, not a proof for all inputs; unresolved caller contracts require uncertain.

For each case, draw one candidate without skill and one with unchanged skill. Each candidate receives exactly one planned same-model self-check with the same sources/probes and its original raw text as untrusted data, no gold/score feedback. The candidate is shared between single-stage and checked outcomes. Retain both, never replace first scores. Self-check is another model response, not an independent oracle or automatic retry-until-pass. Alternate the skill group first by case; each check necessarily follows its candidate.

Budget:48 native calls,120seconds/call,1200seconds/campaign,512 output tokens/call. Checked workflow has up to1024 aggregate output tokens across two calls, reported with both call costs. This budget applies only to the research runner; product runs remain at their existing single-completion contract. No model-selected tools, source execution, writes, network destinations or approval authority. Benchmark source snapshots and exact outbound native payloads are retained owner-private; production metadata history remains unchanged.

## Verification and disposition

Unit-test trusted probe outcomes, admissible locations, wrong claims/types/probes, unknown-versus-safe distinction, source tampering, actual source-read integration, shared candidate hashes, no oracle leakage, first raw retention and no transport retries. Freeze sources, gold/tables, exact evidence, code/config/skill hashes before generation; stop on software/transport/drift with partial evidence. One unrelated schema development control is excluded from quality scores.

Report classification, counterexample correctness, self-check gains/regressions, false positives, unresolved-contract overclaims, resource observations and actual two-call costs. Registered finite templates are authored/implemented by the same agent: this is not independent human qualification, arbitrary repository verification, patch correctness or larger-model parity. Rich output/schema changes are not a causal comparison to L1's different cohorts. No automatic adoption regardless of saturation.

Rollback is to stop the optional benchmark and keep all receipts; product code, skill/model/config/defaults, Docker/Vault/database/Qdrant and historical scores remain unchanged. If CORE is absent, verify/start only its existing approved weights/runtime for this owned trial, then stop owned trial processes to restore the initial state.

## Observed outcome

[Result](../HAR008_Q3_SEMANTIC_RESULT.md):48first calls complete, exact sources/tables and24shared-candidate links verified. Overall single6/12→checked5/12 baseline,5/12→6/12 skill, but complete known-defect proofs **0/5 in every group**. Safe controls dominate successes; titles/categories sometimes recognize a problem while expected/observed values are inverted, mistyped or use the wrong exception. No stable self-check benefit, no independent-proof/adoption claim.407 related PASS/4.50s, no native calls in pytest, no production workflow/model/default change. Q4 assesses deterministic observation assistance with fresh cases and withheld gold before another activation attempt.
