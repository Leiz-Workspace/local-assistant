# D60 web research phase gate

**Purpose:** Track actual end-to-end research/artifact acceptance and its remaining coverage, hostile-evidence, browser-runtime and regression prerequisites without promoting partial evidence to PASS.

**Date:** 2026-10-21. [ADR-079](ADR/079-web-research-phase-evaluation-and-observation.md). **D60 IN PROGRESS.** D59 remains accepted at5676a3d; all529 accepted source/config bytes are unchanged. New diagnostics are test/evaluation helpers only.

## T01 — Bounded observation and unchanged-corpus follow-up

The original D53 first result stays3/8 expected-primary URI presence@5, six/eight valid responses, two provider errors and three/four reference sources observed. These incomplete URI labels do not measure semantic relevance, precision/recall or independently verified freshness.

The separately frozen D60 follow-up repeats the exact original eight queries/four references once, through the same owned SearXNG/Brave engine and original strict adapter/pinned public source acquisition. Diagnostic wrappers forward original requests/headers/chunks/results unchanged, preserve actual cleanup and retain finite guard metadata and hashes only. No previously rejected response is accepted; no raw actual provider snippets/pages, error messages, traceback locals or proof keys are persisted. No provider/model/engine/config change, CAPTCHA/suspension bypass, fallback or hidden retry.

| Observation | First D53 | Distinct D60 follow-up |
|---|---:|---:|
| Queries attempted |8|8|
| Valid provider responses |6|1|
| Provider failures |2|7|
| Expected-primary presence@5 |3/8|1/8|
| Mean reciprocal primary rank |0.291667|0.125|
| Reference sources observed |3/4|3/4|
| Required literal RFC date declaration grounded |1/1|1/1|
| Independently verified freshness |Unknown|Unknown|

The follow-up takes4.244s. All seven error responses are HTTP200/JSON with empty results plus one declared upstream engine failure. The original unchanged decoder returns `searxng_upstream_unavailable`. Specific upstream cause is unknown: these observations do not establish CAPTCHA, rate limiting or engine suspension. A separate bounded readonly owned-container recent-log category scan examines37bytes and finds no matched exception category; raw logs are not retained. The original Python-English `searxng_response_invalid` is not reproduced and its historical underlying cause remains unknown. This worsened result cannot support broad phase-quality promotion.

The Python reference again fails before evidence issuance. A separately frozen **one additional declared source acquisition** retains finite exception types and known code-frame names, not raw messages/locals/page text: `web_fetch_internal` wraps `WebEvidenceError` raised by `evidence_metadata.source_dates` while feeding original HTML to its strict parser (line31, mapped atline58). The final inner type falls outside the predeclared whitelist and remains `other_exception`; no exact malformed token/charset or exception name is invented. Strict metadata parsing rejected this source representation. No `recover=True`, alternative parser, silent metadata omission or validation relaxation is introduced.

All observed original public DNS/pinned numeric TLS/SNI/CA/peer checks and socket closures pass. Evidence service keys/cache/tasks are retired. No model/browser calls; eight provider and four source attempts in the follow-up, one separately declared forensic source attempt, zero automatic retries. [Original-corpus freeze](evidence/d60-t01-diagnostics-freeze.json), [follow-up](evidence/d60-t01-first-diagnostics.json), [forensic freeze](evidence/d60-t01-forensic-freeze.json), [source exception metadata](evidence/d60-t01-python-forensic.json).

Initial diagnostic controls14 FAIL/two PASS/.14s because HTTPX `Response(content=...)` eagerly reads/closes the mock body before its stream can be observed. Full original source/test/log ZIP is preserved. Test-only `stream=ByteStream(...)` setup corrects the fixture to match an unread real transport response; adapter/observer/schema/oracles remain unchanged.16 corrected controls PASS/.10s,109 related source/provider/coverage controls PASS/.24s and three separate exception-context controls PASS. Four new Python evaluation/test files; original529 accepted source/config bytes unchanged. [First fixture failure](evidence/d60-t01-first-fixture-failure.json).

T01 readonly closure passes at533 source/config files: original V006/zero sources/memory/quota/vectors/probes/workers, owners/ACL/grants/triggers/models/config/dependencies, original14 containers plus SearXNG/CORE preserved; zero owned browser resources. This is diagnostic integrity acceptance, **not D60 phase/quality PASS**. [Readonly closure](evidence/d60-t01-readonly-audit.json).

## Remaining D60 gates

T02: freeze and execute broader bilingual/date and integrated hostile evidence→claim→report/export evaluation, retaining every raw-adherence/usefulness/permission outcome and same-agent labeling limits. T03: complete official current browser review, measure exact cached runtime compatibility/resources and record qualification/migration/rollback limits before any production promotion or runtime adoption. T04: run actual original CORE→selected SearXNG→tested public sources→signed report→native DOCX/PDF/durable archive, preserving unknowns and visually inspecting every final page. T05: full regression and final readonly audit. Required failures or incomplete evidence keep D60 open; no automatic D61 advance.

Rollback removes only new diagnostic helpers and closes trial-owned HTTP/source resources, retaining all original scores/errors/full-file archives and agreed models/provider/browser/API/Vault/database/services/data. No new package/image/model download or production activation is part of these diagnostics.
