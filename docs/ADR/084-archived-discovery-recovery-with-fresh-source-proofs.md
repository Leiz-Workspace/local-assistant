# ADR-084 — Archived discovery recovery with fresh source proofs

**Purpose:** Complete researched artifacts through explicit durable discovery recovery while Brave is unavailable, without replacing the provider/models, fabricating results or reviving old source proofs.

**Date:** 2026-10-22. **Status:** Accepted for additive unwired implementation and measured qualification; implementation alone is not acceptance.

## Evidence and dependency

Current full4032 and final readonly audit PASS at540 unchanged source/config files. Repeated fresh-discovery trials correctly fail before source publication. Repeating them does not implement recovery. D59/ADR-078 already permits explicit paused-discovery resume with newly authenticated source spans; D60 used caller-designated references for its downstream diagnostic but never exercised actual retained search provenance.

The immutable original D53 actual Brave observation at09e790b retains search query IDs, UTC timestamps, result order/URLs and title/snippet hashes. Its searxng-en first hit is the SearXNG Search API; rfc-en first hit is `https://datatracker.ietf.org/doc/html/rfc9111`. That IETF page identifies RFC9111/HTTP Caching and links the RFC Editor edition. The original D53 URI labels intentionally recognized a narrower RFC Editor path, so its first3/8 score stays unchanged. A reviewed additional official source host is a new recovery qualification, not retrospective relabeling or arbitrary URL/canonical substitution.

## Decision

Add a bounded metadata-checkpoint importer and one explicit CORE query-selection service. Trusted composition pins complete archive/corpus SHA256 values from the accepted Git blobs, supplies a current owner and aware UTC clock, and explicitly permits the public technical observation corpus. The archive is not a private principal's history and is not automatically shared across authenticated owners. No caller-selected path, new provider request, fake SearchBatch/title/snippet, old HMAC proof or executable archive payload. Preserve all original query/error/empty/result rows and raw metadata bytes/hashes; raw original provider text was never retained and is not reconstructed.

Validate complete duplicate-free bounded metadata/corpus, every canonical query/ID/rank/HTTPS URL/hash/status/UTC binding, pinned complete bytes and owner on import and around model completion. Explicit metadata reuse horizon48hours is a host policy bound on discovery pointers, not verified freshness or a remote cache directive. Future/expired/corrupt/foreign/incomplete metadata refuses; retained files are never deleted/rewritten. The importer has no filesystem/network authority.

One fixed existing CORE fast/temperature0/max512 call selects1–3 IDs from the observed query catalog for the explicit goal; strict complete JSON/known IDs/status/no-duplicate validation precedes any fetch. The model receives bounded neutral JSON query metadata only, no URLs/provider snippets/private context/tools or endpoint/model/budget controls. Existing process-local quota/nonqueued admission/15s model/20s total/shielded joined cancellation/shutdown ownership apply. Checkpoint expiry/integrity is rechecked after inference. Record archived query times and complete provenance; current provider requests are exactlyzero.

Host selection requires both exact independently reviewed primary families in actual retained results: SearXNG API and RFC9111 on the IETF Datatracker HTML path (or the original exact RFC Editor HTML path when actually present). Other results remain recorded but cannot authorize source selection. Never invent the RFC Editor URL from an IETF/PDF result. Acquire the chosen original URLs anew through unchanged public DNS/numeric pin/TLS/SNI/CA/peer/redirect/source-size policy. Fresh D51 proofs/signatures/code-point quotes, unchanged three claims/expected labels/CORE max768/D57 signed report/D58 native export/D59 once-only archives and full all-page visual QA remain required. Search observation time and new source fetch time are separate; publication/semantic truth/freshness remain unverified.

The final report must explicitly say it resumes archived actual Brave discovery, include observation date/archive digest/selected query IDs, and state that no new provider request occurred. Preserve all permitted excerpts/claims/reasons/unknowns, full exported bytes and original failures. Reopen complete archives after live issuers retire; hashes do not revive authorization. No raw page/body/provider snippet, key or live receipt is archived.

## Qualification and phase accounting

This implements the intended durable branch of the researched-artifact acceptance: actual selected-provider discovery provenance→explicit CORE selection→fresh source proofs→report/native/archive, with the temporal boundary disclosed. It is distinct from both the failed same-invocation live-discovery experiment and the previous designated-reference-only diagnostic. All old first scores, errors and fresh-provider trial statuses stay immutable. No claim that Brave recovered, a cached observation is fresh, IETF was an original positive URI label, or a fixture is new search traffic.

D60 can qualify its local durable researched-artifact branch only after original semantic/ownership/source/quote/model/cleanup requirements, actual artifact/all-page review, appropriate regression and final readonly audit pass. Fresh upstream availability remains explicitly degraded/P1 WEB-SEARCH-003 and does not acquire a false PASS. This branch does not remove a semantic/source/owner oracle or authorize production adoption. Keep restricted browser review/production flags and all provider/model choices unchanged.

## Priority, risks and rollback

P1/current D60 recovery dependency; depends on accepted D53 observations, D54/D51/D57–D59 and fresh public access. Effort one metadata importer/query-selection lifecycle milestone plus controlled tamper/owner/expiry/plan/cancel tests, actual fresh-source/native/archive measurement, visual QA and regression. Risks: fake search provenance, treating hashes as signatures, private-history cross-owner leakage, stale pointers, post-score label changes, missing outcomes, unbounded retries and implying source freshness. Trusted local operator/UID and pinned accepted Git artifacts remain the provenance root, not independently signed remote attestation.

No model/package/image download, provider/engine/IP/header/cookie change, CAPTCHA/suspension workaround, Docker/Vault/database/API/config mutation or existing source change. Additive unwired code only. Runtime adoption later requires provider/result-use/retention/owner/storage rights and production qualification under WEB-SESSION-001. Rollback drains only new selection tasks and fresh trial-owned source/native/store handles, removes unwired recovery components, and retains all old archives/data/config/models/services. No migration/reindex or data deletion.

Primary identity reference: [IETF Datatracker RFC9111](https://datatracker.ietf.org/doc/html/rfc9111). Source observation provenance is the existing pinned local D53 record, not this documentation lookup.

## Measured qualification outcome

First actual recovery PASS5.213s/two newly acquired official sources/original3/3 labels/one selection CORE/one assessment CORE/one native batch/durable archive reopen and all3-page visual review.88 new controls/327 related PASS; distinct actual full4120 PASS/1712.84s/0FAIL/0SKIP/exit0,34 private audit controls and final readonly audit PASS545/all540 prior bytes preserved. The original day-level sourced-artifact goal is accepted within this explicit local durable recovery scope; D61 can begin. Original same-invocation fresh-search trials remain FAILED and fresh availability/reliability remains P1 before broad production. No original D53 score/label, model/provider/config/data or production restriction changed. [Acceptance](../evidence/d60-local-recovery-phase-acceptance.json).
