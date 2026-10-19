# D26 — Private source-revalidated retrieval

**Purpose:** Describe the implemented opt-in dense search contract, authorization, resource lifetime and acceptance boundaries.

## Request and source contract

Authenticated loopback `POST /api/v1/retrieval/search` accepts JSON with `query`, optional `top_k` (default5,1–10) and optional `file_ids` (1–16 unique UUIDs). Query text is preserved exactly and bounded to4096 UTF-8 bytes; blank/invalid Unicode is rejected. Unknown fields, caller owner/namespace/model/generation/vector/filter and coercible top-k are refused. File UUIDs narrow the authenticated scope and never grant access. Responses are private/no-store, nosniff and at most1MiB. Retrieved text is untrusted data, never an instruction or automatically added model context.

Query formatting uses the approved profile's exact instruction plus original text. The existing passage encoder has an empty passage prefix, so passing these complete instructed bytes yields the same input as the approved benchmark's query branch. Existing offline tokenizer preflight includes special tokens and instruction in the512-token cap, refuses overflow, and must agree with the actual encoding count/fingerprint. The exact same ingestion encoder instance/admission prevents concurrent query/document model processes. No new model, download, dtype, worker lockfile, project dependency or automatic fallback.

The read-only Qdrant adapter verifies existing installation/model collection ownership and schema, then submits a dense query with server-built conjunctive owner/namespace/model/private/untrusted/active predicates. It never creates/indexes/updates/deletes a collection or point. Optional file UUIDs add a conjunctive condition. Result size is bounded to `candidate_limit=max(20,5*top_k)` (maximum50); IDs/scores/payload scope/duplicates are checked independently. No vector is returned by the server. [Qdrant1.18 API](https://api.qdrant.tech/v-1-18-x/api-reference/search/query-points) documents the underlying query protocol.

Candidates remain untrusted hints. SQL active-generation/source-ready/owner/root/hash joins reject deleted, stale, unpublished and superseded points even when physical Qdrant cleanup is pending. Membership must match the immutable job's deterministic UUID points. Existing source extraction rebuilds the exact D25 manifest and complete allowlisted vector payload; mismatches fail closed. Text and full provenance/quality are taken only from this verified reconstruction, never Qdrant-supplied source content. OCR/formula/cache/review uncertainty remains exact and similarity scores are not calibrated confidence.

Files are rehydrated sequentially through the existing chunk slot. Separate verified source readers remain held through response delivery; a nonqueued search slot and FileService task tracking cover the same lifetime. Before headers, readers are reverified and a final single SQL snapshot validates every retained active generation and source fence after integrity I/O. A delete or publication after that authorization point is ordered after authorization; there is no distributed SQL/Qdrant/HTTP atomicity claim. At most10 retained source readers correspond to returned hits. Repeated source/integrity/SQL work favors local correctness over a production latency claim.

Stale/deleted candidates are omitted within the explicit candidate budget; results may contain fewer than top_k without proving corpus exhaustion. No unbounded refill, arbitrary result offset, reranker, hybrid retrieval, citation-generation or quality threshold is implemented. D27 evaluates the original Qwen3-Reranker-0.6B candidate separately and does not authorize changing the embedding model.

## Startup and rollback

`ASSISTANT_RETRIEVAL_ENABLED` defaults to0. Set1 only alongside explicitly enabled, approved D25 ingestion/files and their existing private operator credential/ownership file. Retrieval initialization checks the existing owned collection; it reads no additional secrets and makes no vector mutations. No production flags/configuration/collection were enabled during acceptance. Approved selection still records `selected_not_deployed`.

Shutdown disables/cancels/joins retrieval responses and encoding before ingestion closes its encoder/vector/worker resources, then files/pool close. Rollback disables/drains retrieval and retains source, journals, collection and ownership; no migration/downgrade/deletion is needed. Existing schema0004 and all original model/source grants remain unchanged.

## Verification status

**D26 PASS for local opt-in retrieval:** final full1030 PASS in216.32s,0 SKIP;51 new tests, focused51 PASS/54.37s. [Evidence](evidence/d26-retrieval-acceptance.json) and [post-audit](evidence/d26-post-audit.json) retain actual results and clean inventories. Actual HTTP drives approved CPU Qwen/SQL/Qdrant/source paths with two principals, narrowing, replacement/delete and query overflow. Explicit unit-vector fault fixtures test stale/tampered payloads, final source/generation races, admission and joined cancellation/shutdown without claiming quality scores. All11 changed Python files pass Ruff/format and68 function/class descriptions.

D27 baseline/reranker evaluation planning is NEXT. Production multiworker/load/DR, independent large-corpus quality and long-input validation remain outside this local scope. No production collection/configuration or new model was created.
