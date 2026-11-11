# D27-T03 — Owner-delegated evaluation and isolated HTTP trial

**Purpose:** Record autonomous AI relevance review, actual request/concurrency evidence, preserved failures and the remaining measured evaluation decision.

**Status:** PASS for local evaluation/retain-dense decision. Three actual AI v2 rounds complete with equal dense/candidate answerable metrics1.0, gain0; ASGI/CORE and real loopback TCP verified.1234 full +16 new AI-focused +1 TCP PASS/0 SKIP;1251 unique tests across checkpoints, not one full invocation. [Decision](D27_RERANKER_EVALUATION_DECISION.md), [acceptance](../evidence/d27-local-evaluation-acceptance.json). D28 NEXT; no adoption.

## Review policy and pre-inference adjudication

The owner explicitly delegated relevance review and similar tasks to the assistant because they are unavailable. [ADR-042](../ADR/042-owner-delegated-relevance-evaluation.md) replaces the pending manual-label requirement for this local milestone. No human attestation is supplied or fabricated. Assistant-authored and same-assistant-reviewed data is a limited diagnostic, not independent-human or production-held-out quality. Historical human packet/template/assignment/scorer remain intact; their earlier requests do not remain current owner tasks.

[Original AI review v1](../evidence/d27-t03-agent-review-v1.json) finds that query04 can be answered negatively from doc-d, which states that the quarterly budget is not approved. Existing relevance instructions count supported negative answers as relevant. Hence v1 has8 answerable/0 absent cases and fails its minimum-one-absent coverage before inference. It is not repaired by calling that source irrelevant.

[Challenge v2](../../tests/fixtures/retrieval/d27-review-challenge-v2.json) changes only query04 to ask for the physical backup disk serial storing G-17. None of the eight original source snippets supplies it. Other seven queries/source bytes are unchanged. [AI review v2](../evidence/d27-t03-agent-review-v2.json), [plan](../evidence/d27-t03-agent-paired-plan.json) and [execution freeze](../evidence/d27-t03-agent-execution-freeze.json) precede all v2 inference. Coverage is7 answerable/1 absent. Same coverage minima/global nonregression/group R@3-loss<=.05 are retained; no scoring threshold is tuned from results. This explicitly versioned change is based on pre-inference ambiguity, not a post-score repair.

The scorer keeps absent support-retrieval metrics null, excludes them from answerable macro means and does not infer abstention/confidence from reranker probabilities. Require three actual paired repetitions, the same candidate/source/hash/point/generation sets and retained source authorization. Record every losing metric and unstable ranking. The eight-document pool is deliberately small; R@10 has little diagnostic power and seven answerable cases cannot establish population significance. Query-bootstrap intervals are descriptive only.

## Actual local request/concurrency measurement

[ADR-041](../ADR/041-isolated-http-reranker-trial.md) precedes implementation. Existing app source/startup/routes/settings remain unchanged. Only an explicitly owned test instance receives the evaluation wrapper; normal dense routing is restored before fixture cleanup. The trial retains all source readers and D26 SQL/owner/root/hash/generation checks through ranking, validates complete exact chunk-hash-bound scores, uses the actual ingestion encoder admission slot and rechecks sources after the model and before response headers. Missing/foreign/nonfinite/over-token scores fail closed without silent dense fallback. Exact original reranker weights/runtime/prompt remain; no model choice, vector-space/schema/grant or production change.

Focused46 PASS/213.98s includes41 protocol/control cases and5 live cases: actual authenticated approved-query/SQL/Qdrant/source/ranking/response, two source delete/supersede-during-delay faults, and actual worker cancellation/shutdown. Scoring/review-execution preparation focused31 PASS/.93s includes30 protocol/scoring cases and one pending-human-gate test; that gate reports no inference and proves no human quality result. The new AI-reviewed actual evaluation is separate and pending.

Focused observed in-process ASGI HTTP complete-response times:

| Path | Samples | Mean seconds | Descriptive p95 seconds |
|---|---:|---:|---:|
| Dense source search |3|5.615784|5.624668|
| Isolated reranker, CORE idle |3|11.592842|13.094273|
| Isolated reranker during bounded CORE traffic |6|10.935013|10.997904|
| Existing CORE before traffic drill |3|.191839|.258581|
| Existing CORE during drill |101|.155182|.158166|

Every one of six concurrent retrieval requests overlaps real CORE traffic.101 CORE completions overlap; traffic admits at most120 sequential requests over90s, with10s per-call timeout,16-token cap and at least.5s spacing after each call. Three idle CORE samples and a repeated cached short prompt cannot establish causal overhead or a speedup under load. Filesystem/prompt cache state is uncontrolled. Three/six samples do not certify a population p95 or production SLO. Timings include actual query preflight/CPU encoding, source/SQL/vector work, fresh ranking child, final response fence and ASGI serialization; exclude socket/network and production server scheduling. No TCP/network, persistent encoder+reranker co-residency or sustained production-load certification is claimed.

Existing CORE and approved embedding remain unchanged. The child is CPU-only; its RAM/CPU measurements are retained per request. CPU-only allocation0 is distinct from host GPU inventory/CORE VRAM. No new weights or package versions downloaded; frozen isolated uv lock reuses cached accepted pins. Failed batch1 T02 and initial request-probe import failure remain historical failures.

## Evaluation decision boundary

P1; dependencies verified local trial, separately frozen AI judgments/actual paired results, existing original diagnostic/failed-runtime evidence. Effort one evaluation milestone; risks same-agent bias, small pool, input ambiguity, CPU/RAM/latency, source-lifetime races and interpreting sort scores as confidence.

Current conservative recommendation is retain the approved dense path and defer production reranker integration: fresh-child request cost roughly doubles the measured local path, while general quality and persistent-runtime benefit remain unproven. Final local evaluation decision must include actual v2 outcomes; a failed candidate quality gate remains failed. Completing evaluation does not require adopting a candidate or granting owner approval. The original Qwen reranker nomination stays in MODEL_REGISTRY and may be revisited with broader evidence and a separately approved runtime/integration scope. No replacement or default routing is chosen here.

Any actual agreed-model/routing replacement still requires owner approval plus benchmark, performance/resources, migration and rollback. A future ranking integration preserves embedding/point/source identity, needs no reindex and rolls back by disable/drain to dense ordering without deleting sources/models/collections. Independent-human/representative quality, TCP/load and persistent-worker optimization remain explicit future evidence, not false PASS claims or new mandatory manual work for the unavailable owner.

## Final measured outcome

Actual v2 focused16 PASS/448.97s; all three rounds stable, seven answerable metrics all1 for both paths, no gain; absent metric null. Actual Uvicorn/TCP1 PASS/40.93s, observed dense5.606043s / rerank8.896878s / dense-after-disable5.634908s with auth/Origin/owner fences and identical source/point identity. Final post-audit rows/quota/probes/collections/workers/locks0, schema0004 and old owners/ACL unchanged. Retain dense and defer adoption; original nominated reranker preserved. Earlier pending/preparation wording describes pre-execution stages, not current work.
