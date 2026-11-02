# Web research dependencies and backlog

**Purpose:** Assess web research prerequisites before scheduling or activating new capabilities.

**Current disposition — 2026-11-03:** D60fresh report3/3and unchanged750-source full5889remain VERIFIED. Brave website rate limiting now proven by exact responseSHA/length; new30-second panel1/8andpost-effective-cooldown panel0/8failed, original4/8retained. [Diagnosis and dependency](D60_BRAVE_RATE_LIMIT_RESULT.md). Four new calls/no retries/no models; fresh preservation VERIFIED. OfficialAPIevaluation is PROPOSED in ADR153, pending owner route/account/credential decision; no default/provider change.

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


## WEB-SESSION-001 — Live provider session retention policy

**Purpose:** Qualify actual provider result retention before production adoption of the D59 full-data session facade.

P1 before live-provider session API adoption; depends on provider/result-use rights, operator storage/data classification and D59/D60 frozen ownership/recovery corpus. Estimate one minimization/retention adapter and qualification milestone after policy review. D59 acceptance used authored data and its facade archives complete D54 query/title/snippet results. D60 actual evaluation instead composes existing services/private store with explicitly labeled metadata-only discovery records under ADR-080; restricted raw provider titles/snippets stay ephemeral, exact allowed primary excerpts/reports/export bytes remain complete. Do not claim that hashes preserve retrievable excluded raw content.

Evaluate explicit principal access/encryption/audit/deletion/retention, contract compatibility and bounded restart/error semantics before runtime reuse. Risks: unwanted restricted/private query/result retention, treating hashes as original data, data loss from silent redaction and confusing test-only composition with production lifecycle acceptance. No provider/model/service/Vault/database/dependency change or activation is authorized by this entry; rollback drains only a future adapter and retains existing data/receipts/services under the reviewed policy. [ADR-080](ADR/080-metadata-only-live-discovery-archive.md).


## WEB-SEARCH-003 — Declared upstream rate limit and discovery reliability

**Purpose:** Resolve the observed D60 live-discovery outage before claiming reliable phase promotion.

P1; current D60 dependency. First actual live attempt fails before source/report/native work because all three selected-provider queries return empty results with a declared engine error. A separately frozen one-query diagnostic classifies the current declaration as rate_limit_declared; exact upstream HTTP status/Retry-After/remaining duration are not independently observed. Pinned SearXNG81371861... defaults differ from general documentation and are not a remote quota promise.

Keep the existing owned SearXNG/Brave configuration, logging/privacy/metrics/cooldown, models and first failures. Permit one separately identified same-oracle follow-up only after full regression completes successfully and this evaluator has sent no search queries for at least1800s. This interval is an explicit conservative evaluation condition, not a verified remote Retry-After. No polling/retry loop, suspension reset, proxy/IP/public-instance rotation, CAPTCHA bypass, caller-designated source fallback or post-score label changes. If still unavailable, retain the failed gate and assess an alternative explicitly rather than claiming D60 PASS.

Alternative engine evaluation depends on actual result-use/privacy rights and fixed source/response/budget/cleanup oracles. Estimate one zero-model frozen provider compatibility/coverage/latency/resource panel plus reviewed migration/rollback before adoption. Risks: silently bypassing a provider restriction, declaring anonymous website scraping equivalent to a licensed API, incomplete primary coverage, unsupported language/region/safe-search/time-range features, introducing a paid account or breaking strict whole-response validation. Official SearXNG [Mwmbl engine docs](https://docs.searxng.org/dev/engines/online/mwmbl.html) describe a small-index engine without those filtering features; it is an unqualified candidate, not an automatic equivalent replacement. Mwmbl's crawling-key rules do not themselves establish search API permission or quality.

No alternative endpoint/engine/account/container/config/model adoption is performed by this item. Any later candidate must retain original selected-provider artifacts and explicit rollback, keep all model choices unchanged, and report every first score/refusal/error. Original D53 first3/8/T01 follow-up1/8 and D60 first live failure remain immutable.


### WEB-SEARCH-003 — 2026-10-22 measured checkpoint

The permitted one quiet-period same-oracle follow-up executed and failed before source acquisition. Both original-provider cohorts remain immutable. The one ADR-081 isolated independent Mwmbl candidate executes8/8 valid strict responses but0/8 expected-primary hits and lacks both required live source families; unqualified/no adoption,19 controls and exact owned resource/key retirement confirmed. Preserve original configuration; do not repeat provider/candidate loops or fabricate direct-reference search hits. Search-discovered source→report/native/archive remains the D60 blocker. PriorityP1, dependency compliant reliable selected-provider discovery or a separately reviewed/qualified provider proposal, effort one focused diagnosis/qualification milestone, risks availability/coverage/usage rights/feature gaps/data retention and false PASS. Existing model choices stay unchanged.

## WEB-OPS-001 — Postboot credential availability and final audit

**Purpose:** Restore operator-approved Vault availability after observed host reboot before completing the D60 readonly audit.

P1/current D60 dependency; TLS-verified health503/initialized=true/sealed=true. Existing15 container identities/images/ports/security remain intact; original starts changed. Same cached CORE restored without a model/config/download/startup-service change. Partial readonly source/V006/count/quota/security checks pass; Vault-backed narrow application grants/triggers, authenticated Qdrant and final workers/locks remain pending. Previous-boot full4018/audit retained separately.

Depends on operator Vault unseal/recovery through the established protected bootstrap procedure, then exact same readonly checks; estimate one operations recovery/audit step. Do not output bootstrap material, rotate credentials, write secrets, change seal/storage/startup architecture, bypass authentication or mark audit PASS from partial SQL checks. Risks bootstrap disclosure, unintended credential drift and confusing historical full evidence with current boot. Rollback preserves all config/secrets/data/accepted models and retained failures; no new auto-unseal service or architecture change is scheduled. [Partial audit](evidence/d60-postboot-readonly-audit.json), [health](evidence/d60-postboot-vault-health.json).


### WEB-SEARCH-003 — Bounded spacing experiment scheduled before implementation

P1/current D60 dependency; original recovery trial first query returns actual required SearXNG URLs, next two fail upstream, but exact cause/remote threshold remains unproven. ADR-082 assesses one evaluator-only5second minimum between actual backend starts and stop-after-first-error, with nonqueued/cancel/clock/error controls and unchanged original45/15/10second deadlines. Effort one small wrapper/test/frozen measurement; no production adoption, automatic retry/engine loop/model/config/label changes or inferred usage right. Preserve distinct actual-backend versus admitted/blocked-port counts and all original failures. Any further runtime adoption remains separately qualified; another live failure stops the experiment.


### WEB-OPS-001 — Completed existing runtime recovery

2026-10-22: existing initialized/sealed local Vault unsealed via original helper after8 controlled tests; protected bootstrap/env/CA bytes/inodes/modes unchanged. Only original unseal requests, no init/rekey/secret/policy/audit-device/config or architecture change. HTTPS health200/unsealed. Distinct complete same-boot audits PASS538 then540 source files/original data/models/ACL/grants/triggers/15 service identities preserved. Prior503/PARTIAL snapshot remains historical. This dependency is complete; no auto-unseal daemon is added. [Recovery](evidence/d60-existing-vault-unseal-result.json), [final audit](evidence/d60-spaced-final-readonly-audit.json).

### WEB-SEARCH-003 — Current remaining dependency

Operator-requested recovery run finds actual SearXNG sources but no required RFC family; no downstream fallback. ADR-082 evaluator14 cases/104 related PASS; first spaced live run fails after one backend request, stops two remaining backend dispatches. Live spacing not exercised/causal benefit unknown; failed gate remains failed. No more trial loops. [ADR-083](ADR/083-next-search-upstream-qualification-proposal.md) is a concrete unexecuted proposal for one Bing-only isolated qualification if the operator selects that path; it requires current usage/retention review and unchanged source/corpus/model/guard/resource/cleanup criteria before any startup/query. Preserve original provider/model/config/defaults and exact rollback; no measured candidate quality or adoption is claimed. P1, dependency compliant reliable actual source discovery, effort one isolated panel then conditional end-to-end gate, risks upstream restrictions/coverage/rights/filtering/parser/selection bias.


### WEB-SEARCH-003 — Operator selection: retain Brave and wait

2026-10-22: operator explicitly chooses existing Brave while waiting for upstream recovery. Status WAITING FOR UPSTREAM; remains the required D60 dependency. ADR-083 Bing qualification is DEFERRED, not scheduled; do not start another engine candidate, change the selected provider/model/config, or create polling/retry/background-monitoring jobs. Keep every failed cohort and unknown recovery/Retry-After unchanged. A bounded new verification requires an operator recovery report or explicit new-verification request; no automatic repeat based on time. D60 remains IN PROGRESS, no D61 advance. WEB-OPS-001 stays complete.


### WEB-SEARCH-003 — New explicit continuation, no provider change

2026-10-22: latest user continuation permits one separately frozen bounded Brave verification after≥1800s quiet. It remains FAILED:one actual upstream error/two backend dispatches blocked/0source-report-native. No recurring requests or Bing evaluation; ADR-083 stays deferred. Complete the independent missing current-boot full4032 regression/final readonly closure while preserving exact540 source bytes. A running full or old direct-reference artifact cannot satisfy the actual searched-source gate.


### WEB-SEARCH-003 — Current full regression prerequisite complete

2026-10-22: independent fresh full4032 PASS/1685.93s/0FAIL/0SKIP/exit0 and final post-verification readonly audit PASS540 source/config/all agreed models/data/services/security preserved. Final foreground Brave verification after≥1800s evaluator silence still fails before sources/report/native:one actual backend/two blocked,1.237s. No actual multi-start interval or causal pacing benefit measured; no further probe in this continuation. Preserve every cohort and exact source/claim/model/family oracles. Retain Brave/wait as selected; ADR-083 deferred, no alternate engine or automatic polling/retry schedule/D61 advancement. Only the actual searched-source report/native/archive/visual gate remains required; successful tests or direct-reference reports do not replace it. [Current combined status](evidence/d60-current-regression-and-upstream-status.json).


## WEB-RECOVERY-001 — Explicit archived discovery with fresh source proofs

**Purpose:** Exercise D59's intended paused-discovery recovery instead of repeating unavailable fresh searches.

P1/current D60 dependency; scheduled under ADR-084 before implementation. Original actual D53 Brave metadata contains SearXNG API and IETF Datatracker RFC9111 URLs. Keep original3/8 URI labels/failures unchanged. Dependencies: pinned complete accepted metadata/corpus, current owner/UTC, bounded CORE selection and original source/signature/report/export/session boundaries. Effort one narrow importer/planner plus tamper/owner/expiry/cancel controls, actual fresh-source/native/archive/visual gate and regression. Risks: fake/cross-owner provenance, stale pointers or falsely claiming current live provider/freshness. Preserve original metadata, search timestamps and all outcomes, reread selected actual URLs freshly; zero new provider calls, no direct-reference synthetic search result or old-proof revival. No model/provider/config/data/service change; rollback removes additive unwired recovery code and closes only owned handles, retaining every archive.

WEB-RECOVERY-001 measured checkpoint2026-10-22:88 new/327 related controls PASS/0SKIP; first actual archived-Brave→fresh official sources→unchanged3/3 assessment→native DOCX/PDF→archive reopen PASS5.213s, all3 pages visually reviewed. Current provider requests0; full4120/final audit pending, no production adoption or new live availability claim. All540 prior bytes unchanged/current545. WEB-SEARCH-003 remains degraded for new live discovery; preserve Brave/operator decision and every first failure.

D61 design preparation only: [inspected existing native image/CORE boundaries and proposed acceptance](D61_NATIVE_VISION_DESIGN.md). No D61 code/sample/acceptance or advance while D60 full4120/final audit remains pending. Existing D21 OCR/text adapters and all selected models remain unchanged.

WEB-RECOVERY-001 **COMPLETE within local D60 scope**: distinct full4120 PASS/1712.84s/0FAIL/0SKIP,34 audit controls/final readonly audit PASS545/all540 prior bytes unchanged. The actual sourced-artifact recovery acceptance is complete under ADR-084; fresh-query availability/reliability remains degraded in WEB-SEARCH-003 before broad production, not a prerequisite silently claimed to have recovered. Original first scores/failures/Brave/model choices and all production restrictions remain. D61 NEXT after this measured closure.

## WEB-SEARCH-003 — 2026-10-24 explicit outstanding-work follow-up

The owner's new request authorizes bounded current verification; Brave remains selected, ADR083Bing stays deferred/no polling. [Actual observations](WEB_SEARCH_003_CURRENT_CHECK.md): one-query check accepted, subsequent three-query direct-result E2E FAILED `live_missing_primary_sources` because the actual RFC hit is an official landing page. No new broad upstream reliability claim. Four accepted searches overall; original failures remain immutable.

ADR131separately assesses P1observed-publisher-link follow-up: acknowledged actual discovery/owner/run/hash→fresh officiallanding→actually observedhref→fresh twoevidence documents→oneCOREassessment→nativeDOCX/PDF→archive reopen afterproofrevocation→all3pagesvisualPASS. Zero additional search/plannerrequests, originalclaim/status/quoteoraclesunchanged. First128KiBparser-size failure retained; isolated corrected1MiBparser uses the unchanged original transport ceiling,46parser/archivecontrolsPASS. Complete optional research operator/tests delivered, not registered in production/API. Effort one bounded compatibility/evidence milestone, complete. No model/provider/default/config/data changes.

Broad WEB-SEARCH-003 remains P1before promotion: direct-result contract stillfails for this genuine publisher-landing case; handling integration, coverage/freshness/reliability/browser/security/retention/rights need scoped product evidence. Existing source guards prohibit inventing a direct hit; production integration must preserve explicit lineage/freshproofs/deadlines and get ADR impact/test review. Risks external markup drift/extra latency/SSRForigin confusion/archive-as-liveproof/overfitting. No further provider trial or integration campaign automatically scheduled.


## WEB-SEARCH-004 first failure and bounded correction

2026-11-02: exactly one current Brave request accepted, no reliability claim/retry. First product-component publication failed before model/export because938808-byte RFC landing violates strict full-DOM HTML parsing. A private source-manifest variable was then shadowed by a ResearchSource locator; final audit raised regression_source_changed although all742application hashes were unchanged. Interrupted discovery-only store and logs remain retained; no first native report existed.

P1 correction depends on retained first records and [parent diagnostic](evidence/web004-parent-parser-diagnostic.json). [ADR139](ADR/139-follow-up-coding-reasoning-and-web-audit-correction.md)/[protocol](D46_D60_FOLLOWUP_PROTOCOL.md): explicit anchor-only parent extraction/opt-in issuer, unchanged child/other-source parser and public transport guards, distinct manifest identity and durable failure result. Effort one corrected workflow/native/visual/full/audit milestone; risks provenance ambiguity, parser drift, SSRF and source expiration. Prepared, not yet qualified; no additional current search or direct-hit score replacement.


2026-11-02 actual optional resolver/native/visual gates VERIFIED: corrected original3claim/evidence expectations,oneCORE,oneDOCX/PDFbatch,revoked-proof archive reopening,zero pending operations and all3pages visually reviewed. One current Brave observation accepted; first malformed-parent/operator-shadow failures remain. Final software/audit pending: first final full5836/1FAIL from an earlier interrupted test fixture, now independently recovered under ADR142. A new clean-baseline full is running; no source/report/provider retry, direct-hit relabeling or broad reliability/adoption claim.


2026-11-02 current software status: both later complete745-source fulls retain5836PASS/1FAIL/0ERROR/0SKIP; the remaining fault is original reranker CPU enforcement, including an inherited-original run2147.54s/exit152after2rounds. Owned runtime and original data/security/vector state independently preserved; no source/counter reset or timestamp restoration. [Resource diagnostics](D46_D60_RESOURCE_VERIFICATION.md) retain every rejected optimization; no450CPU/parity criterion relaxed or failed variant promoted. ADR150original-profile passive/inherited probe is running; only its actual PASS authorizes a same-environment current full. D46corrected-review12/12andD60native/all-page gates remain verified, original first failures retained, final software/audit acceptance pending.


2026-11-02 terminal closure for the selected local remediation: D60selected optional publisher resolver/native/all-page integration VERIFIED3/3/oneCORE/oneexport/3pages. CurrentBraveone-queryobservationaccepted; originaldirect-hitfailure and broader coverage/freshness/reliability/browser/rights/production gates remain open. The dated earlier pending/full-failure checkpoints remain history. Actual final full5837PASS and preservation receipt supersede their pending software status; no failed first score is replaced, no candidate450CPU/parity rejection is reversed and no release is approved.


## D60-FRESH-001 — New discovery and bounded coverage (2026-11-03)

P1; dependency: original ResearchService, publisher/source/report/native/archive services and selected SearXNG-Brave. One optional composition/evaluation milestone, with risks of source substitution, archived authority, raw-provider retention, upstream refusal and score inflation; rollback omits the unregistered service. [ADR152](ADR/152-fresh-search-publisher-evidence-composition.md), [frozen protocol](D60_FRESH_DISCOVERY_PROTOCOL.md), [first results](D60_FRESH_DISCOVERY_RESULT.md).

Fresh workflow VERIFIED3/3claims/oneCOREplanner+oneassessment/oneDOCX-PDF/archive-after-revocation/all3pages. Coverage FAILED/INCOMPLETE:4valid official-locator responses, one declared upstream failure,3not dispatched; original8-question denominator/6minimum/every-topic requirements unchanged. Keep Brave; no polling/retry/provider replacement or automatic new panel. Current750-source full5889PASS/0FAIL/ERROR/SKIP and independent preservation VERIFIED; historical745-source5837PASS remains historical. No production activation or model/default change.


## WEB-BRAVE-RATE-001 — Confirmed anonymous frontend throttling

P1before8/8availability/broad promotion. Dependencies: actual upstream recovery or owner-reviewed officialBraveAPIaccount/token/quota. Effort: diagnosis complete; one separately frozen APIcompatibility/sample milestone if chosen. Risks: repeated website bans, credential/cost/quota, altered result ordering and weak reliability claims. Original fixed criteria and both new failed recovery cohorts retained; no more automatic panel. [Actual4-call diagnosis](D60_BRAVE_RATE_LIMIT_RESULT.md), [concrete proposed ADR153](ADR/153-proposed-official-brave-api-after-frontend-rate-limiting.md). Waiting retains website configuration; rollback of optionalAPIevaluation leaves current route/model/data unchanged. APIchoice/credential is pending; no deployment or model decision.
