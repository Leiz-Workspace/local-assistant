# ADR-137 — Host-selected boolean answer contract

**Purpose:** Address confusion between a boolean expression's value and a proposition about that expression without injecting expected answers or changing models.

Date:2026-10-26. Status: Accepted for one new balanced qualification and, only if justified, a separately frozen complete fresh validation. No model/default/production adoption.

## Evidence and hypothesis

The first complete native reasoning gate measured CORE41/42 and UNRESTRICTED42/42 exact facts, both42/42format and all lifecycle/provenance/context/stream checks. CORE's sole failure answered False to whether `False and (1/0)` returns False without raising. The statement is true; the returned expression value is false. Keep that first failure and the whole first cohort unchanged. Longer reasoning already improves the other observed error families, but is not a universal guarantee.

The remaining hypothesis is task interpretation: distinguish a yes/no claim's truth from the value of an expression mentioned in it. Add an explicit host-selected `boolean_answer_contract` option, defaultFalse, to the new optional adapter. It prepends a generic clarification only when the trusted schema's answer type is boolean. The text contains no case IDs, actual expressions, sources, expected answer values or feedback. It applies equally to true/false and value/proposition tasks. System/profile templates, schema and native budgets remain unchanged. Nonboolean/media/context/stream shapes receive no prefix. Existing default input validation remains mandatory before adding host text.

## Assessed qualification and limits

P1 dependency of D14-SEMANTIC-001. Effort: one small host-option/test milestone, twelve new balanced tasks/profile and conditional complete fresh validation. Risks: overfitting the observed interpretation failure, always-True/False bias, conflict with expression-value requests, added input text and confusing a twelve-case signal with full quality. Use sixTrue/sixFalse cases covering computed booleans, claims, short circuit, nonempty strings/lists, source state and logic. Every expression/source differs from earlier measured questions. Verify exact first JSON, actual prefix, native reasoning, provenance/cancel/retirement and baseline; no neural retry or answer repair. Only12/12 per profile may support a new full42-case validation, whose separate protocol/corpus must be frozen before its load.

Use exactly the same models/projectors/runtime32K/GPU99/thread2/reasoningoff default, request reasoning512/total1024 and all current resource guards. Qualification cap24scored+2planned nativecancel requests, request90s/campaign1200s. No new weights/packages/config/services, no unrestricted action authority. The previous full audit completed before editing this adapter; retain its exact executed adapter/test sources and first report. This option does not relabel that failed aggregate gate.

## Migration and rollback

No route/default activation. Explicit callers alone may select the option; truthy untyped values are rejected. Old730application files remain byte-identical; changes are confined to the two new adapter/test files and benchmark/docs. Rollback leaves the optionFalse, preserving the prior path and all evidence. Full732regression, product/manual/rights/release claims are independent. A conditional fresh full pass would qualify only that bounded selected mode and never rewrite old scores or change agreed model choices.
