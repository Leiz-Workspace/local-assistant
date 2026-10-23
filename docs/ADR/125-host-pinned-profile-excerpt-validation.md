# ADR 125 — Host-pinned profile excerpt validation

**Purpose:** Define an optional output guard for D81-FMT-001 without changing profile templates, model choices or original evaluation scores.

**Date:** 2026-10-23. **Status:** Accepted for independent component implementation/testing under the owner's continuation instruction. No production route activation or model-quality acceptance.

## Problem and decision

The retained D81 CORE reply contains three literal, unique, supporting quotes, but only one matches the requested fact-only excerpt. Source membership alone cannot enforce this narrower formatting contract. Preserve that first failure and all original fixtures/oracles.

Add a separate immutable `ProfileExcerptGuard` after the existing `ProfilePromptRun`. A trusted host pins authenticated owner/workspace, explicit profile/model, the existing committed template, the exact prompt digest, ordered source hashes and one exact Unicode codepoint span per source. It also declares the expected answer field names. None of these pins are accepted from model output. Reject ambiguous/repeated excerpts, including overlapping occurrences, before admitting replies.

Before issuing a receipt, recheck reply scope/provenance, complete Fast-result identity and finite usage, bounded strict JSON, exact top-level fields and one exact citation for each pinned source. Reject longer paragraphs even when they occur literally in the source. Do not trim, normalize, repair, retry, generate replacement text or invoke inference. The receipt hashes unchanged raw reply bytes and reports original source hashes/codepoint offsets. Audit finite outcomes/counts without content or actor identifiers.

## Scope, dependencies and acceptance

This schedules only the P2 D81-FMT-001 **deterministic admission subtask**, one bounded implementation/validation milestone. Dependencies are existing profile reply provenance, trusted source snapshots and host-selected excerpts. Risks are confusing formatting with factual correctness, accepting model-selected policy, offset ambiguity, overfitting Atlas constants and silently rewriting the original failure. Independent Vietnamese/code/Unicode/whitespace cases, ambiguity/shape/scope controls and unchanged D81 replay test these boundaries. It adds no dependency, endpoint, default policy, service, model load, schema or migration.

The guard does **not** find the relevant excerpt, prove that an answer follows from it, validate answer value types/semantics, authenticate an arbitrary Python object, refresh a deleted source or replace a source-lifetime authorization fence. The host must obtain `ProfileReply` through its trusted component, keep current source authorization and apply its own factual/schema checks. Any exposed integration needs those checks; this component is not registered in existing routes. A matching digest is provenance, never an approval or execution capability.

## Outcome and rollback

66 new controls within 227 related tests PASS, zero failures/skips; retained D81 reply is rejected with `excerpt_mismatch`. Its original strict score stays 1/3 and grounding 3/3. There are no new neural measurements, so D81 model-format quality remains OPEN. Existing 707 D87 files and all protected historical inputs remain byte-identical. D87's 5405 result describes its prior frozen snapshot, not a full run including this addition.

Rollback stops using/removes the optional new guard and its tests while retaining evidence. Original model/templates/API and all data are unaffected. Actual listening, product/model/license decisions and final release acceptance remain open.
