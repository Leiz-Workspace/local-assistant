# ADR153 - Proposed official Brave API after frontend rate limiting

Purpose: make the remaining provider-interface decision reviewable after measured website-engine rate limiting, without changing any model or activating a new endpoint.

Date: 2026-11-03 (Asia/Ho_Chi_Minh). Status: PROPOSED, NOT ACTIVATED. The owner retained Brave; this record does not interpret that as approval for a new service plan, paid calls or website-to-API migration.

## Evidence

The original5-second cohort's222-byte error and the new30-second cohort's211-byte error are exact SHA/length matches for SearXNG's serialized `too many requests` declaration. The30-second cohort had1valid/1error/6not-run after a successful Python-English diagnostic. Effective SearXNG suspension is180seconds. A separately frozen180-second recovery panel then received another declared rate limit on its first request0.311245seconds;0valid/1error/7not-run. Local suspension does not establish the upstream's reset deadline. All four calls in this owner follow-up are retained, with no retries/model calls/configuration changes. These observations do not establish a GPU/model/embedding fault.

Read-only Vault discovery found14KVv2secret leaves and no search/Brave-named credential candidate. This does not rule out an unidentified key at another path; credential values were not printed or sent to external services. No account, key or paid plan was created.

## Concrete alternatives

1. Retain the selected anonymous SearXNG-Brave website engine and wait for upstream recovery. Keep its failed panels and unchanged acceptance thresholds. No reliable reset deadline was supplied by the observed JSON; no guarantee that another delay yields8/8, and no automatic repeated panel is scheduled.
2. Keep Brave as the search provider but evaluate its official Web Search API, using the already existing unregistered `src/infrastructure/brave_search.py` adapter and fixed endpoint `https://api.search.brave.com/res/v1/web/search`. The existing adapter requires a reviewed account and API key. The official documentation describes authentication through `X-Subscription-Token` and explicit `X-RateLimit-*` metadata. API quota can still fail; an account/key does not guarantee8/8or relevant sources.

Official references checked for this proposal: [authentication](https://api-dashboard.search.brave.com/documentation/guides/authentication), [rate limiting](https://api-dashboard.search.brave.com/documentation/guides/rate-limiting), [Web Search reference](https://api-dashboard.search.brave.com/api-reference/web/search/get). Example quota values in documentation are not this owner's subscribed allowance. No plan/price is selected.

## Proposed evaluation if the owner chooses the API

P1 dependency: owner-supplied Vault path for an actual Brave API token, reviewed plan/quota/budget/query retention and permitted use. Effort: one bounded adapter/response/cleanup compatibility milestone and one separately frozen eight-question comparison; source/report-model behavior and all model choices remain unchanged. Risks: API cost/quota, authentication, different result ordering/coverage, credential leakage and mistaken production promotion.

Before API requests, inspect the supplied credential only in memory; bind its service origin and never test unrelated keys against Brave. Test missing/wrong credentials, complete response limits, cancellation and quota handling. Freeze exact existing eight questions, source labels and thresholds before the first actual call; cap requests and handle documented rate resets without score-selecting retries. Report the original website cohorts and API cohort separately; availability/URI coverage is not independent semantic relevance or production readiness. Follow existing evidence/report proof boundaries for any later integration.

No migration of models, embeddings, collections, source files, database rows or old evidence is needed. Preserve SearXNG configuration/container and default selection. Rollback discards the optional API evaluation and uses the existing unchanged website route. Production/API selection and any ongoing paid usage require a concrete reviewed implementation and explicit owner decision; neither occurs in this task.
