# ADR-066: Bounded authenticated search API

**Purpose:** Define D48 query normalization, process-local quotas and HTTP/lifecycle ownership around the accepted owned SearXNG→existing CORE pipeline.

**Date:** 2026-10-21 (Asia/Ho_Chi_Minh)

**Status:** Accepted and verified within the defined local D48 scope:99 controlled/1640 related subsets, fresh3010 full PASS/0SKIP/exit0, first actual TCP/provider/CORE4-citation gate and readonly audit pass. D47 is committed at416e75b; its actual selected-provider gate, both failed cohorts and original mocked-search CORE sample remain immutable.

## Priority, dependencies, effort and risks

Existing P1 D48 follows completed D47. Depends on current bearer-principal authentication/local-origin policy, owned SearXNG singleton Brave frontend and original inference port. Estimate one normalization/quota/service/HTTP/lifecycle milestone plus unit, real TCP, cancellation/fault, related, fresh full and readonly audit gates. Risks: unauthenticated query disclosure, selector/endpoint/model authority in client input, unbounded concurrent sends/counters, quota bypass/refunds, leaked query/token diagnostics, cancellation releasing admission before HTTP/model cleanup and startup failure leaving tasks alive. No new model, dependency, schema, Docker/Vault/data or provider configuration change.

## Explicit query only and visible normalization

POST `/api/v1/web/search` accepts only strict JSON `{ "query": "..." }`. Authenticate the existing principal and direct-loopback/no-Origin/no-forwarded-header policy **before body consumption**. Bound incoming stream to2048bytes independently of Content-Length, reject compressed/non-JSON bodies and reuse the accepted strict JSON parser for duplicate/nonfinite/deep/invalid-Unicode rejection. Framework validation errors become finite codes without echoing input. No owner/provider/engine/model/URL/budget/source/conversation/memory overrides.

Validate original query at512 UTF-8 bytes before normalization; NFC plus trim/collapse Unicode whitespace, no case folding/transliteration/spelling/synonyms or hidden new queries. Reject empty/control/surrogate/overbudget results. Reject tokens starting `!` or `:` so SearXNG engine/category/language/external-redirect selectors cannot be requested; keep ordinary `site:`/quoted terms/URL text. [Official syntax](https://docs.searxng.org/user/search-syntax.html). The response returns the normalized query and whether it changed; content remains untrusted. The unchanged pipeline verifies the provider's exact query round trip and never follows redirects.

## Finite process-local admission and quotas

One nonqueued admitted operation per service, retained through final response delivery/error. Fixed60second monotonic window, at most16 admitted attempts globally and4 per principal; at most16 distinct principal counters, cleared only on a known server-owned window reset. No source/result cache/history or durable counter store. This is one-process protection, not distributed billing or multiworker quota certification; restart resets counters and window boundaries may permit bursts. Provider-side limits still apply.

Authenticate/validate/default-off/closing/busy/quota rejections perform no provider/model call. Charge once after admission, before dispatch; an admitted failed/cancelled/task-creation-failed attempt remains charged, with no automatic refund/retry. Exhaustion returns429 and bounded Retry-After. Counters use trusted principal UUIDs, never body identities. No client-configurable quotas/clock. A test-only injected trusted monotonic clock enables deterministic boundary tests without sleeping.

## Operation ownership and response bounds

Run the unchanged pipeline in one owned child task. Shield normal waiting; on caller cancellation cancel that child once and join through the accepted cancellation-safe helper before releasing admission. Actual provider/model failures remain fixed sanitized errors. Dependency deadlines are cooperative; closing HTTP ownership does not promise that a remote inference server has stopped computing. No model preemption or other service cancellation.

Retain the owning request in a bounded operation set until a private no-store/nosniff JSON response finishes or fails; complete encoded response at most64KiB. The response closes its entered context in finally. Final context release has no native or asynchronous cleanup because the pipeline child is already joined. An unentered context/task-creation/serialization/send failure must close its coroutine/context and release the slot without forgetting charged quota. TCP disconnect alone is not claimed as automatic cancellation; actual task cancellation and finite deadlines are tested.

Shutdown rejects new requests, cancels/joins only this service's owning requests, and runs before the existing optional resources close. Initializer is default-off (`ASSISTANT_WEB_SEARCH_ENABLED=1` required), performs no network/model startup, and constructs only the accepted fixed owned-instance adapter and original CORE. No special workspace/database dependency. Required earlier-PASS changes are limited to main router include and lifespan state/initializer/first-drain wiring; existing shared primitives/routers/models remain unchanged.

## Acceptance and rollback

Test normalization/byte/token bounds, fixed-window boundaries/capacity/principal separation, no charge on precondition rejection/no refund after admission, fixed pipeline options and explicit-only input. Test provider/model failure and timeout, concurrent busy, cancellation at each stage, repeated caller cancellation during child cleanup, task-creation failure, serialization/header/body/send failure and shutdown/startup-failure ordering. Prove no credential/query/result text in logs or provider/model authority fields.

Exercise real authenticated HTTP/TCP with controlled ports, two principals, strict malformed/oversize/duplicate/unknown/identity/model/URL inputs, Origin/proxy/nonlocal denial, private errors/success, rate headers and joined lifecycle. Freeze one separate actual HTTP→owned SearXNG→original CORE sample before inference, with no original-score replacement; preserve first failure if any. Run affected regression and a **fresh exact-source full suite** because main/lifespan wiring changes, then readonly source/model/security/data/provider/worker/lock audit. No PASS from code, collection or skips. D49 remains next after these gates.

Disable the new flag and drain this optional service to roll back the API; the separately accepted D47 provider can remain running. Revert only new API/policy/service files and the documented two composition changes if needed; no migration, reindex, source/data deletion, model replacement or shared-container restart.


## Observed acceptance

[Acceptance](../evidence/d48-search-api-acceptance.json), [fresh full](../evidence/d48-full-regression.json), [first actual API attempt](../evidence/d48-first-live-api.json) and [readonly audit](../evidence/d48-final-readonly-audit.json). Full3010 PASS/1637.76s,0SKIP; related1640 PASS/115.45s is a subset, not an additional full run. First separate script2.934s/one provider/one original CORE/four citations; no raw provider snippet persistence or semantic/freshness certification.451 source/config/897 unique current source-protected hashes; exactly two historical composition files verified against D47 Git bytes. Source/model/config/dependency/schema/data/container checks pass; default production flag remains off. D49 is next.
