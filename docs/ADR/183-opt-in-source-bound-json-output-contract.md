# ADR 183 — Opt-in source-bound JSON output contract

**Purpose:** Address the observed HAR-008 JSON/quote/null contract failures without rewriting first outputs, replacing a model or claiming semantic correctness from valid JSON.

**Date:** 2026-11-10. **Status:** Accepted for staged implementation under the owner's continuation request. Default text behavior and all model/adoption/release gates remain unchanged.

## Decision

Add a finite host-selected `source-value-quote-v1` output contract to readonly product runs. Default is `text`; do not change the legacy gateway, browser streaming mode or skill manifests. Require explicit workspace.read evidence. Build a bounded quote catalog from only the source snapshots actually retained by the context composer, not from filesystem paths, discarded evidence or benchmark oracle fields.

Before inference, canonicalize source lines by removing ASCII indentation/trailing spaces. This canonical representation is the contract's declared quote domain; never trim, repair or extract a favorable model output afterwards. Use the pinned llama.cpp server's schema-constrained `response_format` to require exactly value/quote fields: null/null or a nonnull bounded string/integer plus a quote chosen from the admitted catalog. Bind explicit null/quote instructions into mandatory context before token counting. Source text remains untrusted even when it is a grammar literal.

Validate the native first output independently after generation: exact JSON shape, duplicate keys, types, null pairing and admitted quote membership; require a complete finish, no tool calls and the original preset/token budget. Do not retry, coerce values or normalize the response. Record schema/catalog/raw-completion hashes and quote provenance. A source-valid quote does not prove entailment, correct classification or a successful review.

On contract failure retain the raw native response as owner-scoped in-memory diagnostics on a FAILED run, not as a successful result. Metadata history keeps only its digest and the existing finite failed-state code, never diagnostic text or recovered authority. This avoids widening the history schema/error enumeration. Raw diagnostics are available to the evaluation runner for first-outcome auditing, not to logs or an unauthenticated browser.

## Evaluation and limits

Keep HAR-008 v1's 5/12 and 6/12 untouched. Freeze a new controlled cohort after implementation/development checks, before its first native call. Counterbalance four arms on the same cases: text baseline, text skill, constrained baseline, constrained skill. Keep CORE/Fast/output cap/context policy and skills fixed. Report format/value/quote/strict outcomes, raw first outputs, contract failures and paired regressions independently. Compare modes within the new cohort; do not claim cross-cohort causal improvement or large-model parity.

Bound catalog lines/bytes/schema size and reject unknown/omitted/oversized evidence rather than silently creating an incomplete citation domain. The first contract supports full canonical source lines from workspace.read only; arbitrary snippets, multiline spans, caller schemas, executable bundles, streaming constraints and cross-file semantic entailment are outside this slice.

## Rollback

Omit the output-contract option to use the unchanged text path. Keep raw first outcomes and both cohorts' scores. No model/config/Vault/database/Qdrant migration or automatic default activation. New structured-mode results and software tests do not replace full regression, broader specialist evaluation or release acceptance.

## Integration findings retained

R1 stopped before its first constrained completion: the first catalog fixture lacked native run/call IDs and snapshot workspace/trust/omission metadata. Accept the exact real envelope and verify it through the existing native workspace tool in regression tests; do not weaken snapshot hashes or admit arbitrary envelopes.

R2 completed 48 first outcomes, but nine constrained replies failed host validation. The pinned server's README example used a flat `schema` with `type=json_schema`; the actual parser at `tools/server/server-common.cpp:1312` reads `response_format.json_schema.schema`. The former silently becomes a generic object grammar, so R2 is **not evidence of schema enforcement**, regardless of its scores. Keep all receipts and diagnose this as incorrect client binding. Use the nested form required by the actual pinned implementation, test its exact payload and run adversarial development controls before freezing a new R3 cohort. Never regrade R2 after the fix or claim the runtime enforced the original schema.

## Observed staged outcome

[R3 result](../HAR008_OUTPUT_CONTRACT_RESULT.md): corrected binding passed three adversarial development controls, then 48 fresh frozen first native calls. Text baseline/skill strict 8/12 each; constrained baseline/skill 12/12 each, zero contract failures and all 24 schema/catalog/content/provenance checks matched. No added skill benefit at saturation; broad specialist promotion remains NOT_QUALIFIED. Final related software 323 PASS/3.89s, no model calls in pytest. This verifies only the bounded remediation slice. Keep semantic/resource/full-regression/release gates and default text unchanged. Primary desktop and CORE were not restarted; the owned trial process was stopped.
