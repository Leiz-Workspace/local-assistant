# ADR-064: Search provider boundary and the existing CORE

**Purpose:** Define D47 search evidence/privacy boundaries without adopting another model or changing accepted components.

**Date:** 2026-10-21 (Asia/Ho_Chi_Minh); provider research began2026-10-20

**Status:** Accepted for an unwired internal contract; actual provider selection, credentials and live acceptance pending. No account creation, purchase or provider deployment.

## Priority, dependency, effort and risk

Existing P1 D47 follows D46's completed evaluation, first functional repairs7/10. Dependencies: unchanged inference port/CORE and an operator-owned provider endpoint/account. Estimate one contract/adapter/evaluation milestone, re-estimated after provider identification. Risks: private context disclosure, secret leakage, charges, restricted result retention, malicious snippets and fabricated citations. D48 normalizer/rate limits/API, D49 fetch, D51 persistence/cache and D56 semantic citation validation remain separate gates.

## Readonly discovery

Vault metadata traversal lists all11 prefixes/14 leaves of `secret/` KV v2, no errors/remaining prefixes. Private inventory: `data/backups/d47-vault-metadata-inventory.json`, no values. Subsequent schema inspection of `server/local-assistant/api` finds `api_token`/`principal_id`, not a search provider key. Known Tavily/Brave/Serper/SerpAPI/SearXNG/Google search variable names are absent. Credentials elsewhere remain possible. The owner subsequently confirmed **no provider account/key exists yet**. No Vault writes. The missing live prerequisite is established, not a presumed missing secret.

## Candidate review, checked 2026-10-20

Candidates are not an adopted provider or measured ranking. Actual account entitlements remain unverified.

| Provider | API/quota | Privacy/terms |
|---|---|---|
| Brave Web Search | Fixed HTTPS Web Search and subscription header; advertised$5/1000 requests,$5 monthly credits. [Reference](https://api-dashboard.search.brave.com/api-reference/web/search/get), [pricing](https://brave.com/search/api/) | Account/plan/payment information required; queries may remain up to90days, enterprise zero-retention separate. Storage needs plan-specific rights. [Privacy](https://api-dashboard.search.brave.com/documentation/resources/privacy-notice), [storage FAQ](https://brave.com/search/api/) |
| Tavily Search | HTTPS POST/bearer; basic1credit, advanced2;1000 free monthly credits advertised without a card. If selected, disable generated answers, raw content and automatic parameters. [API](https://docs.tavily.com/documentation/api-reference/endpoint/search), [credits](https://docs.tavily.com/documentation/api-credits) | Section6 permits AI-functionality input/output retention and third-party processing. Search-only applicability/account terms require clarification; no blanket zero-retention inference. [Terms](https://www.tavily.com/terms), [privacy](https://www.tavily.com/privacy) |
| Owner's existing SearXNG/other provider | Endpoint/account not found in inspected locations. | Review actual operator/upstream engines/limits/logging when identified; no public instance fallback or deployment. |

## Internal contract; activation deferred

Add a provider-neutral port and internal pipeline with explicitly injected trusted provider/inference dependencies. No startup wiring, public route, environment/credential reader, endpoint, database or persistence. Missing provider fails before inference. No external request from import/construction.

One explicit query,512 UTF-8 bytes, at most five results; complete encoded prompt at most24KiB, rejected before inference on overflow. Send no automatic conversations/workspace/memory/credentials. One provider call,10second cooperative deadline, zero retries. Validate whole immutable typed response: at most five2048byte snippets,512byte titles,2048byte HTTPS URLs without embedded credentials or controls. Reject oversize without clipping/dropping. URLs are evidence only, never fetched; no future-fetch SSRF claim.

Server-assigned source IDs, untrusted snippets in one data message after fixed policy. Use unchanged CORE/fast/temperature0/max_tokens768, one completion/60second cooperative deadline. Empty results skip inference. Strict bounded JSON answer/existing IDs or insufficient-evidence refusal; reject duplicate keys, unknown/duplicate IDs, extra fields, incomplete/wrong-preset results. Server resolves original URLs/titles. Reference binding is not semantic entailment, coverage, freshness or general injection resistance.

One nonqueued operation per instance. Await provider/inference in the owning operation, propagate cancellation after cleanup before releasing admission, no background tasks/retries. Dependencies must honor cancellation; deadlines do not forcefully terminate blocking code. Logs contain finite stage/outcome/count metadata, no query/content/credentials/provider exception text. A later adapter owns credentials outside port payload/model prompts.

## Inactive Brave reference adapter

After the owner confirmed there is no provider, implement a conditional Brave reference adapter without account adoption/startup wiring. It is inert by default: requires a trusted explicit `account_reviewed=True` and a nonempty caller-supplied ASCII key before client construction. No source/env/Vault lookup and no public configuration surface. A future actual account's privacy/payment/storage rights must be reviewed before enabling; this boolean is trusted configuration, not a model/client approval token.

Use fixed HTTPS **POST** so queries are absent from request URLs/default HTTP request logs; no endpoint override, redirect following, environment proxy/credentials, automatic retries, provider answers, rich callbacks or summaries. Five web results only; explicit US/en reference settings, no multilingual-coverage claim. Brave's75word ceiling is checked before HTTP. Request total10seconds, connect3seconds; accept identity encoding/application JSON only, max64KiB raw streamed body/8192byte read chunks, duplicate-key/type/row checks. Compressed responses are refused rather than decompressed. Missing optional web/empty results are no-sources; malformed present web is an error. Provider description-less/oversized rows fail the whole batch. No page fetch/cache/durable real result storage. Auth/quota/non200/transport errors are fixed redacted outcomes. Stream/client cleanup is awaited on completion/timeout/cancellation. Fixed endpoint/schema verified in [official POST reference](https://api-dashboard.search.brave.com/api-reference/web/search/post); actual account support remains unverified.

This extends the same internal boundary; earlier PASS source files remain unchanged. An adapter-ready fixture result is not a real provider result. No provider account is created, paid plan accepted or key obtained.

## Acceptance and rollback

Tests cover byte/type/URL bounds, empty results, model options, binding/strict JSON/refusal, failures, deadlines, cancellation joins, nonqueued admission and redacted logs. A frozen authored fixture may exercise actual unchanged CORE separately; never claim live external provider or independent relevance. Run related inference/workspace regressions and preserve all prior tracked accepted bytes.

D47 remains PARTIAL until actual provider identification, account terms/quota/privacy decision, bounded adapter tests and real credential/endpoint verification. No D48 advance from synthetic results. No model/config/dependency/migration/Vault/Docker/database change. Revert new unwired files to roll back without touching accepted components/evidence.
