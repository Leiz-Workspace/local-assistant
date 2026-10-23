# ADR 127 — Opt-in source-derived structured CORE extraction

**Purpose:** Address D81's measured field/quote-format failures with bounded native JSON grammar, without replacing an agreed model or rewriting prior scores.

**Date:** 2026-10-24 (Asia/Ho_Chi_Minh). **Status:** Accepted for optional component implementation and one declared local paired evaluation under the owner's continuous-work instruction. No default/API activation or model-selection approval.

## Decision, dependency and risks

Schedule D81-FMT-003, P2 following ADR126's retained1/6FAIL. Dependency: unchanged existing CORE, D80v1 template/source provenance, original Fast512budget and the pinned runtime's documented per-request `response_format` support ([local primary documentation](../../runtimes/llama.cpp/tools/server/README.md)). Effort: one bounded implementation/test/paired-evaluation milestone. Risks: forcing answers when evidence is absent, supplying oracle answers as grammar, unsupported native schema features, source-boundary ambiguity, literal-but-wrong values, sticky server decoding state and hiding failed responses.

Add an opt-in CORE-only adapter implementing the existing inference port. Host declares one scalar fact per supplied source, string<=24characters or signed32bit integer, exact question, line/sentence unit policy and explicit grammar on/off. Reject profile/preset/budget/question/template overrides. Native grammar uses declared field names/types and **all eligible unique source units**, including untrusted distractors, as quote choices. It never receives expected fact values or expected quote labels. Boundary selection preserves exact source substrings; it is preparation of admissible units, not trimming/normalizing a model reply.

Grammar permits an explicit whole-result refusal: nested factsnull/citations[] or flat all-null facts/citations[]. The adapter reports finite insufficient-evidence failure and withholds an answer; it does not fill absent fields from a host oracle. Local checks independently reject backend noncompliance: wrong model/finish/usage, extra/missing fields, wrong scalar types, duplicate/foreign/nonliteral quotes and scalar values absent from their assigned quote. Literal consistency is not general semantic correctness, source truth or current source authorization. Callers still maintain source-lifetime fences and independent factual checks. Long/ambiguous/unsupported sources fail rather than silently truncate.

Reuse existing native model verification/template/tokenizer/budget helpers,32Kcontext and Fast512/thinkingoff. One adapter request, no retry/fallback/load; no new dependency, route, registry choice, config, Docker/Vault/database/collection change. Preserve raw native reply content. Separate immutable prompt/schema/native-request/content digests bind provenance; they grant no approval/tool authority. Both old source/template and all712files of the completed5507-test foundation remain unchanged.

## Fixed evaluation before any new inference

Freeze six **fresh** bilingual cases and two separate negatives, source/code/test inventory and instructions. On each positive case, perform one baseline request and one schema request, always baseline then schema, with identical messages/settings; only `response_format` differs. Do not send the baseline result/feedback to the candidate. Separately run two schema-only missing-evidence/instruction-only controls; require explicit refusal and withheld publication.

Only if all six schema cases and both negatives pass, run the original owned native file/code/authored-web workflow once with the new adapter and original question/oracle/source code. This historical-fixture regression is excluded from fresh-case quality and never replaces the original1/3result. Retain failures, raw first bytes and finite publication decisions before scoring. No repair/regeneration/score normalization. Fresh private exclusive roots; no overwrite.

Maximum16generation requests including one ordinary CORE recovery:12paired+2negative+1conditional native regression+1recovery. Fast512/temperature0/per-request20seconds,360seconds campaign wall plus existing30second final recovery bound. Same original PID37256/start63900/command before/after. Backend/model-scope failure stops remaining requests; completed format/refusal failures stay recorded. Acceptance requires six independently scored exact fact objects/18minimal quotes, two explicit negative refusals, conditional native workflow PASS, unchanged source and original CORE. Scope is this small authored extraction protocol, not general reasoning/injection resistance, superiority on a population, voice quality or release.

## Validation and rollback

Prepared **58new controls within190related PASS/0FAIL/0SKIP/0.70s**, Ruff PASS. Includes actual unchanged ProfilePromptRun/provenance composition, baseline/schema body equality exceptformat, type/source/template/usage/stop/cancel/budget guards, refusal support, signed-integer versus identifier/decimal distinctions and conditional campaign accounting with fixture transports. The completed full5507/712snapshot and qualified readonly audit precede these additive files; do not claim that full run included this new component.

Rollback closes/removes the optional adapter and keeps all first artifacts. Old API routes and default inference keep their existing adapter. Actual D70hearing0/24, physical-device review, D14weighted quality, voice/model/license choices and final release approval remain separate. No replacement model or unapproved deployment follows from this ADR.
