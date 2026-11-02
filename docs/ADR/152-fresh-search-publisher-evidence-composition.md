# ADR 152 - Fresh search and publisher evidence composition

Purpose: connect a newly executed research run to bounded fresh source acquisition without turning archived discovery or publisher children into direct search hits.

Date: 2026-11-03 (Asia/Ho_Chi_Minh). Status: Accepted for implementation and bounded evaluation under the owner's instruction; no measured acceptance or production/model/provider adoption.

## Assessment

P1 D60-FRESH-001 depends on the accepted ResearchService, PublisherEvidenceResolver, source-proof/report/export/session boundaries and the existing CORE/SearXNG-Brave configuration. The latest full5837 and preservation audit are retained baseline evidence. The missing composition is fresh research to selected sources: the earlier resolver regression starts from acknowledged archived discovery. Effort is one optional application composition, failure/authority/lifecycle tests, a frozen live workflow and coverage panel, then current-source regression/preservation. Risks are stale-result injection, URL/owner substitution, upstream refusal, extra fetches, raw-provider retention, numerical score relabeling and incomplete cancellation.

## Decision

Add an unregistered LivePublisherResearchService that accepts only an owner and explicit goal. It calls the borrowed ResearchService itself and accepts only a fully typed, fresh, complete same-owner/same-goal result within that invocation's UTC interval. It validates every query/source/attempt/hash and chooses the first actually returned member of each trusted source family in query/rank order. No archive/result argument, source override, guessed URL, alternate candidate after a failed fetch or provider retry is supported.

The initial trusted catalogue is SearXNG Search API and a configured RFC on RFC Editor. A direct result is acquired freshly; a publisher landing is resolved through its actual freshly observed anchor and retains both parent and child proofs. Route, query/source IDs, original search URL, final evidence URL, parent body/anchor binding and child-is-not-search-hit remain explicit. Restrict source HTTP hops to the same configured catalogue before transport; preserve original public DNS/TLS/body/redirect/source validation. Keep the prior direct-result evaluator and all first results byte-identical.

Keep existing research45/model15/provider10-second budgets and at most3queries/5results. The new acquisition composition has75seconds total, with30seconds for its fresh source phase; report/native publication remains a distinct90-second stage. Retain nonqueued admission until owned dependency cleanup joins, including repeated cancellation. Shutdown revokes owned source proofs and closes only this composition; it does not shut down borrowed search/model services. Raw query/title/snippet text stays in bounded memory; actual-provider archives use existing metadata-only projection, never the raw D59 discovery facade.

## Acceptance and rollout

Freeze implementation, corpus, budgets, exact source/claim/quote oracles and every invocation before live I/O. Require controlled direct/publisher positives, deep malformed/stale/foreign source denials, SSRF/redirect/metadata attacks and cancellation/busy/shutdown controls. Run one fresh CORE-planned Brave workflow through real sources, the unchanged three-claim assessment, native DOCX/PDF, proof-revoked archive reopening and every-page visual review. A distinct eight-query bilingual official-source coverage panel is specified before scoring. Preserve its first failures and the old failed direct-hit score; URL coverage is not semantic relevance or independently verified freshness. A provider refusal stops further live dispatch, without polling or bypass.

Require appropriate current-source full tests and independent preservation. No model, embedding, default route, provider/engine, Docker/Vault/database schema, existing data or production activation changes. Browser/runtime rights/security and production packaging/retention remain separate gates. Rollback omits the new composition and retains all old services/results and scoped archives.
