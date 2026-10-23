# ADR 128 — Source-derived string vocabulary

**Purpose:** Preserve exact source spelling during typed extraction instead of allowing native generation to drop or normalize combining marks.

**Date:** 2026-10-24 (Asia/Ho_Chi_Minh). **Status:** Accepted for explicit optional implementation and one bounded fresh paired evaluation; no default or model choice change.

## Evidence and assessed scope

D81-FMT-004's first wire-order-corrected campaign remains FAIL5/6. Both modes emitted scalar `cafe-z` for raw source `cafe\u0301-z`; schema mode preserved the original combining mark in the quote, and the publication guard rejected the scalar. Both explicit negative refusals passed; conditional native workflow was not run. Old results/source/oracles remain immutable.

Schedule D81-FMT-005, P2 existing format remediation. Dependencies: exact source units, wire-order fix, typed publication guard, established CORE and pinned per-request JSON grammar. Effort one literal-domain implementation/validation milestone. Risks: silently normalizing model output, leaking expected answers into grammar, oversized vocabularies, forcing one chosen gold value, excluding unsupported mid-token extraction and claiming general factual correctness.

## Decision

Add explicit `literal_strings=True` to the optional schema adapter; its default remainsFalse. Enumerate **all eligible raw source spans**, including distractors, within admitted units. Spans align to whitespace-delimited token windows, optionally exclude surrounding quotation/sentence punctuation, and preserve interior whitespace/punctuation/Unicode byte spelling. Each is1–24codepoints; at most512choices per source. Reject overflow/unsupported domains instead of truncating candidates. No NFC/NFD normalization, transliteration or replacement of emitted content. `C++`, dotted values and short multiword literals retain their source spelling.

Use this data-derived domain as a native string enum and recheck membership locally. The adapter consumes source text/field types only; it never reads expected fact values or expected quote labels. Candidate lists include non-answer words/phrases and alternative source values. Integer types/literal checks, quote choices, explicit refusal branch, original system template, native budgets/model/owner/source authority and old API remain unchanged. This is bounded source-literal extraction, not arithmetic, translation, arbitrary mid-token extraction, semantic truth certification or model adoption.

## Predeclared fresh evaluation

Freeze `d81-typed-paired-v3.json`: six new EN/VIpositive cases and two new missing/instruction-only controls before inference. Pair typed-schema against source-string-schema, same messages/settings and declared property order; only the source-derived string enums differ. Integer-only cases are unchanged controls. Require exact scalar types/values and all18minimal quotes, both explicit negative refusals with withheld publication, source/CORE identity preserved. Only then run the original native file/code/authored-web workflow once, with original question/oracle, excluded from fresh scores.

Maximum16requests including recovery:12paired+2negative+1conditional workflow+1recovery. Fast512/temperature0/20second requests,360second campaign plus30second final recovery. Retain every first raw payload and all failures; no regeneration, feedback or output repair. No new weights/SDK/model/context/resource cap, config, route, Vault, database or collection changes. A failed campaign stays unqualified and does not activate this component.

Prepared82new controls within214related PASS/0FAIL/0SKIP/0.82s/RuffPASS. Source-vocabulary tests cover combining marks, quotation/multiword/internal punctuation, distractor inclusion, bounded candidate overflow and independent backend-domain enforcement. The original5507full/712file foundation remains unchanged; current additive files have separate focused/native evidence. Rollback closes the optional adapter and keeps original defaults plus every first artifact. D70hearing0/24, device/model/license/D14quality and final release decisions remain independent gates.
