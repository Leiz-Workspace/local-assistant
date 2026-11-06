# D60 Brave rate-limit diagnosis result

Purpose: record the proven provider failure, unsuccessful recovery measurements and the concrete dependency for further8/8qualification without relabeling old scores or changing agreed models.

Date: 2026-11-03 (Asia/Ho_Chi_Minh). Status: diagnosis VERIFIED;8/8availability NOT ACHIEVED. [Initial follow-up protocol](D60_BRAVE_AVAILABILITY_PROTOCOL.md), [cause-based recovery protocol](D60_BRAVE_COOLDOWN_PROTOCOL.md), [exact-response proof](evidence/d60-brave-20261103-final-rate-limit-proof.json).

## Actual cause established

Brave's website engine is declaring **too many requests**. The previous observer retained only a body SHA, so the old report correctly left the cause unknown at that time. The installed SearXNG serializer translates internal exception classes to user-facing English labels; the first new diagnostic observer did not yet recognize these translated labels. Its raw-text hash was retained, then classified offline without rewriting any response.

Using the fixed original questions and installed JSON field order, reconstructing the exact empty-result JSON with the finite label `too many requests` matches complete byte length and SHA256 for three responses: original222bytes,30-second trial211bytes and later recovery197bytes. This is byte identity, not a timing-based guess. No raw error prose, provider title/snippet or query text is persisted in these proof records. The declaration identifies rate limiting; original upstream HTTP status/headers/reset deadline were not independently captured.

## Every measured outcome retained

| Cohort | Valid panel responses | Error | Not dispatched | Actual search calls |
|---|---:|---:|---:|---:|
| Original first panel, unchanged | 4/8 | 1 | 3 | 5panelcalls plus3originalworkflowcalls |
| New30-second paced panel | 1/8 | 1 | 6 | 2panelcalls plus1Python-Englishdiagnostic |
| New panel after effective cooldown | 0/8 | 1 | 7 | 1 |

The new diagnostic itself returned5valid hits and no upstream failure. Its positive observation did not guarantee the following panel would work. The next two starts were30.011105and30.029732seconds apart; the second panel question was rate-limited. This error completed at20:21:44.840204UTC.

The merged setting `search.suspended_times.SearxEngineTooManyRequests` is180seconds, not the one-hour value mentioned in an older exception docstring. That is SearXNG's local suspension interval, not Brave's promised reset time. The recovery measurement began20:28:38.681697UTC, more than413seconds after the previous completed error. Its first request was still rate-limited after0.311245seconds; later cases were not sent. Thus a local180-second cooldown did not restore availability in the measured condition. The planned21–24minute panel ended early under its frozen stop rule.

This owner follow-up made exactly4actual provider calls,0automatic retries and0local-model calls. Headers/cookies/IP/provider selection, adapter10-second timeout, source labels, queries/order and8valid/6primary/per-language/per-topic thresholds were unchanged. No bypass, engine fallback, repeated polling or production deployment occurred. Neither failed panel is combined with successful rows from another run to manufacture8/8.

## Software and data closure

The application remains the exact750-source snapshot with retained full5889PASS/0FAIL/ERROR/SKIP; no new full run is claimed. Private tooling only:32initial diagnostic controls PASS0.45s; an overlapping87related controls PASS0.99s;56translated-reason/cooldown/exact-proof controls PASS1.11s. These are separate scopes and do not sum into the retained full. Source/configuration hashes and original model choices remain unchanged; [fresh read-only preservation is VERIFIED](evidence/d60-brave-20261103-final-result.json): original business/security/schema0006, authenticated Qdrant0, native0/same15containers and176D70inputs/hearing0/24preserved; only the already disclosed zero-usage quota timestamp differs from the older baseline.58separate handoff controls PASS0.39s;12private file Ruff/format/module-function-class descriptions PASS. Both original18-input and recovery25-input execution graphs remain exact. No model download, shared-service restart, database write, Vault secret/policy change or new hearing label.

## Remaining decision

Waiting for actual upstream recovery can preserve the anonymous website route, but the measured JSON supplies no reliable reset deadline and no guarantee of8/8. Retrying sooner or weakening validation does not resolve the external limit.

An optional evaluation of the official **Brave Search API** is concrete in [proposed ADR153](ADR/153-proposed-official-brave-api-after-frontend-rate-limiting.md). The repository already contains an unregistered adapter. The standard existing adapter requires a reviewed account and an API token; official documentation describes explicit quota/reset headers. No API request, account/plan purchase, endpoint migration or default change has occurred. API quota/source coverage must still be measured; it is not a promised8/8.

Read-only Vault discovery found1KVv2mount/14secret leaves and no Brave/Search-named credential candidate. Values were not printed or sent externally. A differently named key would need its actual Vault path from the owner. The owner has been asked to choose retaining the website route and waiting, or evaluating the API with an identified credential. Existing D60fresh report3/3/native/archive/all-page verification and D70owner-deferred0/24 remain unchanged. Broader coverage remains OPEN.
