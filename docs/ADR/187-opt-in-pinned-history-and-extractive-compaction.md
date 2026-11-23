# ADR-187: Opt-in pinned history and extractive compaction

**Purpose:** Record bounded history reduction and owner-private recall without changing approved model selection or claiming unmeasured semantic quality.

**Date:** 2026-11-11. **Status:** Implemented experimental mechanics; production/default adoption and full HAR-009 acceptance remain gated. Supersedes no prior model, memory, skill or approval decisions.

## Context

The owner requested context-overflow strategies: truncation, sliding window, summarization, compaction, retrieval, hierarchical memory and offloading. Existing product composition keeps eleven recent whole pairs, budgets with the native tokenizer and selects one of three source priorities. Older constraints can disappear; signed metadata history intentionally cannot recover raw dialogue. Q3 review experiments did not qualify general model reasoning or reliable semantic self-review.

## Decision

Add an independent optional `HistoryPolicy` to authenticated product chat. Absence executes the existing composer, browser streaming and CLI history behavior. Do not change the CORE model, context size, presets, skills, source-output contracts, base conversation APIs or storage configuration.

- `sliding-window` selects configurable recent complete pairs plus explicit one-based pinned pairs. Systems, pins and the current user request are mandatory. Drop only oldest optional pairs; refuse irreducible overflow. Strict source priority rejects any history loss. Invalid partial history or unavailable pins fail explicitly.
- `extractive-compact` additionally targets a configurable soft input threshold, caches omitted original pairs and selects up to eight bounded whole pairs by lexical overlap. It performs no LLM summarization, clipping or new inference call. Source hashes and turn references bind exact originals. Extracts are untrusted JSON within the current user message, never new live system/assistant roles or permission grants.
- Budget with the approved native template/tokenizer. Explicit policies reserve the finite requested/preset output ceiling and the existing 256-token reserve. Dynamic Unlimited retains the existing minimum 512-token final-answer capacity. Mandatory content may exceed the soft target but never the hard limit.
- `evidence-first` reserves sources only after mandatory pins/task; recent/strict preserve selected history before admitting sources. Never run legacy pair-dropping after new pin-aware reduction.
- Use a separate process-memory cache bound to the authenticated principal. Limits:128 KiB/entry,16 entries/2 MiB per owner,128 entries/8 MiB globally; TTL1,800 seconds without refresh. Reject admission rather than silently evicting live originals. SHA-256 checks detect byte mismatches, not factual errors.
- Expose explicit authenticated metadata list/raw recall/delete and optional request-bound lexical recall over at most four selected handles. No owner field, arbitrary path, cross-owner lookup, automatic memory scan, disk persistence, consent restoration or replay. Shutdown clears raw cache; expired entries are inaccessible and pruned on the next operation, not guaranteed physically erased at the expiry instant.
- CLI retains complete local history only in explicit modes, applies configured pins as pairs become available and refuses capacity beyond the existing request bound. Cache metadata remains inspectable after a model failure; cache deletion does not delete authoritative conversation history or client copies.

## Alternatives and consequences

Arbitrary text truncation is cheap but can split citations, pairs and constraints. Whole-turn sliding remains the low-cost default. LLM summaries may be more compact but need independent retention/contradiction evaluation and add latency; hierarchical memory also needs consent/invalidation. Existing file RAG remains independent. Durable offload would require storage/retention/ACL/recovery design; no database migration is justified in this slice.

Verbatim extraction avoids generated-summary fabrication but can still select the wrong/stale material or omit relevant facts. JSON/provenance overhead can exceed a short original window. Old assistant text remains unverified evidence. Prompt policy expresses precedence without guaranteeing model obedience. RAM cache reduces prompt input, not necessarily total application RAM, and vanishes on restart. Browser controls, task/tool-output compaction and durable working state remain pending.

## Validation and adoption gate

[Strategy guide and measured panel](../CONTEXT_MANAGEMENT_STRATEGIES.md), [native receipt](../evidence/context-policy-native-20261111.json):462 related software tests PASS/0FAIL/0SKIP in4.75s across38files; eight frozen preparation-only scenarios preserve expected whole-turn/pin/archive/fact presence and explicit overflow behavior. No generated answer grading, TTFT, peak resource, broad memory or semantic-summary claim. Prior first benchmark failures and scores remain unchanged.

HAR-009-A mechanics are verified experimentally; full HAR-009 remains PARTIAL. Preserve its semantic/citation/constraint/failure/resource acceptance criteria. Frozen paired semantic/resource evaluation must precede production/default adoption; LLM summary and layered consented memory need their own evidence. Current owner context work takes priority over HAR-008-Q4 research, without closing Q4 or its quality gate.

## Rollback

Omit `history_policy` and use the existing chat branch. Drain owned requests, explicitly delete cache or stop only the owned harness process to clear it. Do not restore grants, rerun writes, erase historical evidence, alter models/configuration or migrate databases. Existing signed metadata history remains metadata-only.
