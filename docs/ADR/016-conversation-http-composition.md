# ADR-016 — Conversation HTTP composition and local access boundary

**Purpose:** Record the REST composition, credential boundary and operational limits introduced for D15-T05.

**Date:** 2026-10-17 (Asia/Ho_Chi_Minh)
**Status:** Accepted for local development; PostgreSQL, CORE and actual API process restart accepted on 2026-10-17.

## Context

D15-T01–T04 provide PostgreSQL repositories and a two-transaction ConversationManager. The existing stateless chat endpoint must retain its contract. V001 has no owner identity, and this execution environment has no DATABASE_URL or running model on port 8080. Existing ORM sources were accidentally ignored by the unanchored `models/` Git rule.

## Decision

- Register a separate conversation router with explicit request/response schemas. The service composes existing repositories and ConversationManager; inference behavior and runtime presets remain unchanged.
- Own one async engine/session factory per FastAPI lifespan and dispose the engine on shutdown. No migration or infrastructure changes occur at startup.
- Accept DATABASE_URL injected into process environment by a trusted operator or scoped secret agent. Never read Vault root tokens, unseal files or another application's secrets. No embedded credentials and no automatic `.env` loading.
- If DATABASE_URL is absent, retain health/stateless endpoints and return 503 for conversation operations. If an explicitly supplied URL is invalid, fail startup with a redacted error. Database connection failures map to 503 on the conversation operation.
- Deny non-loopback connection peers, browser Origin headers, and Forwarded/X-Forwarded-For/X-Forwarded-Host/X-Real-IP headers on conversation routes. Host headers confer no trust. Keep Uvicorn bound to 127.0.0.1; run one worker. Do not publish this API behind a proxy before owner-based authorization exists.
- Use POST for archive, following the current master roadmap. This supersedes the older schema design's PATCH archive row. Add PATCH for title/default preset, also specified by the current roadmap.
- Preserve exact message/answer whitespace and omit internal metadata (including fingerprints and reasoning traces) from HTTP response schemas.
- Log operation names, conversation/run UUIDs, counts, cache flags and stable error codes. Do not log message bodies, titles, request keys, DSNs or exception details that may contain SQL parameters/credentials.
- Lock active conversations and reject update/archive/delete while inference is pending, using the same conversation-row locking convention as reservation. This is preventive protection; cross-connection races and process crashes remain D15-T06 acceptance work.
- Anchor the weight-ignore rule to `/models/` so existing ORM sources are versionable. Add documentation to these sources without changing mappings or migrations.

## Effects and limits

This is a localhost development boundary, not user authentication. Any local process with access to the listener can read history. A local proxy stripping forwarding metadata cannot be distinguished from a local client; proxy exposure remains prohibited. Do not enable Uvicorn proxy-header trust for this API.

Production Vault bootstrap remains open: provision a consumer identity restricted to the application's PostgreSQL secret, then verify delivery/rotation without broad `server` access. No Vault policies, credentials or containers were modified here.

Pending-run lease recovery, whole-turn token trimming, multiworker coordination and PostgreSQL restart testing remain D15-T06. Recreating FastAPI lifespan/pool is automated separately from a full OS process restart; neither is claimed as executed against PostgreSQL until the integration tests actually run.

## Validation

HTTP/unit tests cover all routes, validation, pagination, peer/origin/proxy denial, error redaction, pool disposal, stored defaults, pending mutation rejection, ORM conversion and the unchanged stateless route. Real PostgreSQL HTTP tests and opt-in CORE tests are supplied separately; skipped cases are not acceptance evidence.

See the 2026-10-17 checkpoint in `dev_log/dev_log.md` for actual commands and results.

## Operator acceptance follow-up — 2026-10-17

The user explicitly directed this session to use the existing Vault-held password for verification. Vault was initialized but sealed; the operator used the existing unseal helpers and protected bootstrap material, then read only `secret/server/local-assistant/postgresql`. The operator credential remained in the parent process; API/test children received only DATABASE_URL for `local_assistant_app`. This authorized operator verification does not change the runtime prohibition on giving FastAPI a root token or turn operator bootstrap into production credential delivery.

Four real integrations passed, including CORE. Full pytest completed with 94 passed and zero skipped. A separate actual two-process Uvicorn check verified retained list/history and idempotent replay after restart. The original missing-environment result remains historical in the dev log. Production scoped identity and D15-T06 hardening remain open.
