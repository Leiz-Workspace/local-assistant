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

P1 before D60 phase promotion, after D54 actual planner plus later full-page/evidence composition and existing D52/D53 boundaries. Estimate one frozen bilingual/multiturn hostile source/citation/date/cache/owner/action corpus with controlled native and actual CORE measurements; re-estimate after integration contract. Dependencies: explicit owner-authenticated source/tool context, budgeted research graph and complete first-score artifacts. Risks: overfitting eight visible snippets, treating schema rejection as usefulness, tokenizer-looking data across new serializers, forged metadata/claims/links and unsafe automatic tool routing. Keep fixture/AI judgments distinct from human-independent evaluation.

Reuse D52 original role-delimiter format failure as a mandatory regression, preserve first7/8 and distinct repaired8/8 without relabeling. Freeze new corpus/oracles before scoring; separately report raw adherence, app permission boundary and useful grounded responses. Review every new source-to-model serializer and tool URL/owner/policy selection; no implicit authority from title/date/canonical/cache/page text. No model change/download, permission expansion, secret access or actual public/private attack is authorized by this backlog entry.


## WEB-EVAL-002 — First D53 upstream/source gaps

**Purpose:** Diagnose measured low expected-primary coverage and opaque first failures before broad research promotion.

P1 before D60, depends on frozen D53 corpus/first outcomes and D54 bounded planner error handling. First selected-provider measurement6/8 valid responses,3/8 expected-primary presence@5; Python-English searxng_response_invalid and CDP-Vietnamese searxng_upstream_unavailable retained. Three/four reference sources observed; Python reference fails evidence_source_failed, underlying cause not established. Verified freshness remains null; RFC June2022 declaration quote is grounded, not independently verified publication truth.

Estimate one bounded metadata-only provider/wire/parser diagnostic plus a separately frozen same-corpus follow-up and broader dated-source corpus; re-estimate after finite failure causes. Risks: treating alternate relevant URLs as irrelevant from incomplete labels, changing labels/settings after scores, storing restricted snippets, bypassing CAPTCHA/suspension/validation, automatic retries/fallback, or overstating language/rank/freshness from tiny samples. Diagnose only finite status/shape/length/codec/guard reasons in memory, retain metadata hashes and first outcomes; no raw restricted provider/page persistence. No provider/model/config/permission change or quality promotion is authorized here.


## WEB-EXPORT-001 — Production packaging and runtime qualification

**Purpose:** Qualify the D58 native document toolchain before production API adoption.

P1 before production export wiring, after D58 local export and D59 lifecycle/recovery gates. Estimate one packaging/font/runtime qualification and rollback milestone. Dependencies: an explicit reviewed production dependency/runtime contract, frozen multilingual/layout/native-cancel corpus and operator resource budget. Current local export requires the existing development python-docx dependency and installed Office/fonts/Poppler/bubblewrap; D58 does not install or promote dependencies. Risks: missing development-only package, font/version layout drift, Office security maintenance, unavailable namespace support and mistaking per-process limits for aggregate memory enforcement.

Freeze versions and same input/output/visual/ownership/security oracles before any packaging/runtime change; measure latency/resources/cleanup and complete rendered pages, define migration/rollback to exact accepted local inputs. Refuse unavailable dependencies; no automatic downloads, model/service/config/dependency change or production activation is authorized by this item. D58 remains unwired within its measured local scope.


### WEB-BROWSER-001 — D60-T03 review outcome (2026-10-21)

Official release/security scope review complete, **no new runtime adopted/current-security or broad production approval**. Cached Chrome149.0.7827.155/Brave Origin149.1.91.175 is older than official Brave Latestv1.97.59/Chromium155.0.8059.85 (2026-10-16); standalone crawlerv1.15.0 release notes include Brave1.96.60. GitHub's newer Releasev1.98.60/Chromium156 build is marked Pre-release and was not treated as stable. The standalone crawler security page lists no advisories; that absence does not prove security. Browsertrix backend GHSA-47vv-v544-r985 is a different product/scope. Chrome-blog anti-bot/429 and inaccessible Brave website notes were not bypassed; official GitHub tagged/latest sources were used.

Original cached13 native controls PASS/12.42s and one blank network-none probe PASS/5.702s, three Docker point samples166–166.9MiB RAM container/97PIDs, fixed1GiB/1CPU/256PID/noGPU limits and exact cleanup. These are idle point samples, not workload peaks, model RAM/VRAM, SLO or candidate comparison. Keep local authored/blank compatibility scope/default-off production flags and native-sandbox limitation. D60 live source gate uses unchanged static public acquisition.

P1 runtime qualification remains required before broad production dynamic browsing: select/verify an immutable candidate, official security/native-sandbox review, same frozen CDP/pipe/site/attack/cancel/cleanup corpus and measured latency/resources, then explicit migration/rollback to exact original digest/config/source. Estimate one qualification milestone after candidate/cache/disk/ownership prerequisites. Risks include stale candidate browser, CDP/layout drift, losing cleanup ownership and permission expansion; no automatic image/model/package/service adoption. [Review/evidence](evidence/d60-t03-browser-review.json).
