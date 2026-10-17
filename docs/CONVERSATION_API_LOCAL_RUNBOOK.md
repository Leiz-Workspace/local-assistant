# Conversation API — Local development and acceptance

**Purpose:** Describe safe runtime injection and reproducible D15-T05 acceptance without storing credentials in the repository.

## Runtime

Use the existing PostgreSQL database and CORE runtime. Do not create a new database service or run migrations from API startup. A trusted operator or already configured scoped Vault Agent must inject `DATABASE_URL` into the process environment using the existing `local_assistant_app` credential. Its driver prefix must be `postgresql+psycopg://`; percent-encode credential components when building the URL. Do not use a migrator/superuser credential or read `vault-init.json` to bootstrap the API.

This change consumes the injected URL; it does not implement or claim a production Vault auth flow. Never print the URL, use shell tracing, or paste secrets into command arguments, Git or the dev log. Remove inherited sensitive environment values when finishing the development session.

Once environment injection is complete, run from `ai/`:

```sh
uv run uvicorn apps.api.main:app --host 127.0.0.1 --port 8000 --workers 1 --no-proxy-headers --log-level info
```

Without DATABASE_URL, the conversation API returns 503 while existing health/stateless routes remain registered. Bind only to loopback. Conversation requests with Origin or forwarding headers are rejected. Browser UI, reverse proxy exposure, and multiple users/workers require later security and coordination work.

## Contract

| Method | Path | Behavior |
|---|---|---|
| POST | `/api/v1/conversations` | Create; 201; optional title/profile/preset_default |
| GET | `/api/v1/conversations` | List; limit 1–100, offset ≥ 0, include_archived=false |
| GET | `/api/v1/conversations/{id}` | Read a visible conversation |
| PATCH | `/api/v1/conversations/{id}` | Set non-null title and/or preset_default |
| GET | `/api/v1/conversations/{id}/messages` | Ascending history; limit 1–500, after_sequence ≥ 0 |
| POST | `/api/v1/conversations/{id}/messages` | Send content; optional preset/request_key/temperature/max_tokens |
| POST | `/api/v1/conversations/{id}/archive` | Archive an idle conversation |
| DELETE | `/api/v1/conversations/{id}` | Soft delete; 204 |

Lists are JSON arrays. Continue offset/sequence pagination until an empty or short page; ordering uses the existing repository contract. Deleted conversations and their histories return 404; archived histories remain readable. A send without preset uses the stored default. Use the same request_key and generation parameters to replay a completed turn; pending/failed/mismatched keys return 409. Keep effective preset stable when replaying a request originally sent without an explicit preset.

Errors use `detail.code` and a safe `detail.message`; request validation uses FastAPI's standard 422 details. Expected statuses include 403, 404, 409, 422, 502, 503 and 504. Responses exclude internal metadata and reasoning traces. Runtime logs require the deployment's normal logging configuration.

## Verification

```sh
uv run python -m pytest tests/test_conversation_api.py tests/test_api_health.py tests/test_llama_gateway.py tests/test_runtime_presets.py tests/test_runtime_auto.py -q
uv run python -m pytest tests/integration/ -q -rs
LOCAL_ASSISTANT_LIVE_E2E=1 uv run python -m pytest tests/integration/test_conversation_http_persistence.py -q -rs
uv run python -m pytest tests/ -q
```

The HTTP PostgreSQL tests create uniquely identified conversations and delete only those rows in foreign-key order during cleanup. They recreate the API lifespan and pool to verify persistence. The live variant calls the already running CORE gateway; it never starts or stops containers. An actual two-process Uvicorn restart was also verified during the 2026-10-17 operator acceptance. PostgreSQL container restart and crash recovery remain separate D15-T06 acceptance.

`tests/test_core_acceptance.py` is a historical script making inference requests during import. If CORE is absent, full pytest collection fails. To measure the remaining suite explicitly, use:

```sh
uv run python -m pytest tests/ --ignore=tests/test_core_acceptance.py -q -rs
```

That exclusion is not a full-suite PASS. Missing DATABASE_URL causes integration SKIPs, not successful persistence acceptance.

## Latest operator verification — 2026-10-17

The existing app password was available in Vault. Vault was sealed and needed the established operator unseal procedure before reading the app secret. The authorized operator parent used the protected local bootstrap mechanism; only the application DATABASE_URL entered the API/test child environment. Never pass the operator token to application runtime.

With CORE ready and `LOCAL_ASSISTANT_LIVE_E2E=1`, integration completed **4 passed in 1.18s** and full pytest completed **94 passed in 6.48s**, zero skipped and no exclusions. A separate real process restart check confirmed exact history and cached replay. The live test now requests 512 output tokens to satisfy the unchanged runtime answer reserve; the earlier 128-token fixture correctly received HTTP 422.

## T06 lease and context behavior

Each persistent inference now has an owner UUID, a 120-second database-clock lease and a 30-second heartbeat. A cancelled request is recorded as interrupted when cleanup succeeds. A killed worker is recovered lazily on a later send, or by an explicit manager `recover_expired(conversation_id)` call, once its owned lease expires. A completed request replays; failed/interrupted requests retain 409 semantics under the same key. A new intentional attempt uses a new key. No automatic resend is performed.

Historical pending records without lease ownership are left unchanged. Verify the owning worker is gone before any operator repair. Do not bulk-interrupt pending records on startup. Before rolling back to pre-lease code, drain active inference; old/new writers must not overlap. API remains restricted to one worker and direct localhost access until the remaining authorization/deployment gates are accepted.

The manager reads recent history beyond the old first-500 cutoff, preserves system instructions and selects complete prior user/assistant pairs. Persistent inference then trims oldest pairs using CORE's actual chat template/tokenizer and the unchanged preset policy. Original messages remain in PostgreSQL. Irreducible current/system input overflow returns 422 and a failed run; it is never silently truncated. Invalid output limits are rejected without attempting to prune history.

With the same environment injection used above:

```sh
uv run python -m pytest tests/test_conversation_context.py tests/test_llama_adapter.py -q
LOCAL_ASSISTANT_LIVE_E2E=1 uv run python -m pytest tests/integration/test_conversation_hardening.py -q -rs
LOCAL_ASSISTANT_LIVE_E2E=1 uv run python -m pytest tests/ -q -rs --tb=short
```

Hardening tests use isolated conversation UUIDs and clean them in FK order. The crash test SIGKILLs only its own temporary Python worker, never PostgreSQL, Vault or CORE. The pool probe runs 12 blocked fake inferences and records zero checked-out DB connections during inference; this is an acceptance probe, not production pool metrics export.

Latest T06 result: **127 passed in 9.27s**, zero skipped. ADR-017 defines the remaining owner isolation, runtime telemetry and shared DB backup/restore/restart gates; T06 remains PARTIAL.
