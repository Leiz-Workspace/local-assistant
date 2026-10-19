# D27-T03 — Independent relevance review preparation

**Purpose:** Provide a concrete score-blind review packet, preserve prior benchmarks and make missing human evidence explicit.

**Status:** Prepared; the owner volunteered to perform the independent human review on2026-10-19. Completed judgments are still pending. No human labels supplied, no inference on this challenge, no adoption approval. D27 remains IN PROGRESS; D28 is NOT STARTED.

## Frozen challenge

[Challenge input](../tests/fixtures/retrieval/d27-review-challenge.json) contains eight new queries and eight synthetic source snippets: exact release/generation, numeric/month selection, unresolved OCR identifiers, stale formula caches, rollback and a question that may have no supported answer. It is agent-authored and cannot be called independently authored, representative or production-held-out. Independent human review is a separate action still pending. Plain snippets do not test actual DOCX/XLSX/PDF extraction.

[Review packet](evidence/d27-t03-review-packet.json) contains all64 query/source pairs in deterministic hash order, without model ranks, scores, old target/negative role names or proposed relevance. Hash order reduces presentation-order coupling; it is not a cryptographic guarantee of reviewer independence. [Freeze](evidence/d27-t03-review-freeze.json) binds the exact source/tool/test/packet/pending-template bytes. Existing T01/T02 corpus, labels, top10 candidates, profiles, thresholds, reports and failure records remain unchanged.

## Human review

[Readable source/query form](D27_RELEVANCE_REVIEW_FORM.md) presents the same frozen content and64 pending cells. The JSON packet remains authoritative.

A private pending working copy is available at `data/backups/d27-t03-human-review.json`. It contains no completed labels or attestation.

Copy [pending response](evidence/d27-t03-review-response.pending.json) to a separate response file. Do not overwrite committed pending evidence. Read every query and source in the packet before viewing any future model ranking. Supply a boolean `relevant` and short reason for every pair, reviewer identity, timezone-aware ISO8601 `reviewed_at` and the exact attestation:

> I independently reviewed every query and document without viewing model rankings or scores.

`true` means the source directly supports answering the question, including a supported negative answer. A topical mention alone is insufficient. `false` means it does not provide that support. All sources can be false; do not invent a relevant source for an absent answer. Ambiguity, source mistakes or disputed questions require human adjudication and a separately versioned challenge before inference. Retain all old artifacts; do not silently repair labels after seeing results.

Validate a completed response with the existing uv environment:

```sh
uv run --no-sync python -m scripts.retrieval_relevance_review validate \
  --corpus tests/fixtures/retrieval/d27-review-challenge.json \
  --packet docs/evidence/d27-t03-review-packet.json \
  --review /path/to/completed-review.json \
  --output /path/to/new-validated-review.json
```

Review `packet_sha256` and `corpus_sha256` identify canonical JSON content; freeze manifests additionally bind exact file bytes. Keep the prefilled response hash unchanged.

The validator rejects changed content, duplicate/missing/foreign pairs or queries, pending/numeric labels, blank reasons, invalid timestamps/attestation, duplicate JSON keys, nonfinite values and existing output paths. Output is private0600 and audit logs contain counts/hashes/reasons rather than source or reviewer text. Structural validity does not authenticate a person, prove independence, measure quality or approve adoption. Test-generated labels exist only in protocol fixtures and are never retained as human evidence.

A human-reviewed challenge still needs a separately frozen paired-execution plan before inference: candidate construction, answerable/absent-answer metric definitions, groups, thresholds, repetitions and resource accounting. The old binary scorer rejects empty relevance; it must not be reused by assigning a fake relevant document or counting an absent answer as a perfect retrieval. No new benchmark result or complete execution-plan acceptance is claimed here.

## Resource-only probe

A separate [request probe](../scripts/reranker_request_probe.py) uses only the first original frozen diagnostic query and its exact ten old candidates. It never reads the new challenge. The unchanged pinned CPU BF16 batch4 runtime processes4+4+2. A new, separately frozen resource contract measures one fresh worker's import/verification/model-init/first query, three warm ten-pair queries, actual forward at a complete512-token input and rejection at513. Repeated `x` tokens are a meaningless resource stress input, not long-document relevance quality.

CPU120/121s, actual RSS4GiB, virtual address8GiB, child wall150s and parent wall180s are bounded independently of T02; no T02 budget is raised. No HTTP, source retrieval, embeddings, persistent co-residency or sustained CORE contention is measured. Worker-start-to-first-request begins inside the child before model imports; it excludes interpreter startup, uv launch and parent IPC. Parent total includes all four requests and boundary probes, so it is not a first-request HTTP SLO. Model init includes artifact validation/session load with uncontrolled filesystem cache. CPU time and peak RSS cover the entire worker measurement; RAM is not VRAM. GPU0 follows verified CPU-only Torch/parameter devices, not a host GPU inventory.

The first resource run failed before measurement because importing the comparison helper pulled application dependencies into the model-only worker environment. Its failure/log/source/manifest hashes are retained. Revision2 replaces only worker-side request/manifest loading with standard-library hash-bound loading; original model inputs, runtime and all budgets remain unchanged.

## Remaining D27 gates

P1; dependent on T02, independent human judgments, complete paired execution plan, actual HTTP/concurrent-service resource evidence and owner decision. Effort remains1–2 milestones after required inputs/authorization; risks remain diagnostic bias, long-input quality, CPU/RAM/latency, source/tenant races and false confidence. Review tooling and a resource-only probe do not satisfy these remaining gates.

No application routing, approved embedding, registry lineup, SQL/schema/ACL, sources, Qdrant collection, Vault, Docker or production setting is changed. Existing ADR-039/040 govern the reused evaluation runtime; this preparation introduces no application architecture decision. Any later integration requires its own ADR and owner-approved scope. [Adoption review](D27_RERANKER_ADOPTION_REVIEW.md) retains migration/disable-drain rollback and the original open gates.


## Verified preparation checkpoint — 2026-10-19

Focused61 PASS/15.65s; full1157 PASS/553.32s,0 SKIP, exit0. [Preparation acceptance](evidence/d27-t03-preparation-acceptance.json), [final raw resource probe](evidence/d27-t03-request-probe.json), [focused raw probe](evidence/d27-t03-request-probe.focused.json) and [readonly post-audit](evidence/d27-t03-post-audit.json) are retained. Original failed probe and both execution freezes remain visible.

Final full-run worker-start-to-first-query4.451425s, artifact/model-init2.236234s; three warm queries2.234218/2.211714/2.220581s, complete512-token forward1.113713s and513 rejection. Peak1549.250MiB process RAM,22.222974s worker user+system CPU, verified CPU-only allocation0; parent total12.639595s includes all requests/stress. Focused run differed (first6.987930s, init4.721388s, peak1565.941MiB); filesystem caching is uncontrolled and three warm samples establish no p95/SLO. Scope definitions above remain authoritative.

Post-audit: schema0004; jobs/heads/files/quota0, owned restore probes0, Qdrant collections0, live encoder/reranker/request-probe workers0, worker advisory locks0; original owners/ACL unchanged, immutable-column UPDATE denied/state UPDATE allowed/TRUNCATE denied. No old application source or model/benchmark bytes changed. The owner volunteered to review; completed human labels remain0/64. This is verified preparation/resource evidence, not D27 acceptance. D28 remains NOT STARTED.
