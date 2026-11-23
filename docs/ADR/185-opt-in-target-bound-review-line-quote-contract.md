# ADR 185 — Opt-in target-bound review line and quote

**Purpose:** Prevent the observed HAR-008-Q2 correct-quote/wrong-line mismatch without rewriting outputs, changing models or asserting that a source-valid finding is a real defect.

**Date:** 2026-11-11. **Status:** Accepted for bounded staged implementation under the owner's continuation request. Generic source answers, text defaults, skills and all prior scores remain unchanged.

## Decision

Add `review-line-quote-v1` as an optional readonly run contract, requiring an explicit clean relative `review_target` that is also an explicit workspace.read path. This field narrows the answer target; it never opens a path, grants access or changes workspace authority. Other supplied reads remain untrusted caller/policy context.

Use the existing exact-hash/trust/envelope validation for context-retained read snapshots, then select only target origins. Reject absent/omitted/blank-only targets, inconsistent source hashes or contradictory content for the same source line. Preserve absolute original one-based numbering for partial read ranges. Repeated identical lines at different positions remain separate admissible pairs. Do not choose an arbitrary duplicate or renumber a read range.

Before generation build a bounded schema union: null/null, or each exact target-origin integer line number paired with its canonical whole-line quote. Include every eligible target line, not an oracle defect. The schema cannot pair a correct quote with another line number. Require the pinned native nested schema wrapper and independently validate the unmodified first completion and selected origin afterwards. Do not fix a number, strip a fence or retry. Keep size/cap failures explicit rather than silently reducing the target domain.

Expose CLI `--output-contract review-line-quote-v1 --review-target PATH`; reject targets in other modes. Omit new fields on default CLI text requests for compatibility with an already running old server. No browser streaming, legacy gateway, generic source schema, skill manifest, model/configuration, history schema or database change. Failed diagnostics remain owner-only/ephemeral, history digest-only.

## Verification and limits

Test real snapshots, target authority/omission, conflicting snapshots, repeated quotes, non-one read ranges, schema size, wrong number/type/file/null, direct inference/native payload, CLI forwarding and owner/history privacy. Run development controls separately before freezing fresh review cases. Counterbalance generic versus line-bound contracts on the same new questions, each with/without unchanged skill and same CORE/Fast512/strict. Retain all first outcomes without retries, including semantic mistakes and partial campaigns. Preserve Q2 21/24 and23/24 unchanged.

Line agreement does not prove that a defect exists or that the selected line is the right finding. Null/null and choosing the wrong admitted line remain possible. Controlled saturation does not establish independent broad skill quality or larger-model parity. Repeated-line reasoning, multi-file entailment, real fixes/resource/release acceptance remain separate gates.

## Rollback

Omit the option or select the existing text/source contract, retaining all receipts. Do not change model, weights/SDK, Docker/Vault/DB/Qdrant or existing data. Start only an isolated updated application for tests; do not restart an active primary desktop. If CORE is absent, use its already approved local weights/configuration for the trial without downloading/replacing anything.


## Retained first trial and ordering variant

The first frozen cohort completed48 calls: generic strict10/12 baseline and8/12 skill, value-first bound8/12 each. All24 bound pairs were mechanically valid, but baseline had one gain/three regressions. Do not qualify or default-enable this variant from mechanical consistency. Exact first source bytes and raw outcomes are retained, including source-valid wrong findings and false positives.

Hypothesis, not a measured causal conclusion: predicting the numeric value before the quote can lock a wrong location and constrain the following quote to it. Add a separately named opt-in `review-quote-line-v1`, preserving the same admitted pairs/null policy and validators but declaring native properties in quote-then-value order. Keep `review-line-quote-v1` value-first and the generic contract intact. JSON objects remain unordered for host validation; do not repair either wire order after generation. Policy semantics remain identical except the contract identifier.

Before new calls, freeze a fresh opaque-ID12-case cohort and six arms (generic/value-first/quote-first × no-skill/skill),72first calls, cyclic six-arm order,900s campaign,120s/task, no retries. Preserve the first trial's lower scores and all native replies; compare variants only within the new cohort. No automatic activation even if the new sample improves; broad semantic/quality/adoption gates remain open.

## Current bounded outcome

[Result](../HAR008_L1_REVIEW_PAIR_RESULT.md): both campaigns completed48/72first calls, all72 bound pairs and observed bound native field orders valid. Second cohort strict generic6/12 baseline/7/12 skill, value-first11/12/9/12, quote-first10/12/7/12. Quote-first versus value-first regressed in both baseline and skill comparisons; the hypothesis did not establish a consistent gain. Keep the first cohort's10/12/8/12 generic and8/12/8/12 value-first results unchanged. Bounded mechanics verified, semantic/adoption qualification NOT_QUALIFIED; both variants remain explicit research options, default text/generic/skills/model unchanged. Final389 related PASS/4.63s, no model calls in pytest, not full regression. HAR-008-Q3 assesses semantic locations/claims/counterexamples before another workflow or adoption attempt.
