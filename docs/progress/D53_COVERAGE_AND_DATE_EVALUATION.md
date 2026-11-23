# D53 first search coverage and source-date evaluation

**Purpose:** Record the frozen first selected-provider measurement, missing coverage and date uncertainty without inventing freshness, changing source labels or adopting another model/provider.

**Date:** 2026-10-21 (Asia/Ho_Chi_Minh). **Evaluation execution complete; broad quality/freshness not established.** [ADR-072](../ADR/072-frozen-search-coverage-and-date-evaluation.md), [first outcomes](../evidence/d53-first-coverage-observations.json), [freeze](../evidence/d53-coverage-freeze.json).

Eight fixed questions cover four official-documentation topics in English/Vietnamese: SearXNG JSON API, Python urljoin security, RFC9111 cache/publication declaration and DevTools download policy. Four fixed primary references were chosen before requests. Labels identify exact known URI families, not complete semantic relevance judgments. Query order/settings/oracles stay unchanged after scores. Selected owned SearXNG/singleton Brave website engine only; maxfive results, one call per question, no CORE/model/browser or fallback/retry.

| First measurement | Actual result |
|---|---:|
| Provider calls / valid responses / errors |8 /6 /2|
| Expected-primary URI presence@5 |3/8 (37.5%)|
| Mean reciprocal expected-primary rank |0.291667|
| English / Vietnamese primary presence |1/4 /2/4|
| Predeclared primary acquisitions / observed / failed |4 /3 /1|
| Actual original DNS/TLS connections, closed afterward |4 /4|
| Required literal date declarations / grounded exact spans |1 /1|
| Independently verified publication/freshness |Unknown/null|
| Total scripted measurement |9.113s|

Language/rank/elapsed values are descriptive on this visible same-agent small corpus, not comparative quality, semantic precision/recall/nDCG, statistical superiority or SLO evidence. Failed queries remain in denominators.

Python-English returns `searxng_response_invalid`; CDP-Vietnamese returns `searxng_upstream_unavailable`. The Python primary-reference acquisition returns `evidence_source_failed`; its underlying cause is not established. No CAPTCHA/timeout/HTTP-status explanation is invented. All first errors remain; no engine changes, arbitrary returned-URL fetch, source substitution, validation relaxation or post-score label changes.

The four independently selected references use unchanged D49/D51 system DNS/public pin/numeric TLS/original SNI/system CA/actual peer. Every native socket FD closes. Successful snapshots retain actual final URL/title/body/text/resource hashes and host UTC fetch time; absent page publication metadata stays unknown. RFC9111's predeclared [June2022 declaration](https://www.rfc-editor.org/rfc/rfc9111.html) binds to a genuine issued source span/hash/fetch-time record. This proves a quoted date declaration, not independent publication truth or recency of all search results. HTTP Date, fetch time, title version strings and cache age never become publication dates.

Raw provider titles/snippets, HTML/text and proof key are not persisted; result URLs and metadata hashes are retained. Service/cache/operations/proof key are closed/cleared. No model, browser, Vault/database change, provider/model comparison, production flag or existing service restart.

23 new controlled URI/date/hash/denominator cases included in2187 related PASS/141.80s/0SKIP/exit0. Two evaluated Python files/11 described functions/classes/isolated Ruff correctness/import/format pass.493 source/config/1049 unique current protected hashes match; all490 accepted D52 bytes unchanged. Its fresh3534 full remains historical/source-verified; no new full claim. [Related](../evidence/d53-related-regression.json), [quality](../evidence/d53-source-quality.json), [readonly audit](../evidence/d53-final-readonly-audit.json).

The evaluation delivery is complete because every declared attempt, error, metric denominator and date/source/cleanup outcome is retained and actual evidence gates pass. **3/8 coverage and null freshness are not a broad research-quality PASS.** [WEB-EVAL-002](WEB_RESEARCH_BACKLOG.md) requires bounded metadata-only diagnosis and separate frozen follow-up before D60; WEB-EVAL-001's broader corpus requirement remains. D54 must preserve partial/failed source states and unknown dates rather than filling them with model guesses. Rollback removes only evaluator artifacts; accepted provider/models/config/data/services remain intact.
