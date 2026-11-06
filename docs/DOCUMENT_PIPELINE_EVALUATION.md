# D23 mixed-document evaluation

**Purpose:** Define reproducible pipeline acceptance, retained evidence and the limits of its quality/performance claims.

Priority P1 depends on accepted D17 source verification, D18–D21 native/structured/OCR/read/write paths and D22 chunk projections. Estimated effort one or more milestones; risks are circular oracles, treating expected rejection as universal support, masking degraded OCR behind pass counts, weak span coverage and leaking content into evidence. This milestone adds trusted synthetic evaluation scripts/fixtures/tests only, with no runtime architecture/API/persistence/dependency changes, so no new architecture decision is needed. ADR-026–030 contracts remain authoritative.

The reviewed [manifest](../tests/fixtures/pipeline/manifest.json) defines18 cases using independently documented existing goldens plus synthetic UTF-8 and rejection fixtures. The [corpus guide](../tests/fixtures/pipeline/README.md) records actual ground truth and supported boundaries. The evaluator runs actual verification and sandbox processors on read-only source FDs; fixed DOCX/XLSX edits are independently opened using dev-only python-docx/openpyxl, compared for untouched member bytes, reparsed and chunked. These tools open only packaged trusted synthetic goldens; the CLI accepts no arbitrary source input. Production parsers retain all existing sandbox/kernel limits.

Each successful projection must match independent text/cell/style/table/formula/cache oracles and cover every extracted field exactly once with valid Unicode code-point intervals. Chunk text must match source slices or structured-row JSON. Row metadata, heading sections, stale cache/OCR review flags, private labels, identity hashes and byte/reply limits must survive. Missing/overlapping/forged spans, changed content/owner/digest or incomplete cases fail evaluation. Repeated chunk construction uses the same parsed view; live model output is not claimed deterministic. D22 HTTP tests remain the evidence for actual authorization, source mutation fences, cancellation and quota behavior.

Expected rejections must match stage, stable code and status exactly. Nested tables fail at adaptation422, atomic row overflow at chunking413, malformed PDF at verification415. Unexpected exceptions are sanitized and retain a fixed failed-stage code; remaining cases continue. Unexpected acceptance fails the gate. A scanned PDF's empty native text is an expected unsupported projection for recognition; explicit page OCR is separately measured.

Run from `ai/`:

```sh
uv run python -m scripts.document_pipeline_acceptance --include-vlm --output docs/evidence/d23-document-pipeline.json
```

The default output is ignored `benchmarks/results/d23-document-pipeline.json`. Without explicit VLM opt-in the required vision case is unrun, `complete=false`, `passed=false`, exit1. Full acceptance explicitly uses the existing loopback CORE, never starts/restarts services or silently calls a model for low-confidence OCR. Retained evidence records case/source/corpus hashes, parser/chunker checks, counts/coverage, safe failure codes, CER/WER/table matches and stage wall/resource measurements. It contains no source text/model output/images/private exceptions/credentials. Rewritten chunks use output SHA and a separate synthetic source identity, not a false association with original bytes.

`passed` means each declared case gate met its expectation; it does not mean every transcription was correct. `quality_failures` explicitly retains inaccurate recognition even when required uncertainty detection passes. The existing blurred fixture is unreadable by current English OCR: ground truth remains nonempty and CER/WER1.0 stays visible. VLM table accuracy measures one clean Vietnamese6-cell golden, not arbitrary-language/layout accuracy. Its confidence remains null and review required; its narrative text is not scored against invented ground truth. Source fields for narrative and table are distinct projections and can repeat semantics.

Stage wall time and child CPU are measured sequentially on this host. Child peak RSS is cumulative `RUSAGE_CHILDREN.ru_maxrss` in Linux KiB, not per-case memory or CORE GPU/model-server CPU. These are observations, not latency/load SLOs or new memory bounds. Parser resource/kernel enforcement is tested by existing regression. The report cannot certify arbitrary documents, production concurrency, embedding/tokenizer/retrieval quality, multilingual accuracy or off-host operation.

## Follow-up assessment

**Purpose:** Record priority/dependency/effort/risk before scheduling features suggested by known limits.

| Candidate | Priority / dependency | Initial effort / risk | Scheduling decision |
|---|---|---|---|
| Improve degraded/multilingual OCR | P2; representative multilingual/noisy corpus, uncertainty/routing policy and existing CORE budgets | 2–4 milestones; hallucination, latency/resource pressure and language-specific accuracy | Backlog after D32 acceptance unless a measured required corpus blocks earlier work; current mitigation is explicit OCR/VLM/manual review, no automatic repair |
| Split oversized structured rows | P2; D24 tokenizer/model limits, new chunker version/row-fragment span contract | 1–2 milestones; broken row semantics/IDs or lost cells | Assess after D24 measurements; preserve current413 contract until a separate scheduled scope/ADR |
| Support nested tables | P2; hierarchy/section/locator design and independent nested golden corpus | 1–3 milestones; overlapping source coverage and ambiguous order | Backlog after D32 unless required sooner; current422 is intentional and must not be relabeled data success |

No new feature is automatically added to the current milestone. D24 follows measured D23 acceptance and full Vault-backed PostgreSQL/CORE regression; its embedding/model/Qdrant design requires measured local tradeoffs and an ADR, reusing existing services. D23 evaluation itself introduces no embedding/index/context attachment or generated-output persistence.

## Observed local acceptance — 2026-10-18

**Purpose:** Record the final measured checkpoint without conflating gate acceptance with universal accuracy.

The retained report passed18/18 case gates:11 accepted content projections,3 empty,1 degraded and3 exact expected rejections;56/56 source fields covered,32 chunks/7 empty records. Actual CORE table6/6 exact cells, mandatory review/no calibrated confidence. Blurred OCR remains CER/WER1.0 in `quality_failures`, not transcription success. Sequential corpus wall time6401.331ms includes verification, parsing, independent reopening, chunk repeat and scoring; no load/SLO claim.

Final Vault-backed PostgreSQL/CORE regression: **748 passed in92.02s**, zero skips/exclusions (700 baseline +30 scorer/failure/CLI +18 corpus/live). Ruff correctness/import/format,40 definition descriptions across4 Python files, uv lock/diff and fixture/report hash/privacy checks pass. Post-test global file usage `(0,0,0)`, restore probes0; existing shared services remain running. No production file/config/schema/dependency changes or demonstrated supported-contract failures requiring repair. D23 PASS for this defined local scope; D24 selection/design remains NEXT.
