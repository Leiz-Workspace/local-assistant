# D27 — Frozen retrieval baseline and reranker comparison

**Purpose:** Separate actual baseline measurement from candidate evaluation and model/deployment approval.

## Scope and frozen identity

D27-T01 implements an evaluation harness; D25/D26 application code, approved Qwen embedding, source/ACL/lease/generation behavior, schema0004 and configuration remain unchanged. The harness measures actual source upload/admission/journal/Qdrant/D26 rehydration/final delivery authorization against a new synthetic diagnostic corpus. No reranker or hybrid search is implemented or selected.

The corpus was authored before inference:24 documents,36 queries,12 each Vietnamese/English/cross-language,12 intent pairs with near-topic negatives. Labels are binary and every document fits one unchanged256-byte chunk. This is agent-authored diagnostic data separate from D24's20/40 corpus; it is not human-blinded, held-out production data or evidence of general retrieval quality. Human adjudication/independent labeled coverage remains required before adoption claims.

- Corpus SHA256: `0bc96e6c5bebacb3ffbd3eedd4fed466c730f2f540eef556aeb4654949bd7ee8`.
- Plan SHA256: `4f39578e917b8a07175ea86946e21e76f577a0d7c6ffd5397ad1a6aaf6423048`.
- Approved Qwen fingerprint: `77a5716028f187821f9e6aa198b5c5774b5d69b54d95093701a7f2dfaaa0bc9b`.

[Corpus](../tests/fixtures/retrieval/d27-corpus.json), [plan](../tests/fixtures/retrieval/d27-plan.json), [ADR-038](ADR/038-frozen-retrieval-baseline-and-reranker-evaluation.md). Plan/corpus changes require a new version and paired rerun, never silent post-score edits.

## Actual encoding and explicit replay

One actual unchanged offline CPU worker encodes60 complete inputs:24 exact passages plus36 fully instructed queries, with the worker's existing batches of four and left padding. Full tokenizer counts/fingerprint/dimensions/normalization are validated. The harness retains only these real vectors in memory and rejects unknown text/model lookup; it has no random/unit/zero-vector fallback. Existing production query handling encodes one query per request; batching/padding can produce numeric differences. This evaluation is explicitly the frozen batch/replay configuration, not an assertion that singleton HTTP scores or latencies are identical.

Upload24 sources for one synthetic owner and a25th source for a foreign owner with bytes identical to the first relevant document. Each admission runs actual complete tokenizer preflight; each actual worker processes the trusted source with recorded real passage vectors and actual owned vector writes/verification/publication. No application monkeypatch or source/ACL bypass. D26 then replays36 real instructed query vectors twice while executing actual tenant filtering, SQL active-source checks, exact source reconstruction, retained-reader/final integrity and final SQL snapshot. Wrong-owner data is forbidden even for identical semantic content. Test cleanup removes only these owners/probes under existing ownership guards.

Retain all per-query top10 candidate IDs/scores/source hashes/point bindings, both replay orders and every miss. Binary Recall@3/5/10 and MRR@10 macro-average queries; nDCG@10 uses binary gain and log2 discounts. Missing relevant documents have null rank and zero reciprocal rank. Unknown/duplicate/unsorted/nonfinite/incomplete candidates fail measurement protocol. Fixed-seed2000-resample query-bootstrap intervals are descriptive; queries share12 intents and are not independent human samples.

Timing separates actual tokenizer/encoder batch wall time from cached-vector source retrieval/rehydration. Replay p50/p95 includes final checks/context cleanup and excludes per-request tokenizer/model startup, HTTP and serialization. It is not an interactive API SLO or measured reranker overhead. Child peak RAM/VRAM are not instrumented here and stay null; historical model resource evidence must not be relabeled as a new measurement.

## Verification and observed baseline

Focused22 tests PASS/89.34s:21 unit/oracle/identity cases plus one actual CPU/source/SQL/Qdrant measurement. Initial baseline Recall@3=.972222, Recall@5=.972222, Recall@10=1.0, MRR@10=.949074, nDCG@10=.961613; two replay rankings stable and identical-text foreign source excluded. Final full **1052 PASS/306.02s,0 SKIP**; T01 **PASS for local frozen diagnostic measurement**, D27 still **IN PROGRESS**. Full-run quality equals the focused run. [Actual baseline](evidence/d27-retrieval-baseline.json), [T01 acceptance](evidence/d27-t01-baseline-acceptance.json) and [clean post-audit](evidence/d27-post-audit.json) retain both replay orders/source hashes/misses; no candidate result is implied.

Frozen diagnostic warning gates (R@3>=.90, MRR@10>=.85, group R@3>=.80) do not grant model adoption. Retain misses: English `query-q2` against Vietnamese query/token policy ranks relevant source6; Vietnamese `owner-q1` against English ACL policy ranks2; Vietnamese `vision-q1` against English vision review policy ranks2. Other authored judgments rank1. Do not alter those judgments/content to improve the score.

## T02 reviewable candidate execution plan

Original candidate: **Qwen3-Reranker-0.6B**, official revision `e61197ed45024b0ed8a2d74b80b4d909f1255473`, Apache2.0, causal-LM yes/no scoring. [Official public metadata review](evidence/d27-reranker-metadata-review.json) records model/tokenizer LFS hashes and Git blob IDs without downloading weights/tokenizer assets. Config maximum positions40960 differs from card-advertised32K; neither is validated host long-input quality. The proposed complete pair+instruction/chat-prefix/suffix budget remains512 tokens, no truncation. [Pinned official card](https://huggingface.co/Qwen/Qwen3-Reranker-0.6B/blob/e61197ed45024b0ed8a2d74b80b4d909f1255473/README.md).

Before candidate execution: verify all artifact SHA256 values, exact yes/no token IDs and formatting; use a separate frozen CPU-only environment with proposed existing torch2.10.0+cpu/transformers4.57.6/numpy2.5.4 pins, batch1/two threads. No GPU, remote code, network during inference or silent input truncation. Complete a separate execution/approval record; this T01 metadata proposal does not provision/select the model. Proposed resource gates are measured child RSS<=4GiB (RAM, not VRAM/address-space cap), GPU allocation0, wall<=60s per ten-candidate query, with actual cancellation/timeout/process-death cleanup. These are unmeasured budgets, not results.

Compare identical frozen top10 candidates/source bytes/queries/labels. Reranker may only reorder; exact score ties use stable document ID. Adoption proposal requires no Recall@10 loss, macro R@3/MRR nonregression, group R@3 drop<=.05 and nDCG@10 improvement>=.02, plus protocol/ACL/resource/latency gates and independent human-reviewed quality coverage. Keep baseline/inconclusive is valid when gains are too small or evidence weak. Candidate reranking cannot recover sources absent from its fixed candidate set.

| Milestone | Priority/dependency | Effort/risk | Status |
|---|---|---|---|
| T01 frozen baseline | P1; D26 and approved CPU embedding |1 milestone; agent-authored small-corpus bias/cache timing confusion | **PASS local frozen baseline**;1052 full PASS/0 SKIP |
| T02 isolated original-candidate comparison | P1; T01 frozen candidates, pinned artifacts/runtime and separately reviewed provisioning scope |1–2 milestones; pair truncation, incorrect logits, CPU/RAM cost and quality regressions | **Batch4 local measurement PASS**;1096 full PASS/0 SKIP; batch1 FAILED CPU/incomplete; no adoption |
| T03 decision and authorized integration | P1; real T02 results, independent judgments, migration/rollback/owner decision |1–2 milestones if adopted; stale/foreign delivery and response/model lifetime | TODO; no adoption authorized |
| Conditional lexical/hybrid experiment | P2; demonstrated exact-term/numeric retrieval gap and separately frozen benchmark/ADR |1–2 milestones; fusion bias, extra index/state/resource and scope leakage | Unscheduled; no new search engine/configuration implied |

D27 remains IN PROGRESS, D28 not started. Do not change any agreed model/routing based on this baseline or on better candidate scores alone. Migration would preserve the approved embedding/vector space/source identity and default-disabled baseline, add only an approved reranking stage, and provide disable/drain rollback without deleting source/journal/collections. Production load/DR/long-input and safe tombstone compaction remain separate debts.

## Final measurement boundary — 2026-10-19

**Purpose:** Distinguish validated measurement from production/model adoption.

Final replay p50≈110.446ms/p95≈116.020ms over72 observations; actual tokenizer/encoder batch times and full counts are retained in baseline evidence. All source/candidate hashes were independently matched to corpus bytes after regression. Post-audit schema0004, source/jobs/heads/quota0, collections0, restore probes0, encoder processes0 and worker advisory locks0; prior owners/ACLs and grants preserved. Three Python files/22 function-class descriptions and Ruff/format checks PASS. No application, dependency, model/runtime/configuration/schema/Docker/Vault change. At this historical T01 checkpoint T02 was NEXT; subsequent candidate execution is recorded below.

## T02 measured follow-up — 2026-10-19

**Purpose:** Supersede historical provisioning/evaluation status without changing frozen T01 data or gates.

Original candidate was subsequently provisioned under the owner's continuation and evaluated in isolation. Batch1 v1/v2 failed to complete the three-round CPU budget; failures/source manifests retained. Separate CPU BF16 batch4 variant completed all three repetitions: diagnostic R@3/MRR@10/nDCG@10=1, same frozen candidates/labels; actual resource/quality gates pass, full1096 PASS/540.75s,0 SKIP. [Comparison and exact definitions](D27_RERANKER_COMPARISON.md). T01 plan's pre-execution NOT_PROVISIONED status is an immutable historical field, not current deployment evidence. No production/selection change; D27 remains IN PROGRESS, T03 independent/adoption review NEXT, D28 not started. [Review proposal](D27_RERANKER_ADOPTION_REVIEW.md).

## D27 final local evaluation follow-up — 2026-10-19

**Purpose:** Link final actual evaluation while preserving this document's original frozen measurements.

[Final decision](D27_RERANKER_EVALUATION_DECISION.md) retains approved dense retrieval and the original reranker nomination without adoption/model/routing changes. Owner delegated relevance tasks to AI; no human review fabricated. Three new actual paired rounds show equal answerable quality on the separately frozen limited v2 diagnostic. ASGI/CORE and actual loopback TCP/source/lifecycle/rollback pass;1234 full+16 new AI-focused+1 TCP PASS/0 SKIP (1251 unique tests across checkpoints, not one full invocation). Original gains, failed runtimes, inputs/profiles/thresholds and exact E5 rollback unchanged. D27 local evaluation PASS; D28 NEXT.
