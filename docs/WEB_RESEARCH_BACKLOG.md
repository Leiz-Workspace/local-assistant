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


## WEB-BROWSER-001 — Browser runtime freshness and compatibility review

**Purpose:** Assess the cached pinned tool runtime before broad production browsing without changing agreed models.

P1 before D60 production/phase promotion, after D50 functional isolation, D52 attacks and D53 coverage. Cached Browsertrix digest7f9d5e20... (created2026-08-20) contains Brave Origin149.1.91.175/Chrome149.0.7827.155; actual pinned-CDP compatibility does not certify current security patches or general website support. Estimate one official release/security/compatibility/resource comparison milestone; dependencies are frozen browser/coverage corpora and operator-compatible cache/disk budget. Risks: stale browser vulnerabilities, changing runtime after scores, breaking CDP/CSP/pipe/OS isolation, or broadening image/worker/frame/download permissions just to pass a site.

Review official current runtime/CVE/release sources, benchmark same frozen pages and policy/cancel/cleanup/resource gates, migration/rollback to exact previous tool image and ownership records, before any tool-runtime replacement. No model/account/service/key adoption is implied. D50 keeps a fixed cached offline image and defined local text-only scope; no current-security or production-readiness claim. Larger resources, images/fonts/media, iframes/workers, authenticated/stateful profiles and write/download actions remain unimplemented; evaluate need/priority/dependencies/effort/risks before scheduling.


## WEB-INJECT-001 — Broader integrated evidence-to-agent attack evaluation

**Purpose:** Prevent the limited same-agent D52 snippet/native cases and narrow JSON angle encoding from being promoted into general prompt-injection or full-page research safety.

P1 before D60 phase promotion, after D54 actual planner/full-page-evidence composition and existing D52/D53 boundaries. Estimate one frozen bilingual/multiturn hostile source/citation/date/cache/owner/action corpus with controlled native and actual CORE measurements; re-estimate after integration contract. Dependencies: explicit owner-authenticated source/tool context, budgeted research graph and complete first-score artifacts. Risks: overfitting eight visible snippets, treating schema rejection as usefulness, tokenizer-looking data across new serializers, forged metadata/claims/links and unsafe automatic tool routing. Keep fixture/AI judgments distinct from human-independent evaluation.

Reuse D52 original role-delimiter format failure as a mandatory regression, preserve first7/8 and distinct repaired8/8 without relabeling. Freeze new corpus/oracles before scoring; separately report raw adherence, app permission boundary and useful grounded responses. Review every new source-to-model serializer and tool URL/owner/policy selection; no implicit authority from title/date/canonical/cache/page text. No model change/download, permission expansion, secret access or actual public/private attack is authorized by this backlog entry.
