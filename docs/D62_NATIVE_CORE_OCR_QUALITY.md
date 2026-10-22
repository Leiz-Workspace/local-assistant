# D62 native first OCR and CORE VLM quality evaluation

**Purpose:** Report measured native/CORE text/grid/uncertainty/absence/latency/resource tradeoffs with unchanged model selection and every first failure retained.

**Date:** 2026-10-22. **Status:** Actual paired quality observation complete; D62 IN PROGRESS pending full4265 and final readonly audit. [ADR-087](ADR/087-native-ocr-and-existing-core-quality-evaluation.md), [necessary FD repair ADR-088](ADR/088-synchronized-buffered-source-native-fd-handoff.md).

## Existing model and scope

Native PDF parsing first and explicit CORE Qwen3.5-9B/mmproj remain the registry strategy. Native Tesseract remains English-only. No OCR/VLM alternative, package, model, font, service, Docker/Vault/database/API/config or resource limit was changed/downloaded. The only necessary accepted-code changes synchronize buffered/native input positions at six proven failing adapters; all other550 prior source/config bytes remain unchanged/current562. No broad production or general OCR/VLM accuracy claim.

## First errors and necessary repair

First paired observation attempts16 modes and obtains13: searchable-PDF raster branches fail before model dispatch. Independent Poppler runs with the same original limits succeed; original-worker finite child metadata identifies an empty input stream. The1565-byte PDF probe shows logical cursor0 with kernel cursor1565 after an ordinary buffered rewind. End-then-start synchronization sets both0. Eight real regressions reproduce all five parent adapters and three internal small-PDF raster cases; original source/tests/output/logs preserved in completeZIP b267f294f8b66e366fd302628ea9d2eb36b9fed9fe0854b08b9429ea451f84d4. No old score or fixture changed.

The shared helper changes only pre/post source rewinds in verifier/PDF/DOCX/XLSX/OCR and the OCR child handoff. No codec, parser, model, language pack, limits or source pixels change.20 new real/native-position cases PASS/4.20s;361 related PASS/28.17s/0FAIL/0SKIP.20 independent quality metric controls and12 private evaluator/resource-parser controls are included in that related set. Native PDF page1 was also visually checked through an in-memory normalized render; original ASCII readable, no raster file retained.

## Distinct repaired first run

Same eight source/page/case labels/scorer/model/options, one attempt per mode.16/16 observations complete/18.772s, eight CORE OCR calls, two distinct missing-field image questions and one ordinary-text recovery completion. All model transports and QA operations/admission retire. This is an observation-complete evaluation, not a claim that all OCR text is correct.

| Authored case | Native CER / WER | CORE CER / WER | Native seconds | CORE seconds |
|---|---:|---:|---:|---:|
| native-pdf-ascii | 0.000000 / 0.000000 | 0.000000 / 0.000000 | 0.165 | 3.838 |
| native-pdf-empty | 0.000000 / 0.000000 | 0.000000 / 0.000000 | 0.465 | 3.140 |
| clean-english-image | 0.000000 / 0.000000 | 0.000000 / 0.000000 | 0.315 | 0.892 |
| scanned-english-page | 0.000000 / 0.000000 | 0.000000 / 0.000000 | 0.515 | 1.055 |
| scanned-blank-page | 0.000000 / 0.000000 | 0.000000 / 0.000000 | 0.415 | 0.774 |
| blank-image | 0.000000 / 0.000000 | 0.000000 / 0.000000 | 0.265 | 0.625 |
| blurred-latent-text | 1.000000 / 1.000000 | 0.285714 / 0.500000 | 0.265 | 0.886 |
| vietnamese-table | 0.250000 / 0.750000 | 0.000000 / 0.000000 | 0.315 | 1.583 |

Native PDF/clean English/scan text are exact in these visible examples. Vietnamese native OCR has CER.25/WER.75 and raw engine score82.772 with review/English-only flags; no native table grid was inferred. CORE preserves the exact six table cells/row order, CER/WER0 on this one table. Blurred native text has CER/WER1.0; CORE still has CER.285714/WER.5 and signals uncertainty. Preserve both errors; unreadable text is not scored as perfect blank output.

All three known authored blank cases produce empty text in both modes;0 observed blank false-positive transcriptions. Both new absent due-date/unit-price questions abstain with uncertainties and pass the narrow predeclared absence gate. These are same-agent/visible labels, not independent semantic certification. Native scores are uncalibrated; CORE confidence remains null and review always required. Complete original public authored outputs/text/tables/uncertainties are retained separately for audit; no raw raster/full model request body or private user content is archived.

## Resource points and latency limits

Across32 before/after points, existing CORE process RSS RAM is 9426.879–9763.918MiB and its NVIDIA compute allocation VRAM is 9234.000–9380.000MiB. These are separate quantities. RSS can include mapped/shared file pages and is not unique/private RAM requirement; GPU allocation includes model/KV/workspace, not just weights. Neither series is a workload peak or required minimum.

The original CORE stays resident even during native OCR, so its existing GPU allocation is not native OCR cost. Native worker512MiB is an address-space limit, not measured RSS; native worker RSS was not sampled. Latencies include each mode preparation and inference but exclude the separate before/after resource query; original D21 cache behavior/warm sequential process remains. No cold-start, paired alternative-model efficiency or OOM/SLO claim. D67 retains broader resource/context/load measurement.

## Current closure and next dependency

Original first13/16 and every error/quality discrepancy remain immutable. A fresh full4265 application invocation is now running with accepted in-memory readonly Vault paths/live flags and redacted durable logs; previous full4120 remains a separate545-source cohort. Do not mark D62 complete or start D63 from quality output alone. Final full/frozen source/model/data/runtime audit is required after the six necessary shared adapter changes. Optional dedicated OCR/Qwen3-VL remains MODEL-EVAL-006 candidate-only; this tiny corpus does not justify a replacement and none is selected.

[First result](evidence/d62-first-quality-incomplete-result.json), [FD diagnosis](evidence/d62-native-fd-diagnosis.json), [preservation](evidence/d62-native-fd-first-failure-preservation.json), [repaired freeze](evidence/d62-native-core-quality-repaired-freeze.json), [actual measured output](evidence/d62-repaired-native-core-quality-result.json), [full4265 freeze](evidence/d62-4265-full-freeze.json).
