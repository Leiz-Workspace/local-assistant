# D47 owned SearXNG acceptance

**Purpose:** Record the owner-selected real search provider, actual CORE integration, failed attempts and remaining web research limits.

**Current state:** PASS for the defined local selected-provider scope on2026-10-21. The owner explicitly selected self-hosted SearXNG. [Acceptance](evidence/d47-searxng-acceptance.json), [ADR-065](ADR/065-inactive-local-searxng-candidate.md), [runtime audit](evidence/d47-searxng-runtime-audit.json). Earlier [D47 PARTIAL](evidence/d47-status.json)/[pre-provider plan](D47_SEARCH_PROVIDER_GATE.md) remain historical immutable evidence; they do not describe the now-completed live prerequisite.

## Actual deployment and selected upstream

One isolated `local-assistant-searxng` container, project `local-assistant-search`, serves only `127.0.0.1:8889`. Official linux/amd64 image pinned to manifest `aa7270053bc3bf92155e2af83e2b0a7c3833c209cdeb8d396861a00c55ee7110`. Nonroot/readonly/drop-all-capabilities, no GPU or host socket/shared service network,768MiB memory/swap cap, oneCPU,128PIDs and bounded temporary cache/tmp. The14 original containers retain exact IDs/images/start times/ports. Current service health200 and original CORE health200. Point memory observation90.42MiB/768MiB; not a peak, benchmark or SLO.

SearXNG uses its anonymous **Brave website engine**, not the separate paid/key-based Brave Search API adapter. There is no commercial search key, new model, Valkey or other database. Query text reaches the upstream from this server's IP. Upstream limits/terms/content rights still apply; no SLA, broad coverage or universal zero-retention claim. No proxy/public-instance rotation, CAPTCHA solving or hidden fallback. Explicit request engines are not combined with categories, and every returned/merged engine must match the singleton allowlist. [Pinned SearXNG engine source](https://github.com/searxng/searxng/blob/81371861f67226091d1c4df2e3908a11d3b54eb9/searx/engines/brave.py).

Private local `.env`0600 holds only a generated cookie-signing secret, excluded from Git and backed up privately; existing Vault unchanged. New stack [operations](../../infras/searxng-server/README.md). Container Python logging retains finite severity/component categories and omits messages/arguments/tracebacks; access logging disabled. The actual query and signing secret are absent from container logs. This is defined tested logging behavior, not proof about every upstream vendor's logging.

## First failures and compatibility repair

1. Initial Bing/DuckDuckGo/Wikipedia trial: actual HTTP200/ten rows/five selected/two upstream failures, unrelated selected literature sources. Exactly one unchanged CORE attempt correctly returned insufficient evidence. The frozen answered/JSON/primary-citation oracle failed. Original source/config/summary preserved in `data/backups/d47-searxng-before-upstream-repair.zip`.
2. Four zero-model diagnostic calls retained variable results, DuckDuckGo CAPTCHA and Wikipedia suspension. They did **not** isolate engines: the pinned server adds category engines when categories and explicit engines are both specified. This limitation is recorded; no per-engine quality scores inferred.
3. Necessary no-category/provenance repair plus singleton Google configuration: HTTP200/zero rows/one upstream failure before inference. A separate zero-model diagnostic observed native suspension. Entire failed Google cohort preserved in `data/backups/d47-searxng-google-cohort.zip`.
4. Frozen two-engine zero-model compatibility panel: Mwmbl200/eight rows without the required primary domain in first five; Brave200/twenty rows with primary documentation and exact engine identity. Frozen preference selects the first ready engine, Brave frontend. Mojeek was excluded before execution because its pinned implementation contains automatic CAPTCHA solving. No blocked-engine bypass.

These are a visible connection/query sanity panel and necessary request-provenance repair, not a broad relevance benchmark or a model-comparison winner. Both failed live cohorts remain failures. The original query/oracle/CORE prompt/model thresholds were retained for final verification.

## Final evidence

Final selected-source live attempt: one actual local SearXNG POST and one original CORE/fast/temperature0/max_tokens768 application-port call,2.663seconds total, answered JSON-format question with four source-bound citations including official documentation. All selected snippets/URLs/engine fields passed bounded validation, HTTP stream/transport joined; no model-authored URL authority. Twenty raw rows are validated, first five projected in original order, omitted count logged. Raw provider snippets are not persisted; hashes/byte counts/URLs and generated result retained privately. Reference binding is not semantic entailment, freshness or general injection robustness.

Final82 new pytest cases PASS; included in **1541 related PASS/116.73s,0SKIP,exit0**. The actual live acceptance is a separate asserted script, **not another pytest case**. Original pre-provider one-case mocked-search/actual-CORE measurement remains separate and unchanged. Four evaluated Python files/30 described functions/classes pass isolated Ruff correctness/import/format; [freeze](evidence/d47-searxng-related-freeze.json) binds443 source/config files/882 unique protected hashes. Pre-live metadata copied an earlier description count29; the regression freeze records the corrected30 without editing either frozen source/oracle artifact.

Readonly security/model/data audit: V006, zero source/memory/quota/vector/probe/worker/native/advisory-lock/app/pending inventories, original ACL/owner/grant/trigger properties and agreed models/config/dependencies/migrations preserved. D46 first7/10/three failures, D45/D43/D38 first measurements, D44 full/both interrupted predecessors and D24/a88584b remain unchanged. Historical D44 full2622 stays separate; this affected regression is not a new full suite.

## Remaining work and rollback

D48 query normalization/rate limits/authenticated API is NEXT; no application search route/startup flag has been enabled yet. D49 fetching, D51 provenance/cache, D52 webpage attacks, D53 fresh multilingual coverage and D56 semantic citation validation remain later gates. Single upstream HTML drift, rate limiting, process-local admission/cooperative deadlines and local-only deployment limits remain explicit. No long-run/production/multiworker quality claim.

Rollback stops only this new container, preserving private signing secret/config and all evidence; never stop shared stacks or delete existing volumes. No source/data migration or reindex. Full evaluated source/config files and committed versions are retained privately with hashes/ZIP readback verification.
