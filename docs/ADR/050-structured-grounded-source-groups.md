# ADR-050: Preserve verified native row relationships in grounded evidence

**Purpose:** Repair an observed D32 table-answer failure without changing models, citations, indexes or agreed retrieval policy.

**Date:** 2026-10-20 (Asia/Ho_Chi_Minh)

**Status:** Accepted design for the necessary local repair. Runtime/day acceptance requires unchanged frozen D32 cases, transport/privacy regression and cleanup audit; see the D32 acceptance evidence.

## Evidence and decision

On accepted baseline `f010abc`, the frozen D32 integrated test failed after70.32s: TXT/PDF answered correctly; DOCX returned `insufficient_evidence` despite actual dense top3 retrieval including table1 row2 with paragraph5=`một` and paragraph6=`42`. `evidence_units` correctly projects exact fields but `build_messages` omits their shared row, column and table relationship. Independent native citations passed earlier; this composed semantic loss was not covered by that parser test. Preserve the original failure and source manifest; do not weaken the question, expected42, relevance or top3 policy.

Add `source_groups` to user JSON only for structured-row hits. Each group identifies the exact field source IDs already provided, native row locator, section path and complete existing verified structure. It conveys existing row/cell/sheet relationships; it introduces no new source or model fact. Plain TXT/native PDF user JSON remains identical. Fixed instructions identify group metadata as untrusted context and permit citations only to exact lexical source fields. Structured text remains untrusted data and never enters system instructions. Exact quote/span/parser contracts and all existing byte/evidence/token/deadline/source-delivery fences remain authoritative.

## Effects and alternatives

Prompt bytes/tokens increase for structured rows because native structure repeats field content. Keep the existing32768-byte prompt guard and tokenizer/context budget; refuse overflow without truncation. Tests must cover native grouping, duplicate/ambiguous quotes, metadata-only quotes and adversarial structure. Do not widen top3, add reranking, rewrite chunks, reindex, replace models or silently claim that exact citation proves arbitrary semantics. Passing this small same-agent set is local integration evidence only.

Embedding/model/profile/registry/migrations/database/vector schemas and stored generations remain unchanged. No migration is needed. Rollback is reverting this prompt-only change to `f010abc` behavior; existing indexes and data remain usable, with the demonstrated table limitation restored. If the frozen gate still fails, retain failure and continue diagnosis rather than accepting D32 or changing agreed models.
