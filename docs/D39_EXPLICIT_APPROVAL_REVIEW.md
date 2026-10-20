# D39 explicit scoped approval review

**Purpose:** Describe exact human review, expiring one-shot grants, bounded event ownership and tested CLI behavior before action execution exists.

**Status:** PASS within the local process-local approval-contract/CLI scope. [ADR-057](ADR/057-explicit-scoped-expiring-approval-events.md), [acceptance](evidence/d39-approval-acceptance.json), [source freeze](evidence/d39-approval-freeze.json).

Explicitly enable `ASSISTANT_APPROVAL_ENABLED=1` only with the accepted workspace service/catalog. Default off. No actual host workspace, production feature or production action is enabled/approved by these changes. Only trusted future application composition can create a request with exact owner/workspace UUIDs, action kind patch or run_checks and complete concrete UTF-8 review bytes. D39 exposes no arbitrary public creation, consumption, command or edit endpoint. D40–D43 must supply canonical source-version/patch/command context and revalidate it before any action; an opaque review alone does not validate future action semantics.

## Review and explicit decision

Authenticated local bearer/Origin routes:

| Method | Route | Behavior |
|---|---|---|
| GET | `/api/v1/approvals/{request_uuid}` | Full owner-only artifact, owner/workspace/kind/hash/digest, nonce, state/expiry and bounded event copies |
| POST | `/api/v1/approvals/{request_uuid}/decision` | Only explicit approve/reject with the exact displayed scope_digest and review_nonce |

Successful responses are private/no-store/nosniff. Unknown and foreign request IDs return the same not-found response before expiry/events. Strict16KiB streamed JSON rejects duplicate/nonfinite/invalid-Unicode/extra/authority fields. Decisions cannot change owner, workspace, artifact, model, action or TTL. Nonces are256-bit server randomness encoded as43 URL-safe characters; they are owner-only and removed after a decision. Exact scope SHA256 binds owner/workspace/kind and SHA256 of all review bytes. Review artifacts are copied immutable UTF-8 bytes,1–32768 bytes. A body containing model approval text is not an explicit server decision.

Fixed lifetime120 monotonic seconds; exact deadline fails both decision and consumption. Recheck immediately before publishing a transition, including time crossing during validation. UTC expires_at is display data only. Approved grants can be consumed by trusted action code exactly once for the same current complete artifact/kind/owner/workspace. Changed context invalidates rather than widens the request; rejected, expired, invalidated and consumed requests cannot revive or replay. Domain operations are synchronized for actual competing-thread consumption. There is no automatic action on approval.

At most64 records and256 events; active records are never evicted to admit another active request. Terminal records may retire at capacity, old IDs then fail closed. Expiration is checked on access/capacity management; idle expired records may remain as bounded review history but cannot authorize action. Shutdown/restart invalidates all grants. This is single-process ephemeral state: no durable/cross-worker replication or approval recovery claim. Audit records only server request/event IDs, owner/workspace/kind/digest/state/UTC time, never artifact/nonce/credential content. No DB/Vault/model/config migration.

## CLI review

Supply an explicit literal loopback API base and a server-generated request ID from trusted proposal composition:

```sh
uv run --no-sync python -m scripts.review_approval \
  --base-url "$APPROVAL_API_BASE" --request-id "$APPROVAL_REQUEST_ID"
```

`APPROVAL_API_BASE` must use http/https with literal127.0.0.1 or::1 and exact `/api/v1` base, without user-info/query/fragment. Set it to the actual running local API address; no port is inferred. The CLI privately prompts for the bearer token; no token command-line or autoapprove flag exists. HTTPX disables proxy environment and redirects. It verifies the returned complete artifact hash and owner/workspace/kind scope digest, renders all review data as escaped JSON without displaying the nonce, then requires exactly `APPROVE <complete-request-uuid>` or `REJECT <complete-request-uuid>`. Partial/wrong/empty input or EOF cancels without POST. Source terminal-control characters are escaped; review is never silently truncated.

Only the exact displayed digest/nonce is submitted. Redirects, changed/malformed/oversized review or missing nonce fail before prompting/posting. If full review cannot be displayed, no approval POST occurs. If receipt output fails after a successful server decision, CLI reports failure while server state remains authoritative; it does not invent a rollback, retry or action. User can fetch current request state. Cancelled token input does not contact the API. No proposed action executes after a CLI decision.

## Observed verification

**548 related PASS/7.70s,0 SKIP,exit0**, including71 new D39 cases and477 existing workspace/auth/API/explanation/diagnosis cases.10 evaluated Python files/75 described functions/classes pass Ruff correctness/import/format.2099 collected is **not a fresh2099 full run**; historical D34 full1785 and D38 separate first coding measurement remain separate.

Actual local ASGI and Uvicorn/TCP CLI fetch/typed decision plus one-shot synthetic consumption pass, with source bytes unchanged. Exact monotonic/validation-crossing boundaries use a disclosed controlled clock; real simultaneous thread consumption grants once. Hash/nonce/owner/kind/content immutability, replay/rejection/scope invalidation, capacities, retirement/restart/shutdown, unauthorized/foreign/Origin/extra fields/strict body/default-off, maximum32768-byte review, terminal escaping, private token/nonce audit, redirect/URL limits, cancelled input and broken output pass. Later DB-startup failure invalidates approval before diagnosis→explanation→workspace cleanup. These are disposable synthetic owner approvals, not consent on behalf of the real owner for project mutation.

[Final readonly audit](evidence/d39-final-post-audit.json): V006, empty source/memory/quota/vector/probe/worker/lock inventories, no sandbox survivor, original owners/ACL/grants and all protected model/config/dependency/migration bytes preserved.330 prior files unchanged and10 D39 evaluated files match freeze; only old main/lifecycle composition changes. D38 first4/6 repaired tasks and two failures are hash-protected and were not retried for score selection.

Disable/drain approvals to roll back; outstanding grants invalidate without data/model migration. D40 concrete proposal/diff/path validation and atomic edits is next; the D39 approval itself cannot modify a source file or execute a command.
