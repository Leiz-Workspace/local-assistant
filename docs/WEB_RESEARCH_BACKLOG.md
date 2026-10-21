# Web research dependencies and backlog

**Purpose:** Assess web research prerequisites before scheduling or activating new capabilities.

## WEB-ONBOARD-001 — Actual search provider/account

| Field | Assessment |
|---|---|
| Status | **COMPLETE within D47 local scope:** owner chose self-hosted SearXNG; actual provider/CORE/citation and1541 related gates pass. Historical no-account discovery remains true; commercial key is unnecessary for selected anonymous website engine. |
| Priority | P1, required before D47 live acceptance and D48 API activation. |
| Scope | Identify the operator-owned provider and actual plan; verify quota/payment/query retention/result-use rights, then supply its credential through an approved secret path and run bounded live acceptance. |
| Existing independent work | Provider-neutral search/CORE contract, inactive Brave reference adapter and controlled HTTP/actual CORE fixture tests under [ADR-064](ADR/064-search-provider-boundary-and-existing-core.md). This is implementation readiness, not account adoption. |
| Dependencies | Owner account/contract decision; valid provider credential/endpoint; reviewed least-privilege secret storage plan before any Vault write. Internal API/Vault operator credentials are not search credentials. |
| Initial effort | One operator account/terms/credential setup plus one bounded live verification gate; elapsed time and account fees unknown. Re-estimate after provider selection. |
| Risks | Unexpected paid usage, disclosing private queries, retaining restricted results, using an unrelated secret, accepting blanket zero-retention claims or mislabeling mocked HTTP as live search. |
| Activation | No signup/purchase/payment acceptance, Vault write, production API wiring or provider fallback is performed by this backlog item. No actual provider budget has been authorized. |
| Acceptance | Record actual plan/provider/terms/quota/privacy decision and credential provenance without values; make a bounded explicit public query, validate status/shape/citations/cleanup and retain real outcomes/usage without storing restricted raw results. Failures remain retained; no synthetic substitution. |
| Rollback | Disable and drain the later search adapter; preserve original models/config/data. No migration/reindex needed for the current unwired implementation. |

Brave REST API remains an inactive credential-requiring reference; Tavily remains a candidate. The selected provider is an owned SearXNG instance using its anonymous Brave website engine, with no new model. [Actual acceptance/failures/limits](D47_SEARXNG_LIVE_ACCEPTANCE.md) supersedes the historical pre-provider gate. D48–D60 remain sequenced by roadmap criteria.


## WEB-EVAL-001 — Broader freshness, coverage and upstream resilience

**Purpose:** Prevent a single visible provider smoke query from being promoted into broad research quality.

P1 before phase D60 release; scheduled at existing D53 after D48 API/rate limits, D49 fetch, D51 provenance and D52 attack gates. Estimate one frozen bilingual/cross-language query-and-source evaluation milestone; re-estimate after corpus design. Risks: overfitting the D47 visible query, changing engine/query/thresholds after scores, variable HTML/rate limits/CAPTCHA, stale/irrelevant snippets, unsupported storage rights and mislabeling source binding as semantic entailment.

Freeze complete queries/labels/settings/resource budgets and failure/refusal oracles before scoring; retain every first outcome and source/config lineage. D47's initial irrelevant-source CORE refusal and Google unavailable case remain mandatory regressions. The Mwmbl/Brave two-engine panel is only one-query connectivity/readiness evidence, not a general ranking winner. Do not clear/bypass upstream CAPTCHA/suspension, rotate public instances, download a model or infer permission to switch agreed models. Produce explicit freshness/coverage/partial-upstream/latency/resource evidence and rollback analysis before promotion.
