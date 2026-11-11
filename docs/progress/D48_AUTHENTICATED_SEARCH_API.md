# D48 authenticated bounded search API

**Purpose:** Document the explicit local search API, ownership/rate limits, measured acceptance and operational limits without changing the agreed models or provider.

**Status:** PASS within the defined local authenticated explicit-query scope; fresh full-suite and readonly audit gates complete. D47 is committed at `416e75b`; its selected-provider acceptance and both earlier failing cohorts remain immutable. [ADR-066](../ADR/066-bounded-authenticated-search-api.md) records the design and the two necessary earlier-PASS composition changes.

## Operator configuration and request

The API is registered at `POST /api/v1/web/search` and remains unavailable by default. Enable it for an application process with `ASSISTANT_WEB_SEARCH_ENABLED=1` and the existing private `ASSISTANT_AUTH_FILE` principal configuration. Startup constructs dependencies without making a provider/model request, loading a model or requiring a workspace/database. The already accepted owned SearXNG instance on loopback8889 and original CORE must be available for actual queries. No new commercial search key, account, model, Docker change or Vault write is required.

Use a direct loopback client, the existing bearer token header, `Content-Type: application/json` and a body containing only an explicit query:

```json
{"query": "SearXNG Search API JSON format"}
```

No owner/provider/engine/model/URL/source/memory/conversation/budget override is accepted. Query text is intentionally disclosed to the configured upstream search engine; no automatic private context is included. Origin and forwarded/proxy headers are refused. Authenticate before consuming any body bytes. Logs retain finite operation/error/count metadata; query/result/token/provider diagnostic text is excluded.

## Bounds and visible behavior

| Boundary | Policy |
|---|---|
| Incoming body | At most2048 raw bytes, strict JSON object, no duplicates/nonfinite numbers/invalid Unicode/compression |
| Query | Original at most512 UTF-8 bytes; NFC plus trim/collapse Unicode whitespace, canonical query and changed flag returned |
| Provider selectors | Tokens starting `!` or `:` refused; ordinary `site:`/URL/quoted query terms remain text |
| Rate | Fixed process-local60second monotonic window;16 admitted attempts globally,4 per principal,16 principal counters maximum |
| Concurrency | One nonqueued operation; retained through response completion/failure, busy429/Retry-After1 |
| Charge | Once before dispatch; admitted errors, timeouts, cancellations and task-creation failure retain the charge; no automatic refund/retry |
| Rate rejection |429 with finite Retry-After1–60; no provider/model activity |
| Provider/model | Accepted SearXNG singleton Brave frontend, existing CORE/fast/temperature0/max_tokens768; one call per stage |
| Deadlines | Existing cooperative provider10s/model60s; child cancellation/HTTP cleanup joined before admission release |
| Evidence | At mostfive provider snippets; original URL/title/snippet hash bindings, untrusted, semantic_validation=false |
| Response | Complete encoded JSON at most64KiB, private no-store/nosniff on both successes and errors |
| Persistence | No query/result cache/history or durable/distributed quota store |

Fixed finite errors distinguish invalid input422, owner/local denial403, authentication401, media415, body/response limits413, busy/quota429, provider/model unavailable503, malformed generated contract502 and pipeline deadline504. Errors do not echo submitted fields or private exception messages. The accepted authentication configuration's unavailable503 remains distinct.

A fixed window can permit boundary bursts; restarting resets counters and multiple processes have independent limits. This is not a distributed billing/quota guarantee. Actual task cancellation and service shutdown join only owned requests; a TCP disconnect alone is not claimed to cancel inference immediately, and joining local HTTP ownership does not establish backend computation preemption. Upstream rate limits, suspension and CAPTCHA still apply; no bypass/fallback is implemented.

## Measured evidence

Final controlled gate: **99 PASS/1.00s**, including policy/byte/token/rate boundaries, two principals, default-off/startup failure, strict HTTP/auth-before-body, actual Uvicorn TCP, dependency failure/deadline, malformed generation, task creation, repeated cancellation while cleanup is held, shutdown, serialization and response header/body/send cancellation. Tests use authored controlled provider/model ports and do not establish external relevance.

Related gate: **1640 PASS/115.45s,0SKIP,exit0**, including prior accepted workspace/coding/native/source/authentication components. [Related result](../evidence/d48-related-regression.json). This subset is separate from the fresh full-suite gate.

Before the first actual D48 call, freeze451 current source/config files and897 unique current source/protected hashes, including the private one-attempt runner. Exactly `apps/api/main.py` and `apps/api/storage/lifecycle.py` change earlier accepted composition; prior bytes are independently verified against D47 commit416e75b. All other accepted source/provider/model/config/data stays unchanged. Ten evaluated Python files/78 described functions/classes pass isolated Ruff correctness/import/format. [Freeze](../evidence/d48-search-api-freeze.json), [quality](../evidence/d48-source-quality.json). Complete evaluated file versions retained privately in `data/backups/d48-evaluated-full-files.zip` with0600 permissions and CRC/exact-byte checks.

First separate actual authenticated Uvicorn TCP API→owned SearXNG→original CORE: **PASS/2.934s**, HTTP200, four bound citations including docs.searxng.org, visible canonical query, one provider call/one model call/zero retries, charged quota1, joined response/lifespan and private headers. Query/token/signing secret absent from logs; raw provider snippets not persisted. Exclusive artifact `data/backups/d48-first-live-api/summary.json`; [public observation](../evidence/d48-first-live-api.json). This asserted script is not an added pytest case, unseen evaluation, semantic entailment, source-page fetch or freshness certification. D47's original irrelevant-result refusal and Google unavailable cohort remain failures; no first score is replaced.

**Fresh full:3010 PASS/1637.76s (0:27:17),0SKIP,exit0**; wrapper1638.57s. The1640 related and99 controlled cases are subsets; the actual SearXNG API script remains separate. [Full result](../evidence/d48-full-regression.json), [acceptance](../evidence/d48-search-api-acceptance.json). Full log SHA256 `eb7550fbe784598d640c8a425a79943b8d2e40253d0ab0380fe126f3a81fb982`. Final readonly audit passes:V006, zero source/memory/quota/vector/probe/worker/native/advisory-lock/app/pending inventories, original owners/ACL/narrow grants/invoker fixed-search-path triggers, original14 containers and provider resource/security limits preserved. The two authorized composition changes are Git-verified; agreed models/config/dependencies/migrations and all first/failed evidence remain unchanged. Existing CORE/provider remain healthy/running, production search flag off. [Audit](../evidence/d48-final-readonly-audit.json). D49 remains next: bounded HTTP fetch/text/redirect/canonical-source handling, under a new ADR and actual tests.

## Shutdown and rollback

Disable the new process flag and drain this optional API. Shutdown marks it closing, cancels and joins owned requests before earlier optional services close; later startup failure also drains it. Keep the separately accepted D47 provider running if still needed. Reverting the new API/policy/service modules and the two documented composition changes requires no migration/reindex, data deletion, model replacement or existing-container restart.
