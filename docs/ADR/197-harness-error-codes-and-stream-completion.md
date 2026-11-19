# ADR-197: Harness error codes and stream completion (addendum to ADR-181)

**Purpose:** Make the opt-in product harness report client errors and truncated answers with finite codes of their own, instead of a 500, a generic 502 or a silently complete-looking answer, and let the CLI show those codes. This is an addendum to [ADR-181](181-checkout-cli-desktop-and-readonly-specialist-runs.md); the opt-in composition, the admission lock and the browser boundary it chose are unchanged.

**Date:** 2026-11-19. **Status:** ACCEPTED by the owner's choice of "Phase 1: quick fixes" ("Pha 1: sửa nhanh") from the 2026-11-19 code quality review (`docs/reviews/2026-11-19-code-quality-review.md`, section 4, Phase 1 items a to d). Implemented on branch `fix/harness-error-codes-and-stream-completion`, cut from `develop` `cabb1d7`. One part of item (b) is deferred; see Not changed.

## Context

- **ADR-181** asked for finite safe failure codes, a separate browser cookie/Origin/CSRF boundary and "real native SSE". The review found five places where the implementation falls short of that:
  - **H-m1.** `ApiClient.request` ignored the error body and raised `http_<status>`. `history_unavailable`, `harness_closed`, `workspace_unavailable` and `auth_unavailable` all reached the user as `http_503`; `run_capacity` and `generation_capacity` as `http_429`.
  - **H1, C-m1.** `ChatInput.messages` was `list[dict[str, str]]`. A turn with role `tool`, an extra key or whitespace-only content reached `compose_context`, whose `ValueError("invalid_messages")` `/chat` reported as 502 `inference_unavailable` on the default path.
  - **H8.** `bounded_json` read the browser request body under `asyncio.timeout(10)` but let the `TimeoutError` escape. No handler caught it, so a stalled body got a 500.
  - **C-m2.** `ProductInference.stream`, the web UI path, forwarded events until `[DONE]` without reading `finish_reason`. The non-stream gateway rejects `finish_reason: length` through `classify_completion` (`apps/api/runtime/presets.py`); the stream presented the same truncated answer as complete.
  - **H18.** `HarnessRoute` inherited `ProtectedStatelessRoute`, which requires `Content-Type: application/json` on every request, bodiless GET and DELETE included. `POST /api/v1/harness/ui-pairings` was an app-level route in `browser.py`, outside the route guard and the audit line.
- **Evidence binding.**
  - `apps/harness/routes.py` is listed in HAR-006 v2's `UNCHANGED_SOURCES` (`benchmarks/context_har006_v2.py`). That list feeds only the runner's S3 gate at run time, and ADR-195 decision 5 already runs v2 only from its recorded commit. No test compares those bytes.
  - `apps/harness/inference.py` is in the `SOURCES` of several context benchmarks and in their receipts. These hashes feed `--recheck` and receipts, not tests.
  - ADR-193's "byte-unchanged" list describes the scope of that change, not a standing rule.

## Decision

1. **The CLI shows the server's code (H-m1).**
   - On a status of 300 or more, `apps/cli/client.py` parses a JSON body of at most 16 KiB. It takes `detail.code`, then `error.code`, then a top-level `code`.
   - The code must fully match `[a-z][a-z0-9_]{0,63}`. The client-local transport codes `server_unavailable` and `invalid_server_response` are refused, so a server cannot make the desktop launcher believe that no server is listening.
   - The exit category still comes from the HTTP status. Any other body (invalid, oversized, no code, a code outside the pattern) falls back to `http_<status>`. No other body text is shown.
2. **`/chat` messages are typed (H1, C-m1).**
   - Each turn is a closed model like the stateless `ChatMessage`: role `system`, `user` or `assistant`; content of 1 to 262,144 characters with some non-whitespace text; no extra keys. At most 256 turns, as before.
   - Every `/chat` validation failure answers 422 `{"detail": {"code": "invalid_context_request"}}`, the code the history-policy path already used, instead of FastAPI's default detail, which echoes the input. Other harness routes keep the default validation response.
   - The CLI sends only `user` and `assistant` turns with the text the user typed, so nothing it sends legitimately is newly refused.
3. **A stalled browser body is a 408 (H8).** `bounded_json` turns its timeout into `HTTPException(408, request_timeout)`. The browser error handler returns it in the usual envelope, `{"error": {"code": "request_timeout", ...}}`. External cancellation still propagates. The 10-second bound is now the module constant `BODY_SECONDS`.
4. **The stream verifies completion (C-m2).**
   - `stream()` keeps the last `finish_reason` and the streamed `delta.content`. At `[DONE]` it classifies them with `classify_completion`, the function the non-stream gateway uses.
   - Anything but PASS raises `IncompleteCompletion` (a `GatewayError`) before `[DONE]` is forwarded. That covers `length`, a missing or other `finish_reason`, and an answer with no text.
   - The browser SSE path then sends `data: {"error":{"code":"incomplete_completion",...}}` and `data: [DONE]`. The deltas already streamed stay on screen, followed by the error.
   - Other stream failures still end with `inference_unavailable`. A stream cut before `[DONE]` still raises `incomplete_stream`. `llama_gateway.py` is unchanged.
5. **The harness has its own route class (H18).**
   - `HarnessRoute` now derives from `APIRoute`. It still requires a direct local client and a bearer principal, bounds the body at 262,144 bytes (413 `request_limit`), adds the private no-store headers and `X-Request-ID`, and writes the `product_api_request` audit line.
   - It requires `application/json` only when the request carries a body. A bodiless GET or DELETE without `Content-Type` now succeeds; the CLI may keep sending the header. The body is read before the media check, so an oversized non-JSON body now gets 413 rather than 415.
   - `POST /api/v1/harness/ui-pairings` moves into the harness router and so gets the same guard, private headers, request identifier and audit line. A JSON body is optional.

## Not changed

- **Status of client-correctable context failures on default `/chat`.** The review also asked to answer `context_overflow`, `invalid_context`, `invalid_token_budget` (`InferenceFailure` with status 422) and `strict_context_would_trim` and `evidence_limit` (`ValueError` from the composer) with 422 and their own code on `/chat` without `history_policy`. This is deferred. `benchmarks/tests/test_context_har006_v2.py::test_11_api_mapping_observation_records_current_behaviour` is part of the frozen HAR-006 v2 benchmark. Its O1 observation asserts today's 502 `inference_unavailable` (API_MASKED), and that observation is the `api_observation` of v2's software record. The change would fail that test, so it waits for an owner decision on that test. Changing the mapping is HAR-006 v2 follow-up 3 (`docs/HAR006_V2_RESULT.md`).
- **`/runs` failure codes.** The run error code is persisted in the signed history, whose closed set is `ERRORS` in `src/infrastructure/harness_history.py`. Reporting `context_overflow` or `strict_context_would_trim` there would need new persisted codes, so `/runs` still records `run_failed`.
- **One browser error envelope, one body reader and one pairing store** (the rest of H8) belong to Phase 4. **A shared admission and error mapping for the four CORE paths** (the rest of H1) belongs to Phase 6, together with the `llama_gateway.py` cleanup that draft PR #90 touches.

## Consequences

- **Externally visible changes.**
  - CLI: errors print the server's code, for example `{"error": "history_unavailable"}` instead of `{"error": "http_503"}`. Exit codes are unchanged.
  - `/chat`: an invalid turn gets 422 `invalid_context_request` instead of 502 `inference_unavailable` (default path). A malformed field elsewhere in the body gets the same finite body instead of FastAPI's echoing detail; the status stays 422.
  - Browser POST routes: a stalled body gets 408 `request_timeout` instead of 500.
  - Web UI: an answer cut by the output budget ends with the `incomplete_completion` error event instead of looking complete.
  - Harness API: bodiless GET and DELETE need no `Content-Type`. A body without `application/json` still gets 415. `ui-pairings` responses gain `Cache-Control: private, no-store`, `X-Content-Type-Options: nosniff` and `X-Request-ID`, and the route is audited.
- **No persisted change.** The signed run history, its error codes and the evidence files are unchanged.
- **Rebase with draft PR #90.**
  - The edits in `routes.py`, `browser.py` and `inference.py` avoid the lines PR #90 changes. `git merge-tree` of this branch with `feat/adr195-special-literals` (`eaff4cb`) reports no conflict.
  - One PR #90 test needs a fixture update after the merge. `tests/test_core_request_builders.py::test_product_inference_stream_body_is_sealed` streams a delta without `finish_reason`, which now raises `IncompleteCompletion`. Its fixture should end with `finish_reason: "stop"`, as llama.cpp does.

## Rollback

Revert the five `fix:` commits of the branch. No state, migration or configuration is involved; the CLI and the server can be rolled back independently.

## Validation

Run from the worktree with the project virtual environment, `-p no:cacheprovider --basetemp=$HOME/.cache/wt/pt-p1-harness -n 2`. These are software tests only; no model was called and no model quality was measured.

- `pytest tests/test_aevra_branding.py tests/test_aevra_desktop.py tests/test_context_inspection.py tests/test_context_token_budget.py tests/test_harness_history.py tests/test_history_summary.py tests/test_product_assets.py tests/test_product_cli.py tests/test_product_context_policy.py tests/test_product_generation.py tests/test_product_harness.py tests/test_product_inference.py tests/test_review_output_contract.py tests/test_source_output_contract.py tests/test_working_state.py tests/test_review_approval_cli.py tests/test_readonly_browser.py -q`: 665 passed, 0 skipped.
- `pytest benchmarks/tests/test_context_budget.py benchmarks/tests/test_context_har006_v2.py benchmarks/tests/test_context_retention.py benchmarks/tests/test_context_state.py benchmarks/tests/test_context_summary_dev_plus.py benchmarks/tests/test_context_summary_heldout.py benchmarks/tests/test_context_summary.py benchmarks/tests/test_context_summary_v2.py benchmarks/tests/test_harness_stream_timing.py benchmarks/tests/test_semantic_review_run.py benchmarks/tests/test_context_policy_probe.py -q`: 280 passed, 0 skipped. This includes HAR-006 v2 `test_11` and `test_12`, which post to `/chat`.
- Regression tests added:
  - CLI: each envelope shape and their precedence, the 64-character and 16 KiB boundaries, oversized, invalid and non-object bodies, codes that fail the pattern, client-local codes, and the printed code with its exit category.
  - Route guard: bodiless GET and DELETE without `Content-Type`, 415 for non-JSON bodies on POST and DELETE, the 262,144-byte boundary, `ui-pairings` guard, audit and capacity.
  - `/chat`: every invalid turn shape on both paths without echo or admission, the 0, 256 and 257 turn bounds, the content bound, and the accepted roles reaching inference as plain dictionaries.
  - `bounded_json`: timeout, cancellation and the size boundary, plus a stalled body through the real middleware and handler.
  - Stream: `stop` shapes that pass; `length`, missing, `tool_calls` and textless endings that fail; a stream without `[DONE]`; the SSE error event through a fake stream and through the real `ProductInference`.
- The full suite was not run here; CI runs it.
