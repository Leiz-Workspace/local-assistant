# ADR-083 — Next search upstream qualification proposal

**Purpose:** Present a concrete next option after retained selected-provider and Mwmbl/spacing failures without silently switching a provider or changing any model.

**Date:** 2026-10-22. **Status:** DEFERRED by operator on2026-10-22: retain Brave and wait for upstream recovery; no Bing evaluation, runtime wiring or adoption.

## Current evidence

Vault/runtime recovery and final readonly audit PASS at540 source/config files; all538 prior bytes and model/data/security/services remain unchanged. D60's operator recovery trial finds actual SearXNG API URLs but no required RFC family; first spaced trial stops after its first upstream error. Actual live spacing was not exercised. The searched-source→report/native/archive gate remains failed. Further repetitions of these trials or label/source-family relaxation are not a qualification strategy.

Official SearXNG documentation distinguishes [Brave web engine from keyed Brave API](https://docs.searxng.org/dev/engines/online/brave.html). The current owned service uses the former; self-hosting SearXNG does not create an upstream availability or API-key guarantee. Mwmbl's actual panel remains0/8 expected-primary hits. [Bing web](https://docs.searxng.org/dev/engines/online/bing.html) is another built-in upstream; its docs state paging/time-range functionality is limited by JavaScript. [DuckDuckGo](https://docs.searxng.org/dev/engines/online/duckduckgo.html) documents bot detection and reverse-engineered form fields, so it is not assumed to remove the observed website-engine availability risk. None of this documentation is a measured local quality comparison or independent permission determination.

## Concrete proposed next step

Keep the existing selected Brave instance and every agreed model unchanged. If the operator chooses further upstream qualification, evaluate **one Bing-only isolated candidate**, not a rotating fallback pool. Before startup, review current provider usage/result-retention requirements; the existence of a built-in module is not sufficient proof of permitted use. If that review cannot support a bounded technical evaluation, do not send queries. No account/key purchase or service registration is included.

Use the exact cached SearXNG digest already present, original nonroot/readonly/cap-drop/no-new-privileges/noGPU/768MiB1CPU128PID constraints, a unique owned temporary project/container/loopback port and fresh throwaway fixture signing key. Never pull/build/install, mount private credentials/models/workspaces, change the original service/config/default route, or use CAPTCHA/proxy/cookie/IP/suspension workarounds. Prepare strict conformance/identity/cleanup tests and frozen complete evaluated files before any startup.

The first panel uses the unchanged eight-query/four-primary D53 corpus and original complete strict response/URL/source-family rules, at mosteight ordinary public queries with fixed spacing; stop on the first declared restriction/upstream failure, retaining every unattempted row in the denominator. Persist hashes/URLs/counts/finite errors only. Report actual executed/accepted/blocked requests, expected-primary presence/rank, latency and bounded container-resource samples separately. No semantic precision/recall or general-quality claim from these URI labels.

Require both actual D60 primary families before considering any separate same-goal/model/claims/label live source→signed report/native/archive trial. No caller-designated fallback or redirect/canonical/source-family relaxation to manufacture a hit. A successful candidate panel does not automatically qualify production or relabel any previous failed gate. A failed candidate ends this proposed panel; no engine loop.

## Priority, impact and rollback

P1/current WEB-SEARCH-003 dependency; depends on compliant upstream access, cached immutable runtime and existing strict source/ownership/cleanup corpus. Estimated effort one isolated compatibility/coverage/resource panel, then a distinct end-to-end measurement only if prerequisites pass. Risks: upstream restrictions, insufficient primary coverage, filtering/paging/date differences, parser/URL incompatibility, data-use rights, transient outcomes and false equivalence with a licensed API. No measured performance or quality benefit is claimed now.

Future adoption requires a separate concrete compatibility/performance/resources/privacy/retention/migration/rollback review. Reconfigure no production provider until that decision; preserve exact original Brave adapter/settings/container identity as rollback. Trial cleanup stops/removes only the verified owned candidate ID/empty project network and removes its fresh temporary secret. Existing models, collections, database, Vault secret values, accepted artifacts and original15 resources stay intact. No model replacement, migration or reindex.

## Operator resolution — 2026-10-22

The operator explicitly selected: retain Brave and wait for upstream recovery. The Bing-only qualification proposal is deferred and not scheduled or authorized for execution by this decision. Preserve the existing SearXNG/Brave instance, configuration and every agreed model. No further provider trials, automatic polling/retry schedule, engine rotation or background monitoring is started. No recovery time or upstream Retry-After is known.

D60 remains IN PROGRESS / WAITING FOR UPSTREAM; the failed searched-source artifact gate and every original score/exception remain unchanged. Do not advance D61 or infer PASS from elapsed time, source-designated reports or the successful Vault/data audit. Resume a bounded verification only after the operator reports upstream recovery or explicitly requests a new verification; freeze that invocation and retain prior outcomes. Reconsidering another upstream requires a new operator selection.
