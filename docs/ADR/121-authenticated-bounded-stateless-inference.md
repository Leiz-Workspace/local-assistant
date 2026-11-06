# ADR 121 — Authenticated bounded stateless inference

**Purpose:** Close the D82 stateless chat exception to authenticated local access and sanitize its error/response boundaries.

**Date:** 2026-10-23. **Status:** Accepted for security fix and tests; no running service/model configuration change.

## Finding and decision

D15 authenticated persistent/resource routers reuse direct-loopback/origin/proxy denial and reloadable owner-bound bearer principals. Legacy `POST /api/v1/chat/completions` currently has neither dependency and returns raw backend/config exception text. Its stateless behavior is not a reason to permit unauthenticated resource consumption or cross-origin model calls.

Reuse the unchanged local/authentication helpers before reading the legacy request body. Bound incoming JSON to262144bytes independently of Content-Length, reject unsupported media/oversize, then replay the complete body to normal FastAPI validation/gateway delegation. Preserve endpoint/profile/preset/messages/stateless response behavior for authenticated local callers. Do not add persistence, tools, model switching, permissions or fallback. Sanitize config/backend failures to finite public codes; log only finite outcome/profile metadata and set private/no-store/nosniff on successful responses.

This is the necessary exception to preserving all previously passed source bytes: modify only the legacy chat route plus new tests/docs. Existing auth helpers, model settings/gateway/presets, conversation/resource routers and state remain unchanged. Existing authenticated stateless compatibility tests must still pass. Health remains public and content-free; OpenAPI remains a local operator surface, not an authentication authority.

## Impact and rollback

Existing D82/P1 security milestone. Depends on private `ASSISTANT_AUTH_FILE` delivered through the existing operator workflow; missing/invalid config fails closed503, invalid/revoked credentials401, remote/origin/proxy403. Stateless callers must now supply the same bearer credential as the resource API. No token should enter URLs, source code, browser persistent stores or ordinary logs. Native model loopback8080 is an operator-only backend, not a replacement public API; network exposure, reverse-proxy/TLS/OIDC/multiworker roles remain unaccepted deployment scope.

Rollback must not silently restore the insecure route: disable stateless access or roll forward a corrected guarded implementation. Validate before/after denial tests, malformed/oversized streams, duplicate credentials, live digest reload/revocation, safe error handling and authenticated response compatibility. No production restart/deployment is part of this edit.
