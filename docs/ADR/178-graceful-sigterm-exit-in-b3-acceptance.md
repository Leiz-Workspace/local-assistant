# ADR 178 — Graceful SIGTERM exit in B3 acceptance

**Purpose:** Fix a B3 runner acceptance rule that rejects the expected exit status of a correctly stopped uvicorn application, close older gaps in the same post-panel cleanup check found by review, then allow exactly one more B3 panel.

**Status:** ACCEPTED, 2026-11-07. On 2026-11-06 the owner approved "Duyệt B3 mới": fix the runner so it accepts the re-raised SIGTERM exit only when the complete shutdown is proven by the audit, then run exactly one new panel. Product activation, model/default changes, downloads and the D90 release remain out of scope.

## Context

- The ADR176 replacement B3 (`data/backups/d74-main-integration-adr176/result.json`, private) met every row criterion. It produced 4/4 `EXACT_COMPLETE_PCM` speech rows at 2.247–3.241 s server time and 2/2 `CORRECT_NO_SPEECH` negatives. Stage counts were 6/4/4/4, readiness was 1 and all 3 workers joined. The owned CORE exited 0 and was reaped.
- The run still ended `NOT_PASS` with `main_voice_call_budget_or_cleanup`, only because `web_exit` was `-15`. The runner required `web.returncode == 0`. Because that check failed first, the next criterion (borrowed CORE alive after application shutdown) was never evaluated.
- uvicorn 0.54.0 (`uvicorn/server.py`, `Server.capture_signals`) records SIGTERM, completes the graceful shutdown including the ASGI lifespan, and then calls `signal.raise_signal` with the captured signal. Python's default SIGTERM disposition then ends the process, so `Popen.returncode` is `-signal.SIGTERM` (−15) after a fully successful shutdown. Exit 0 is not reachable when uvicorn is stopped with SIGTERM.
- The runner starts uvicorn with `--log-level warning`. uvicorn's own `Application shutdown complete.` line is INFO, so it does not appear in the audit. The voice lifespan writes its own INFO events, which do appear.
- A pre-merge adversarial review of this change found three older gaps in the same post-panel check, all present before this ADR:
  - **Worker joins.** The runner counted `voice_native_worker_joined` lines without reading `exit=` or `forced=`. `Worker.close` (`src/infrastructure/voice/ipc.py`) kills a worker with SIGTERM/SIGKILL when the close handshake or exit takes longer than 3 s. A forced or crashed worker is logged at INFO and does not raise. Such a run could therefore pass cleanup.
  - **Release.** `release_HTTP_status` and `status_after_release` were recorded but never checked.
  - **Credentials on the failure path.** On the credential-logged failure path, the `finally` block copied the raw `app.log`, credential included, into the evidence directory.

## Decision

1. `benchmarks/scripts/main_voice_integration.py` adds `graceful_web_exit(returncode, audit)`, and the campaign records the result as `web_shutdown_graceful`. A shutdown is graceful only when all of these hold:
   - The exit code is the integer `0` or `-signal.SIGTERM`. Any other code fails, including SIGKILL, SIGINT, positive codes, non-integers and `None`.
   - The audit contains each of these lifespan events exactly once, as INFO lines in the runtime log format and in this order: `voice_service_closed`, `voice_identity_closed`, `gpu_admission_unbound`, `voice_managed_gpu_paths_restored`, `voice_manifest_closed`. The last of these is written by the manifest finalizer, which runs only when no runtime, admitted call or poisoned admission remains.
   - The audit contains no `voice_shutdown_quarantined`, no `Traceback` and no ERROR or CRITICAL line, whether in the runtime format or in uvicorn's default `ERROR:` format.
2. The post-panel verdict moves into pure functions: `audit_summary(audit, returncode)` and `verify_cleanup(result, server)`. `run()` calls both, and tests can exercise them. `main_voice_call_budget_or_cleanup` is raised before the borrowed CORE is consulted when any of these fails:
   - stage counts are exactly 6/4/4/4;
   - exactly one readiness call;
   - exactly three worker join lines;
   - `workers_joined_clean`: every join line is INFO, roles are distinct, and each has `exit=0 forced=False`;
   - `web_shutdown_graceful` is true. This replaces `web.returncode != 0`; `web_exit` is still recorded unchanged;
   - the release returned HTTP 200 and the status after release is `idle` with no error.

   Only after all of these pass does `main_voice_borrowed_core_not_preserved` check that the CORE is still alive and has not failed.
3. The worker and release conditions are stricter than before. They reject only a teardown that was forced, crashed or left the session in a non-idle or error state, which is a real cleanup fault and not an acceptable result. The ADR176 audit, release status and result meet them: 3 joins, all `exit=0 forced=False`; HTTP 200; `idle` with no error.
4. When the runner has to keep a raw application log on a failure path, `retain_audit` replaces the per-run bearer token and pairing code with `[REDACTED_CREDENTIAL]` before writing it.
5. Every other criterion stays exactly as before:
   - no credential in the audit;
   - borrowed CORE alive and unfailed after application shutdown;
   - exact prior transcript, answer and audio;
   - at most 4 s complete server response;
   - no retry;
   - same inputs, models, voice and CORE command.
6. `source_snapshot` binds this ADR, in addition to ADR174–176, so the new run is tied to the documented rule.

## Scope of the new B3

Exactly one panel in a new directory, `data/backups/d74-main-integration-adr178`, using the `prepare` and `run --root` flow of ADR176. The rules are those of ADR176:
- a preflight stop is reported as a stop and is not a B3 result;
- a failed panel stays failed.

The first and ADR176 campaigns keep their recorded `NOT_PASS` results. Applying the new rule to the ADR176 audit would have accepted its shutdown. That is recorded here as a fact only: it does not relabel that run, because its CORE-alive criterion was never evaluated. Physical first-audible measurement, room/short/quiet speech and product/default decisions remain B4/D74 gates.

## Validation, migration and rollback

`benchmarks/tests/test_main_voice_integration.py` covers:
- **Exit and shutdown events**
  - acceptance of exit 0 and −15 with the complete shutdown, including when INFO or WARNING lines from other loggers fall between the voice events;
  - refusal of other or non-integer exit codes;
  - refusal of a missing, reordered, duplicated, non-INFO or suffixed event;
  - refusal of quarantine, traceback, ERROR, CRITICAL and uvicorn `ERROR:` lines anywhere in the audit, before or after the shutdown events, whatever the exit code.
- **Worker joins:** acceptance of three clean joins; refusal of forced, nonzero, −15, duplicate-role, unformatted or suffixed joins.
- **Wiring through `verify_cleanup`**
  - −15 with a complete audit reaches the borrowed CORE check;
  - a dead or failed CORE raises `main_voice_borrowed_core_not_preserved`;
  - each of these raises `main_voice_call_budget_or_cleanup` without consulting CORE: a kill or crash exit, a missing event, a forced join, a wrong call count, missing readiness, release HTTP 409, a non-idle status, an error status or a missing status.
- **Credentials:** the retained raw log has both credential values redacted, and other content is kept byte for byte.

The tests use synthetic audits only, without private evidence. No data migration is needed. Rollback restores `web.returncode != 0` in place of `web_shutdown_graceful`, or reverts this change. Recorded evidence is not affected.
