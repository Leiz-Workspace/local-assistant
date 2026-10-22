# ADR-082 — Bounded provider dispatch-spacing evaluation

**Purpose:** Evaluate polite request spacing and stopping after the first provider failure without changing agreed models, the selected provider or original semantic acceptance labels.

**Date:** 2026-10-22. **Status:** Accepted for a single isolated evaluator composition only; no production adoption or claim of an upstream quota contract.

## Evidence and assessment

The new operator-requested recovery run follows at least eight quiet hours and completed same-boot Vault/data/security/runtime audit. The original selected SearXNG/Brave adapter accepts the first five results, including the required SearXNG API family, then reports two empty-with-declared-engine-failure responses. The first frozen result remains FAILED/live_missing_primary_sources/1.997s, no source/assessment/native. Earlier rate-limit declarations and failed cohorts remain immutable. This pattern does not prove a burst threshold, remote HTTP429, a specific suspension duration or that pacing will fix discovery.

P1/current D60 dependency WEB-SEARCH-003; depends on original D54 bounded plan/quotas/cancellation, D47 strict selected adapter and D60 unchanged source/claim/model oracles. Effort one small pure evaluation wrapper, negative/cancellation/concurrency controls and one distinct live measurement. Risks: treating guessed spacing as permission, hiding skipped requests, extending accepted deadlines, retrying blocked requests, accepting partial evidence, selection bias or implicitly adopting an unqualified component.

## Decision

Add evaluation-only tests/helpers under tests/. One nonqueued wrapper imposes a fixed minimum five seconds between its actual backend request start times, using trusted monotonic time and awaited cancellable sleep. Five seconds is a conservative experimental parameter, not verified Retry-After/throughput permission. No retry, endpoint/engine/proxy/cookie/header change, request replay, suspension reset or CAPTCHA action. After the first backend exception, stop subsequent backend dispatches for this wrapper; retain explicit wrapper admission, actual request and blocked-port counts. No synthetic successful empty response or forged source/query IDs. Preserve the original provider error; blocked later calls fail finitely before I/O.

Original ResearchService remains unchanged, including its45s total/15s model/10s provider deadlines, per-attempt quota/no refund and at mostthree planned queries. Spacing is inside the existing provider call deadline, reducing available backend time rather than increasing budgets. Validation/source/quote/model/label/export/session oracles remain unchanged; all538 accepted source/config bytes stay intact. No raw provider strings/messages or private material persisted by the wrapper. Same-owner local objects do not establish process-wide/distributed quota guarantees.

After passing controlled tests and source/oracle freeze, run at mostone new distinct spaced live evaluation against the existing provider with fresh store/issuers and exact original goal/claims/families. Every previous run remains failed. Success would qualify only this measured evaluator composition, not prove causal improvement/general search quality/current browser security or production adoption. Failure stops further live trials; no engine loop or altered labels/required families. No new package/image/model or configuration/service/Vault secret/database changes.

The original provider is the website engine rather than the keyed REST API; SearXNG documents these as separate [Brave engines](https://docs.searxng.org/dev/engines/online/brave.html). No API account is created, and spacing does not confer a usage right or availability guarantee.

## Adoption and rollback

Any runtime reuse needs a separate review of provider terms/retention, current contract/Retry-After, shared admission/cooldown scopes, fairness/cancellation and whole service budgets, then unchanged-corpus quality/resources/latency and concrete migration/rollback. PriorityP1, dependency compliant provider access and measured reliability, effort one integration qualification milestone; risks include excess requests and silently changed public behavior. This ADR authorizes no production wiring. Rollback removes only the two new evaluation helpers after draining owned calls; preserve first metrics/artifacts/archives and original model/provider/source/data/config. No migration/reindex.
