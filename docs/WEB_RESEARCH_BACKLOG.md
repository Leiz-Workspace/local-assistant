# Web research dependencies and backlog

**Purpose:** Assess web research prerequisites before scheduling or activating new capabilities.

## WEB-ONBOARD-001 — Actual search provider/account

| Field | Assessment |
|---|---|
| Status | Required external prerequisite, not fulfilled: owner confirmed no existing provider account/key. D47 remains PARTIAL. |
| Priority | P1, required before D47 live acceptance and D48 API activation. |
| Scope | Identify the operator-owned provider and actual plan; verify quota/payment/query retention/result-use rights, then supply its credential through an approved secret path and run bounded live acceptance. |
| Existing independent work | Provider-neutral search/CORE contract, inactive Brave reference adapter and controlled HTTP/actual CORE fixture tests under [ADR-064](ADR/064-search-provider-boundary-and-existing-core.md). This is implementation readiness, not account adoption. |
| Dependencies | Owner account/contract decision; valid provider credential/endpoint; reviewed least-privilege secret storage plan before any Vault write. Internal API/Vault operator credentials are not search credentials. |
| Initial effort | One operator account/terms/credential setup plus one bounded live verification gate; elapsed time and account fees unknown. Re-estimate after provider selection. |
| Risks | Unexpected paid usage, disclosing private queries, retaining restricted results, using an unrelated secret, accepting blanket zero-retention claims or mislabeling mocked HTTP as live search. |
| Activation | No signup/purchase/payment acceptance, Vault write, production API wiring or provider fallback is performed by this backlog item. No actual provider budget has been authorized. |
| Acceptance | Record actual plan/provider/terms/quota/privacy decision and credential provenance without values; make a bounded explicit public query, validate status/shape/citations/cleanup and retain real outcomes/usage without storing restricted raw results. Failures remain retained; no synthetic substitution. |
| Rollback | Disable and drain the later search adapter; preserve original models/config/data. No migration/reindex needed for the current unwired implementation. |

Brave remains an inactive reference implementation; Tavily and an owner's existing alternative remain candidates. No provider/model benchmark winner or migration is implied. D48–D60 stay sequenced by their roadmap acceptance criteria. [D47 plan and limitations](D47_SEARCH_PROVIDER_GATE.md).
