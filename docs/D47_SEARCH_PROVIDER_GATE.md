# D47 search provider implementation and remaining gate

**Purpose:** Track the unwired bounded search/CORE implementation separately from missing real provider/account acceptance.

**Current state:** IN PROGRESS/PARTIAL. The owner confirmed “Tôi chưa có” in response to the provider/account question. There is no search account/key to retrieve. [ADR-064](ADR/064-search-provider-boundary-and-existing-core.md) defines candidate review and the inactive Brave reference adapter. No signup, purchase, actual external search, model adoption or deployment.

## Implemented boundary

- Immutable credential-free search port; one explicit query/512 UTF-8 bytes, five complete validated snippets,24KiB whole prompt.
- Conditional Brave reference adapter: explicit reviewed-account configuration and key required; fixed HTTPS POST, environment proxies disabled, no redirects/retries/summaries/callbacks. Five web rows; US/en reference settings, no multilingual coverage claim. Total10second cooperative timeout,64KiB uncompressed JSON body, streamed8192byte reads; finite redacted errors and awaited cleanup.
- One unchanged CORE/fast/temperature0/max_tokens768 completion/60second cooperative timeout. Server-owned source IDs and original URLs/titles; strict JSON/refusal and no model-authored link authority. Single nonqueued operation, no background tasks, no automatic source/conversation/memory disclosure.
- No startup/public API/config/Vault/database integration or durable search cache. Import/construction sends no request. Real result storage rights remain unchecked. Reference binding does not prove semantic entailment, freshness, relevance or general injection robustness.

## Validation protocol

Final unit/HTTP fixture gate115 tests; source-quality/collection/source freeze precede one actual CORE authored fixture. The authored input/oracle in `tests/fixtures/search/d47-search-core.json` is fixed before inference: one mock Brave-shaped HTTP response, one actual original CORE port attempt, zero actual external provider requests/retries, exact S1→original URL binding and answer containing G-17. Retain first failure as well as success; no replacement/retry/claim of independent labels. Future regression trials must retain unique artifacts separately.

Run the prior D33–D46 affected target list plus the115 new controlled cases. Preserve prior accepted source/config/model/evidence bytes; no new full-suite claim from collection or this affected regression. Readonly original ACL/data/vector/process/model audit follows. Complete new/committed files are saved privately with hashes and ZIP readback verification.

## Unmet acceptance and next action

1. Identify the operator's actual provider/account and accepted plan. Brave is only an inactive implementation candidate; no entitlement/payment/retention approval is inferred from a passing fixture.
2. Review that account's terms, query privacy, permitted transient/durable use and quota. No default zero-retention or storage-rights claim.
3. Provide a provider-specific credential through an approved secret path; the local application API token is a different credential. This task performs no Vault writes or account creation.
4. Exercise the bounded adapter against the real service and retain actual status/usage/resource observations. No paid query or plan signup is authorized by this document.

D47 remains open until these live prerequisites are fulfilled; D48 remains dependent. The next code milestone is D48 query normalization/rate limits/authenticated search API after D47 acceptance, followed by D49 separately controlled fetching. Existing source/data/models/D24 and all first measurements remain unchanged.
