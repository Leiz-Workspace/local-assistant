# Conversation API — Authenticated local operation and recovery

**Purpose:** Describe the current principal boundary, safe runtime configuration, telemetry and reproducible Day 15 acceptance.

## Runtime configuration

Use the existing PostgreSQL database and CORE container. A trusted operator supplies DATABASE_URL for `local_assistant_app` in process environment; the URL uses `postgresql+psycopg://` with credential components encoded. API startup does not run migrations, load `.env`, read bootstrap/unseal files or receive an operator Vault token.

Conversation endpoints now require a bearer credential. The raw local API token and its principal UUID are stored in the existing Vault KV v2 path `secret/server/local-assistant/api` as `api_token` and `principal_id`. The operator prepared `data/auth/principals.json`, a private 0600 file in a 0700 directory, containing only UUID/token-digest bindings. Neither artifact belongs in Git. The raw token is not stored in the auth file and must not be printed, put in command arguments or pasted into shell history.

After secure DATABASE_URL injection, run from `ai/`:

```sh
ASSISTANT_AUTH_FILE="$PWD/data/auth/principals.json" uv run uvicorn apps.api.main:app --host 127.0.0.1 --port 8000 --workers 1 --no-proxy-headers --log-level info
```

API clients send `Authorization: Bearer <token>` using the credential retrieved securely from Vault. Keep direct-loopback deployment: Origin and forwarding headers are still rejected even with a valid token. No public/reverse-proxy deployment or multiple workers are accepted here.

Missing/bad auth configuration returns 503 `auth_unavailable`. With valid configuration, missing/invalid/duplicate bearer headers return 401 plus `WWW-Authenticate: Bearer`. Missing DB configuration returns 503 `storage_unavailable` after authentication; health/stateless routes keep their existing contract. Auth config is reloaded on every request: rotate tokens by keeping the stable principal UUID and changing digest records atomically with owner-only permissions; revoked digests stop working without process restart. Tokens must be random high-entropy credentials, never passwords chosen by humans.

The authenticated principal exclusively assigns owner identity. Every conversation operation filters that owner, including manager reservation/recovery/finalization locks. Another principal sees 404 for guessed IDs and cannot replay cached answers. Metadata/owner fields in request bodies are rejected and arbitrary identity headers have no authority. Internal unscoped repositories are trusted maintenance interfaces, never exposed by the HTTP dependency.

Legacy conversations with no owner are retained unchanged and hidden from all HTTP principals. Do not automatically adopt them. A later adoption requires an explicit identity-to-record mapping, backup and review; no owner was guessed or silently backfilled in this release. Ownership currently lives in JSONB and is enforced in the application, without PostgreSQL RLS or an owner-column migration.

## HTTP contract

| Method | Path | Behavior |
|---|---|---|
| POST | `/api/v1/conversations` | Create with the authenticated owner; 201 |
| GET | `/api/v1/conversations` | Own visible conversations; limit 1–100, offset ≥ 0, include_archived=false |
| GET | `/api/v1/conversations/{id}` | Own visible conversation or 404 |
| PATCH | `/api/v1/conversations/{id}` | Set non-null title and/or preset_default |
| GET | `/api/v1/conversations/{id}/messages` | Own ascending history; limit 1–500, after_sequence ≥ 0 |
| POST | `/api/v1/conversations/{id}/messages` | Own persistent send; content, optional preset/request_key/temperature/max_tokens |
| POST | `/api/v1/conversations/{id}/archive` | Archive own idle conversation |
| DELETE | `/api/v1/conversations/{id}` | Soft-delete own idle conversation; 204 |

Lists are JSON arrays. Deleted conversations/history return 404; archived own history remains readable. Omitted send preset uses the stored default. Completed same-key requests with identical generation parameters replay; conflicting/pending/failed/interrupted requests return 409. Keep the effective preset stable when replaying a request originally sent without an explicit preset. Fast requests need at least the existing 512-token answer reserve; other presets retain their existing policy.

Errors use `detail.code` and a safe `detail.message`; request validation uses FastAPI's 422 details. Internal metadata, request fingerprints and reasoning traces are excluded from response schemas. Message/answer whitespace is preserved.

## Leases, context and pool logs

Persistent inference has a manager owner UUID, 120-second database-clock lease and 30-second heartbeat. Cleanup records cancellation as interrupted when possible. Owned expired runs recover lazily on later send or explicit per-conversation recovery; late owners cannot finalize. No automatic retry/replay occurs for interrupted/failed requests. Use a new key for an intentional new attempt. Unowned historical pending runs require operator verification, not a startup bulk interruption. Drain active runs before rolling back to pre-lease code; old/new writers must not overlap.

Recent context preserves system instructions, complete user/assistant turns and current input beyond the old first-500 history cutoff. Actual CORE template/tokenizer and unchanged preset rules trim only oldest complete pairs. Original transcript remains intact. Irreducible current/system overflow returns 422 and a failed run; invalid output limits are rejected without pruning history.

Application logging enables INFO audit events under the default Uvicorn launcher while preserving existing deployment handlers. Pool telemetry exports structured JSON event `database_pool_metrics` every 30 seconds and on timeout/shutdown. Fields include checkouts, checkins, invalidations, timeouts, peak_checked_out, pool_size, checked_out and overflow. The sampler holds no DB connection. Pool acquisition is bounded to 10 seconds; timeout maps to safe 503 `pool_timeout`. No SQL parameters, DSNs, bearer values or driver exception text are exported. Logs are the V1 export channel; no public diagnostic endpoint was added.

## Verification

Inject the app DATABASE_URL without logging it, then run:

```sh
uv run python -m pytest tests/test_conversation_auth.py tests/test_application_logging.py tests/test_conversation_api.py -q
LOCAL_ASSISTANT_LIVE_E2E=1 uv run python -m pytest tests/integration/ -q -rs
LOCAL_ASSISTANT_LIVE_E2E=1 uv run python -m pytest tests/ -q -rs --tb=short
```

Tests create their own private auth configs/principals and isolated conversation UUIDs. Cleanup follows FK order. The worker-crash test kills only its disposable Python worker. A pool-reconnect test terminates only the backend PID it created itself. No test implicitly restarts PostgreSQL/Vault/CORE.

Current full result: **151 passed in 9.45s**, zero skipped, no exclusions, against real PostgreSQL and CORE. A separate two-process Uvicorn check used the real Vault API credential to prove anonymous denial, CORE response persistence, history/replay after process restart and secret-free metric export. Both temporary API processes and their conversation were removed.

The historical `tests/test_core_acceptance.py` calls CORE at import and prints its checks without pytest assertions. Ensure CORE is ready before the full suite; pytest green is not a model-quality scorecard. Missing DB/CORE/auth prerequisites must not be reported as accepted integration.

## Shared PostgreSQL recovery drill

Read ADR-018 before rerunning the operator script. Choose a new ignored backup directory; existing directories are deliberately not overwritten. The default performs protected backups and isolated restore only:

```sh
uv run python scripts/postgres_recovery_acceptance.py --backup-directory data/backups/manual-recovery-drill
```

An explicitly planned restart additionally uses `--execute-restart`. The script checks the existing named volume, absence of active consumer transactions/app connections/pending runs, and Keycloak discovery both before backup and immediately before restart. It creates private archives for every non-template database plus globals, preserves ownership/privileges, records SHA-256, restores Local Assistant into a uniquely named temporary database, compares rows and normalized owners/ACLs, and removes only that probe. Only verified restore permits restart; source rows and Keycloak are checked after recovery. No second service/instance is created.

Final accepted artifacts: `data/backups/t06-acl-verified-20261018/manifest.json` plus four custom DB archives and `globals.sql`; manifest flags `restore_verified`, `restore_security_verified`, `restart_verified` are true. All files are 0600 within a 0700 directory. Globals include role password hashes and archives contain private application data: retain them outside Git and never attach them to code review. Their hashes, permissions, post-restart owner/ACL fingerprint and canary/probe cleanup were independently checked.

On failure, retain the protected artifacts. Start/inspect the same container and volume first. Do not initialize a replacement volume or automatically restore over a production DB; review archive/global-role recovery explicitly. Backups include the identified temporary canary (its ID is recorded in the manifest); source cleanup removes it after acceptance. Off-host/full-cluster disaster recovery and ongoing backup retention are separate operational work.

Day 15 is accepted for authenticated localhost operation. OIDC/scoped production Vault identity, production multiworker/load certification, full Unit of Work inversion and explicit legacy adoption remain tracked future work.
