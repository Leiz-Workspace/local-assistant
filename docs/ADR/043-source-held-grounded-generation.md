# ADR-043 — Source-held grounded generation with exact citations

**Purpose:** Compose accepted dense retrieval and existing CORE generation while binding every returned citation to current authorized source spans.

**Date:** 2026-10-19
**Status:** Implementation in progress after D27 local evaluation PASS; actual D28 acceptance pending tests.

**Status note — 2026-11-11:** this line is historical. D28 later passed as local opt-in (roadmap row D28: full 1334 + 2 new native-field tests PASS, actual CORE/TCP). The original status is kept unchanged.

## Context and scope

D27 retains the approved dense path and defers production reranker adoption. D28 requires grounded generation and citations resolving to actual file/page/chunk spans. Reuse approved Qwen embedding/dense/source authorization and existing CORE/fast inference; no model/routing/precision change, new model download, database/schema/collection migration or conversation behavior change.

P1; depends accepted D26 retrieval/source lifetime, D27 evaluation decision and existing verified CORE inference/token budget port. Effort one development milestone. Risks: fabricated or ambiguous quotes, stale/foreign source delivery during generation, instruction injection in untrusted source text, output/token budget overflow, cancellation/model timeout and confusing provenance verification with semantic correctness.

## Decision

Add a stateless default-off authenticated local endpoint for source-grounded answers. Enable only through an explicit grounded flag with enabled dense retrieval. No chat/history/memory persistence or new secret path. Input is a bounded query, at most three retrieved source chunks and optional existing file UUID narrowing; no caller model/profile/owner/filter/provenance overrides.

Hold the unchanged dense response-lifetime context/readers for retrieval, CORE inference, parsing and final response delivery. Validate SQL owner/root/hash/active generation before generation, after model delay and immediately before headers. Drain/cancel grounded operations before retrieval/file shutdown; one nonqueued operation, bounded model wall and fixed output budget. Reuse existing public inference adapter with CORE/fast, temperature0 and output512 tokens; exact tokenizer/whole-message budgeting rejects overflow without truncating source bytes or switching models.

Keep sources in a clearly serialized untrusted data block under separate fixed system instructions. The model may return only strict JSON: answered/insufficient_evidence, answer/null and source-ID/exact-quote citations. It cannot supply authoritative file/page/hash/generation/offset metadata. Validate duplicate keys/extra fields/shape/size and stopped completion. Answered requires nonempty answer and citations; insufficient requires null answer/no citations. No-source requests return explicit no_sources without generation. No automatic fuzzy quote repair, model fallback, citation substitution or retry loop.

Resolve each nonblank quote as one unique exact Unicode-code-point substring of the retained current chunk. Reject missing/foreign source IDs, absent/ambiguous/duplicate quotes and malformed output before delivery. Attach original rehydrated file/source-hash/point/chunk/generation/locator/spans/processor/quality metadata, plus exact chunk quote start/end. These offsets are code points in reconstructed chunk text, not raw PDF bytes. Retain native page/paragraph/sheet/cell and source span provenance; structured/OCR uncertainty remains untrusted and visible.

Exact quote/provenance checks establish where quoted evidence came from; they do not prove every generated claim or calibrated confidence. Expose that answer text is model-generated and source content untrusted. Evaluation must check actual known-fact/insufficient-answer cases and malformed/foreign/ambiguous citation failures. Prompt-injection resistance is tested locally; authorization/source fences never depend on whether the model follows its instructions.

## Compatibility and rollback

Existing API source, ingestion, dense and conversation semantics remain unchanged except necessary new router/lifespan initialization/shutdown wiring. Default flag0 creates no new resources or collections. Disable/drain the grounded service to restore existing API behavior; no source/journal/vector deletion or reindex. Preserve original model registry/selected embedding/E5 rollback and all data. Any later model/routing replacement still needs owner's explicit approval and separate benchmark/migration/rollback.

D28 is accepted only after exact source/citation golden cases, real approved embedding/source/CORE generation, owner/root/delete/supersede/final-delivery, budget/malformed-output and cancel/shutdown tests plus related-system regression/post-audit. Record failures and actual limitations; do not claim universal factuality, confidence calibration or production SLO from pytest.

## Pre-acceptance amendment after initial real-model failure

The first focused run71 PASS/1 FAIL/52.60s returned insufficient_evidence for page-two copying. The prompt supplied source ID/text but omitted native page location, so a page-specific query lacked necessary context. Retain v1 source/manifest/log hashes. Add server-rehydrated locator/field/quality metadata to the untrusted evidence block; do not change question/source bytes/model/limits or weaken exact quote checks.

Related-system review also found that a quote in canonical structured-row JSON could refer to serialization scaffolding rather than an actual document field. Build a bounded deterministic evidence catalog: native page/paragraph/text chunks preserve their exact chunk text and source span; DOCX table paragraphs, XLSX value/formula/cache fields and OCR table cells become individually identified lexical evidence units using existing server-derived spans. At most three retrieved chunks and64 evidence units; no field/source truncation. Metadata remains untrusted data to the model, and output may still provide only source ID/quote.

Verify each selected evidence unit against one exact original field/span, resolve unique literal quotes within that unit and return both chunk/field-relative quote offsets and an authoritative original source-field span. Reject ambiguous/missing spans or unknown row representations before generation. Do not cite JSON keys/wrappers as native content. Preserve original structure/formula-cache/OCR quality metadata. This is a pre-acceptance citation-correctness amendment, not a model/routing/indexing change; original D22/D25/D26 source representations remain unchanged.

## Subsequent D32 amendment — 2026-10-20

D28 historical local acceptance is recorded in [its evidence](../evidence/d28-grounded-acceptance.json). The later frozen D32 integrated DOCX question exposed loss of native row relationships after otherwise correct field projection. [ADR-050](050-structured-grounded-source-groups.md) preserves these relationships as untrusted source-group context while retaining exact lexical citation authority, original model/top3 policy, budgets and source fences. The original D28 observations and guarantees remain historical, with D32 results reported separately.
