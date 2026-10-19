# D28 — Source-held grounded generation

**Purpose:** Describe the opt-in grounded API, exact source-citation contract and observed acceptance boundaries.

**Status:** PASS for local opt-in scope. Full1334 PASS/1387.90s, then2 additional real native-field cases PASS/1.21s, each0 SKIP/exit0;1336 unique tests across checkpoints, not one1336-case full invocation. [Acceptance](evidence/d28-grounded-acceptance.json), [post-audit](evidence/d28-final-post-audit.json).

## Behavior and configuration

`POST /api/v1/grounded/answer` requires the existing authenticated local-client policy. `ASSISTANT_GROUNDED_ENABLED=1` enables it only with existing enabled dense retrieval; default0 creates no grounded service. Preserve all existing source/indexing/retrieval configuration and model choices. See [ADR-043](ADR/043-source-held-grounded-generation.md).

Input is `{"query":"What port does this project use?","top_k":3,"file_ids":["<owned-file-uuid>"]}`. `file_ids` is optional,1–16 UUIDs when supplied; `top_k` is1–3. Query is nonblank and at most4096 UTF-8 bytes. Additional keys and caller model/profile/owner/provenance overrides are rejected. The service has one nonqueued operation, fixed existing CORE/fast, temperature0, output512 tokens and a60-second model deadline. Complete prompt budgeting never silently truncates sources or switches models.

Responses have `status` of `answered`, `insufficient_evidence` or `no_sources`. Answered requires a nonblank answer and1–3 exact quotes. Insufficient evidence has null answer/empty citations; no_sources additionally skips generation. `answer_trust` distinguishes model-generated output from no generation; source content remains `untrusted`. Responses are private/no-store/nosniff. No conversation/history/memory write is introduced.

The model emits only source IDs and exact quotes. The server attaches file/point/chunk/source-hash/generation and rehydrated provenance. `quote_span` uses Unicode code-point offsets in chunk text or an individual lexical source field. `source_span` maps the same quote to the authoritative native page/paragraph/cell field and offsets. Combining characters are preserved; offsets are not PDF byte positions. DOCX table paragraphs, XLSX values/formulas/caches and OCR cells are individual evidence units, not serialization keys. Quality metadata preserves OCR review and formula-cache uncertainty. At most64 evidence units are allowed without truncation.

Missing, ambiguous, duplicate, foreign or fabricated quotes, extra output keys, duplicate JSON keys, nonfinite constants and incomplete completions fail closed. Exact quote verification establishes source provenance; it does not prove that every generated claim follows semantically from the quote or establish confidence calibration.

## Source lifetime and rollback

The unchanged dense operation retains authorized source readers through generation and response delivery. Owner/root/hash/current SQL generation is checked before/after inference and immediately before headers. Delete/supersede during inference or before final delivery prevents an answer. Operations ordered after the final authorization point are not a distributed transaction with delivery.

Timeout/cancellation/shutdown join the owned model-client task before source readers close. Grounded shutdown precedes retrieval/file shutdown. The shared CORE server is not killed or restarted; this does not certify backend KV-cache erasure or immediate backend compute cancellation. Disable and drain grounded generation to return to the existing API without deleting/reindexing source or vector data.

## Verification record

Initial v1 focused run71 PASS/1 FAIL/52.60s: page-two query returned insufficient evidence because the prompt omitted native page location. [Failure](evidence/d28-initial-failure.json) and [v1 freeze](evidence/d28-execution-freeze.v1.json) are retained. ADR-043 records the pre-acceptance amendment: include native locator/field/quality and map structured lexical fields. Source questions/bytes/model/output limits and exact quote policy remain unchanged.

The revised [execution freeze](evidence/d28-execution-freeze.json) precedes focused82 PASS/94.72s. Seven live cases include six actual CORE completions for known PDF facts, Unicode page location, a limited hostile-source instruction, second-owner isolation, absent identifier and immutable replacement. Other live fault cases deliberately use controlled model ports to test actual SQL/source cancellation/delete/supersede/final-delivery/malformed-output behavior; they are not additional real-model quality samples. Unit tests cover strict budgets, source-field goldens, cancellation/shutdown order and API startup/default-off contracts.

The separate [TCP freeze](evidence/d28-tcp-execution-freeze.json) precedes one real approved embedding/CORE/SQL/Qdrant request over temporary loopback Uvicorn. It uses the fixture event loop, not a separate production process, sustained load test or deployment SLO. Focused raw outputs are preserved separately from the running full regression. Final regression, audit, acceptance and source archive remain pending.


## Final local acceptance — 2026-10-19

Full1334 PASS/1387.90s (23:07),0 SKIP/exit0 includes all original1251 tests and83 D28 cases. Focused82+TCP1 are subsets, not additional unique tests. Two tests added after collection independently verify all7 DOCX paragraph/table lexical fields and11 XLSX cell/value/formula/cache fields against the existing fixture README goldens through actual retained source/SQL/native processors, ingestion planning and production citation parsing:2 PASS/1.21s. They perform no model inference or embedding-token admission and do not certify arbitrary document indexing. Total1336 unique tests across checkpoints, not one1336-case full run. No production code changed after the successful full run.

Final actual six CORE outcomes agree with focused outcomes; actual full/focused synthetic raw observations are retained separately. Exact-source field, generation/hash/owner and Unicode quote goldens pass. Source delay/delete/supersede/final-delivery, cancellation/repeated cancellation/shutdown and sanitized invalid-output gates pass with their disclosed real/controlled port boundaries. Read-only audit: schema0004, files/jobs/heads/quota/probe DBs/Qdrant collections/live model workers/advisory locks0, original owners/ACLs unchanged, immutable manifest UPDATE denied/state allowed/TRUNCATE denied. Registry/model selection/E5 rollback/dependencies/migrations unchanged.

ADR-043 and execution freezes intentionally retain their pre-execution status/text; this measured acceptance resolves their pending D28 gates. The v1 failure remains a failure, not overwritten by v2 success. Source-only full-file archive: `/tmp/local-assistant-d28-complete-full-files.zip`. Local commit includes dev log; no push or production enablement. D29 memory class/consent/provenance schema is next.
