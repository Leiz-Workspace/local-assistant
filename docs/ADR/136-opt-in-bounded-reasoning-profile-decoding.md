# ADR-136 — Opt-in bounded reasoning profile decoding

**Purpose:** Correct the research token-budget mismatch and evaluate native reasoning as an optional semantic improvement on unchanged agreed models.

Date: 2026-10-26. Status: Accepted for implementation and one fresh complete validation within the owner's request to find a solution. No model/default/production adoption.

## Observed evidence and fault

The fresh twelve-question paired diagnostic generated all48first native responses. Direct strict facts were7/12 for both profiles. Native thinking final JSON was12/12 for both after offline verification using the declared request budget. Thinking cost approximately84–86seconds per12cases versus5.6–6.2seconds direct, and6444/6458output tokens versus277/287. These small matched fresh text results support further evaluation, not a universal quality claim.

The first research subclass sent max1024 but retained the parent's self.max_tokens512; all thinking replies used more than512total tokens and were rejected by its validator. The first diagnostic therefore remains invalid/unqualified with0/12accepted thinking per profile. Preserve its exact source/tests, failed first measurements, native bytes, freeze and audit. An independently labeled declared-budget replay may inspect existing bytes, but never overwrites first scores. This implementation fault is separate from earlier D14 factual failures and was introduced during the investigation.

## Decision and assessment

Correct the research adapter's total limit and cover native usage540/1024/1025 in tests. Add a separate unregistered `ReasoningProfileAdapter` extending the unchanged structural adapter. It sets both request and validator max1024, thinkingTrue, native reasoning budget512 and reasoning_formatdeepseek. Reuse exact existing profiles/templates/schema validation, bounded HTTP/SSE and owned cleanup. Require actual nonempty native reasoning; preserve final content verbatim. For streams, keep reasoning separate and reject malformed or late reasoning. No expected answer enum, value insertion, source-label extraction, hidden oracle feedback, neural retry or executable generated code.

D14-SEMANTIC-001 remains P1 before promotion. Dependencies: exact current models/projectors/native runtime, strict shared gate/provenance/lifecycle, independent references and first-trial evidence. Effort: one additive adapter/test and fresh complete42case/profile validation. Risks: latency/token overhead, thinking budget truncation, long-context headroom, SSE wire size, label ambiguity, mistaking replay for first success, overfitting observed questions or changing model defaults. New images/text/codes/sequences and frozen references mitigate repeated-case bias; the full42/42 criteria remain unchanged.

Run only new questions through the optional adapter, including fresh media/context/streaming. Keep configured reasoningoff/context32K/GPU99/thread2/batch512/ubatch128, all resource guards and no initial/final native process. Only explicit owned requests enable thinking. Long-context prompt usage plus1024must fit32768. At most84scored first requests plus2planned nativecancel probes, no replay of old questions or mode-tuning campaign. Missing/incorrect answers retain a zero in their denominator. Full local quality requires42/42format+facts/profile, verified native reasoning, actual cancel/retirement, five distinct provenance passes and restored baseline.

## Impact, migration and rollback

No new models, weights, packages, config, Docker/Vault/database/Qdrant/data/provider/HTTP routes. Existing730application files stay byte-identical; new adapter/test add two files. No fresh full-suite result is inferred from scoped tests or native benchmarking. Original scores and D70/manual/rights/release gates stay independent. No production migration: callers must explicitly instantiate the new adapter. Rollback omits it and retires only owned workers, retaining all evidence. A successful bounded fresh gate would qualify this optional path locally; it would not rewrite historical failures or authorize a release/default change.
