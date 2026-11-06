# ADR 088 Synchronize buffered source and native descriptor positions

**Purpose:** Repair reproduced native document handoff data loss without changing source bytes, parsers, models, resource limits or acceptance labels.

**Date:** 2026-10-22. **Status:** Accepted necessary narrow adapter repair after first D62 incomplete measurement and eight actual red regressions, before implementation.

## Evidence and affected boundaries

First D62 native/CORE paired run attempts16 modes but observes13; three searchable-PDF raster branches fail before model dispatch with ocr_processing_unavailable. The exact original PDF renders successfully with the same sandbox/512MiB/8–9CPU/32FD/8MiB output limits when passed directly to Poppler. A separate original-worker child diagnostic observes exit1/39-byte stderr whose complete digest matches the known empty-document-stream diagnostic. No raw stderr/page pixels are retained.

Independent local offset probe on the original sub8192-byte PDF demonstrates Python buffered read-ahead: after reading1byte, kernel offset is at the buffer end; `source.seek(0)` resets the logical buffer cursor but leaves the native descriptor offset at EOF. Handing `fileno()` to a subprocess therefore supplies an empty/partial stream. Seeking to end and then start clears the buffered read window and synchronizes the actual kernel position to0 on the supported Python runtime. No more RAM, renderer/model replacement or source recreation is needed.

Eight actual pre-repair red tests confirm this is broader than the observed internal Poppler handoff: valid preread BufferedReader sources fail full-byte/position equivalence through each of verifier, PDF extractor, DOCX processor, XLSX processor and page OCR; three small-PDF raster cases also fail inside the worker. Original source/raw outcomes/tests/logs retained before repair. Python-only PDF/ZIP readers inside other workers do not lend their own buffered source to another native child, so they do not require changes. Blob ownership/inode locks and pread-based integrity checks remain unchanged.

## Decision and qualification

Add one small shared native-input synchronization helper: seek0 from end, then seek0 from start, log finite metadata only. This preserves all bytes and invalidates buffered cursor state before lending and after reclaiming a native FD. It accepts existing seekable BinaryIO, adds no path/FD authority, does not reopen a path, change a lease, close the caller source or alter original input validation. Native codecs remain isolated.

Use this helper at the five parent adapters' existing pre-dispatch/finally rewind points and around the OCR worker's source-provided external renderer call. Keep data-provided Tesseract input unchanged. These six prior PASS files change only because each affected contract is now reproduced by real failing tests. No unrelated worker, parser, BlobReader, schema/owner checks, response lifecycle, limits, fonts, image pixels, model/prompt/options, source fixture or metric/oracle change.

P1/current D62 dependency; depends on existing native sandbox/source-lifetime contracts. Effort one shared helper/20 focused native-position cases plus relevant full document/ownership regression, distinct same-corpus first repaired quality measurement, fresh full suite and final readonly audit. Risks: failing to flush/invalidate both stream states, closing a borrowed FD, changing write-buffer semantics, masking malformed content, missing exception cleanup or accidentally widening the sandbox. Test raw/BufferedReader/BufferedRandom/BytesIO/closed/error cases, exact complete source bytes and final Python/kernel position, every native adapter and original small-PDF raster cases. Preserve original eight red failures/first13of16 observation and all OCR errors; no silent retry or post-score label revision.

Rollback drains only owned native jobs, restores all six exact original files from the retained complete ZIP and removes the new helper after callers retire. It retains models/config/data/collections/services and every first result. Original resource limits/privacy/model choices remain; no Docker/Vault/database/API/dependency/download change. A distinct repaired source/oracle freeze and actual regression results are required before D62 completion.
