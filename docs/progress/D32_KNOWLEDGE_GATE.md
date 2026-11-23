# D32 integrated local knowledge gate

**Purpose:** Explain the reproducible supported-format RAG evaluation and its practical limits before advancing to coding-agent work.

## Scope and reproducibility

[Pre-inference plan](../evidence/d32-knowledge-plan.json), [criteria](D32_KNOWLEDGE_TEST_PLAN.md) and `tests/integration/test_knowledge_gate.py` define immutable fixture bytes, manual source-field goldens, five answerable questions and two refusal cases. This is a small same-agent synthetic acceptance set, not independent human relevance, a general accuracy benchmark, a model comparison or a production SLO.

Use the existing configured local PostgreSQL, Qdrant, approved embedding and healthy original CORE/vision. Supply existing application PostgreSQL and scoped Qdrant test credentials through the protected runtime process, never source files, command arguments or committed reports. The test creates only fresh fixture principals, temporary blob directories and one acknowledged UUID-named vector probe, and removes these in fixture teardown. Run sequentially with other shared-service tests:

```sh
uv run --no-sync python -m pytest tests/integration/test_knowledge_gate.py -q -rs --tb=short
```

The explicit existing live-test flag and credentials are required. A skipped run does not satisfy D32. The new test retains incremental results under protected `data/backups/d32-latest-knowledge-live.json`, including failed checkpoints. Its fixture enables only the test instance's default-off file/ingestion/retrieval/grounded features; it does not alter production configuration.

## Demo cases

| Case | Actual path and source oracle | Required result |
|---|---|---|
| TXT | `cedar.txt` → approved Qwen/Qdrant → CORE; exact UTF-8 text | TCP7443 with native text citation |
| PDF | Existing native three-page fixture; page1 manual extracted golden | Alpha123 with exact page1 span; blank page yields no chunk |
| DOCX | Existing D19 table fixture; paragraph5=`một`, paragraph6=`42` | Table value42 with paragraph6 citation |
| XLSX | Existing D20 workbook; sheet1 C2 formula/cache preserved | Cache30 with C2 cached_value citation and `preserved_not_recalculated` |
| Cross-file | Unfiltered search across all four owned documents | Cedar TCP7443 with TXT citation |
| Absent fact | Atlas restore generation is absent from these sources | `insufficient_evidence`, no answer/citations |
| Foreign-only filter | Second principal's private canary document | `no_sources`, no answer/citations and no CORE call |

Each supported file must pass real complete-chunk embedding preflight and background publication; byte ceiling2048 and token ceiling512 are enforced independently. Citations must match exact source bytes' SHA256, native field/locator and Unicode offsets, fixture principal, chunk and active generation. Every citation must lie in a predeclared relevant field, and each answer must cite the actual answer-bearing value. Citation precision is measured over citations, not merely over successful HTTP responses.

## Limits retained from accepted components

- Dense top3 retrieval can miss relevant information. Four questions explicitly narrow to a selected document; only one answerable question searches across all four owned files. This is not evidence for large-corpus retrieval accuracy.
- Text-exact quotations do not prove every free-form generated statement. The frozen cases separately assert expected values and relevant answer-bearing fields; there is no general semantic entailment checker.
- Native PDF extracted text can differ from visual layout. This gate uses native text, not scanned-PDF OCR. OCR uncertainty and source-quality annotations remain untrusted; D18/D21/D28 tests provide their separate recorded scope.
- DOCX body paragraphs/table rows and conservative XLSX lexical cells are supported under existing package verification. Headers/footers, arbitrary layout, macros, external relationships and unrestricted Office packages are outside this gate.
- XLSX caches may be stale. Neither opening, indexing nor answering recalculates a formula. Quoting30 does not establish that current input cells evaluate to30.
- Atomic table rows can exceed the2048-byte test policy or512-token embedding limit; failure is explicit, never silent truncation. Oversized documents/chunk counts and strict source/parser budgets remain enforced.
- Grounded generation uses existing CORE/fast, at most three retrieved chunks, bounded quote/evidence budgets,512 output tokens and60-second model deadline. No reranker or additional model is adopted.
- Memory opt-in/consent/export/source invalidation remain D29–D31 scope; no automatic learning, prompt injection of memory, file-memory adapter or vector memory is enabled. Conversation soft-delete and retained backup/export/cache domains are not secure erasure.
- Production flags stay off. No model, source adapter, SQL schema, infrastructure, dependency or existing accepted behavior changes merely to make this test pass.

## Results

**D32 PASS for this defined local scope.** [Acceptance](../evidence/d32-knowledge-acceptance.json):90 focused PASS/108.24s plus9 HTTP/TCP/privacy PASS/105.51s,0 SKIP, both actual exit0. Actual approved Qwen indexes TXT/PDF/DOCX/XLSX as1/2/5/5 chunks; original CORE makes6 calls. Frozen results:5/5 answerable,5/5 exact relevant citations (precision1.0),1/1 absent refusal and1/1 foreign refusal with0 foreign CORE calls. [Actual native results](../evidence/d32-native-knowledge-live.json) and [audit](../evidence/d32-final-post-audit.json) retained.

The initial70.32s native failure is retained: DOCX row2 was retrieved but its relationships were omitted from the prompt. ADR-050 adds existing verified structure and exact lexical source IDs as untrusted groups; the original plan/questions/expected values/relevance/model/top3 policy remain unchanged. Plain TXT/PDF prompts stay identical. A new synthetic OCR grouping unit initially failed because its locator and spans disagreed; only the fixture was corrected. A private wrapper setup error and an accidental unscoped collection into optional upstream runtime tests are recorded separately; neither is a successful application test.

Application collection1621 succeeds;13 new tests were added. Historical D31 full1608 remains a separate baseline. This milestone revalidates99 related tests after the one-file structured prompt repair; **no fresh1621 full invocation is claimed**. Current audit verifies0006, no app/pending work, files/jobs/heads/memory/quota/restore probes/vectors/workers/advisory locks0, original owner/ACL/narrow grants retained, all other252-baseline bytes/protected models/migrations unchanged. D33 is next.
