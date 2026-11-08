# Local Assistant

Local Assistant is a local-first personal AI assistant that runs on one Ubuntu home server with an NVIDIA RTX 4070 Ti SUPER (16 GiB). The CORE model `qwen3.5-9b-core` (Qwen3.5-9B, GGUF Q6_K) is served by a locally built `llama-server` on `127.0.0.1:8080`. A FastAPI application on `127.0.0.1:8000` adds authenticated chat with runtime presets, optional PostgreSQL-backed conversations, files and memory, web search through a local SearXNG instance, and reviewed coding tools over registered workspaces. Voice is an optional composition that is off by default.

## Current status

This is an engineering candidate, not a release: there is no tag and no GitHub Release, nothing is deployed to the Home Server, and voice (`ASSISTANT_VOICE_ENABLED`) stays off by default. Open owner decisions and the evidence behind them are tracked in:

- [Release candidate status](docs/RELEASE_CANDIDATE_STATUS.md)
- [Outstanding work](docs/OUTSTANDING_WORK_STATUS.md)
- [Master roadmap](docs/LOCAL_ASSISTANT_MASTER_ROADMAP.md)
- [D90 release decision dossier](docs/D90_RELEASE_DECISION_DOSSIER.md)
- [Development log](dev_log/dev_log.md)

## Repository layout

| Path | Contents |
|---|---|
| `src/` | `domain/` models, `application/` services and ports, `infrastructure/` adapters. Domain logic stays independent of HTTP, databases and inference. |
| `apps/` | Entry points: `api/` (FastAPI), `web/`, `voice/`, `voice_trial/`. |
| `tests/` | pytest suites, integration tests and document/audio/image fixtures. |
| `benchmarks/` | Evaluation runners; benchmark tests live in `benchmarks/tests/`. |
| `configs/` | Model registry (`models.yaml`), pinned runtime and evaluation configuration. |
| `migrations/` | Alembic migrations for the `assistant` schema (`0001` to `0006`). |
| `scripts/` | Operator tooling, including `start-core.py` and `full_regression.py`. |
| `docs/` | Roadmap, status, ADRs (`docs/ADR/`), protocols, results and evidence. |
| `dev_log/` | Development log. |

Model weights (`models/`), the llama.cpp build (`runtimes/llama.cpp/`) and local data (`data/`) are ignored by Git and exist only on the server.

## Development

Run commands from this directory and use `uv`, not `pip`:

```bash
uv sync --locked --dev
uv run --no-sync python -m pytest tests/test_reasoning_profile.py -q   # focused
uv run --no-sync python -m pytest tests benchmarks/tests -q            # broad
uv tool run --offline ruff check --isolated --select E4,E7,E9,F <files>
uv tool run --offline ruff format --check <files>
```

Integration tests need the configured services and credentials; without them some skip themselves and others fail (CI excludes the latter through `.github/ci/hosted-runner-exclusions.txt`). A skip or a missing prerequisite is not an acceptance result, and a green test run is not a model-quality measurement. Keep the virtual environment on Python 3.12 for now (see the Vault TLS note below).

## Run the MVP locally

Everything binds to loopback. Use three terminals (CORE, API and a client) and set the same `AUTH_DIR` (step 2) in the API and client terminals.

### 1. Start CORE

```bash
uv run --no-sync python scripts/start-core.py
```

The script reads `configs/models.yaml` and starts `runtimes/llama.cpp/build-cuda/bin/llama-server` with alias `qwen3.5-9b-core` on `127.0.0.1:8080` (context 32768, `--parallel 1`, `--n-gpu-layers 99`, no multimodal projector). It holds about 8.4 GiB of VRAM. Only one model serves port 8080, so the `unrestricted` chat profile answers 409 `inference_unavailable` while CORE is loaded.

### 2. Create an auth file

Every API route except health needs `Authorization: Bearer <token>`. `ASSISTANT_AUTH_FILE` points to a JSON file that stores only the SHA-256 of each token:

```json
{"principals": [{"id": "<principal-uuid>", "token_sha256": "<64 lowercase hex characters>"}]}
```

`apps/api/core/conversation_auth.py` refuses the file unless it is a regular file (not a symlink) owned by the user that runs the API, with no group or other permission bits (use 0600), at most 64 KiB, with 1 to 100 principals and no other keys. Tokens must be 32 to 512 ASCII characters without whitespace. The file is re-read on every request, so replacing a digest takes effect without a restart. For a local run, this creates a random token outside the repository, keeps the raw token only in a 0600 curl header file and never prints it (it refuses to overwrite existing files):

```bash
export AUTH_DIR="$HOME/.local/share/local-assistant-auth"   # outside the repository
install -d -m 700 "$AUTH_DIR"
python3 - "$AUTH_DIR" <<'EOF'
import hashlib, json, os, secrets, sys, uuid

root = sys.argv[1]
token = secrets.token_urlsafe(48)  # 64 URL-safe ASCII characters
config = {"principals": [{"id": str(uuid.uuid4()),
                          "token_sha256": hashlib.sha256(token.encode()).hexdigest()}]}

def write_private(name, text):
    fd = os.open(os.path.join(root, name), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(text)

write_private("principals.json", json.dumps(config))
write_private("curl-auth-header", f"Authorization: Bearer {token}\n")
EOF
```

The operator's existing principal file and its Vault-held token are described in the [conversation runbook](docs/CONVERSATION_API_LOCAL_RUNBOOK.md). Database rows belong to the principal UUID: if a principal is later removed, its rows stay in the database but no HTTP client can reach them.

### 3. Start the API

```bash
ASSISTANT_AUTH_FILE="$AUTH_DIR/principals.json" \
uv run --no-sync uvicorn apps.api.main:app --host 127.0.0.1 --port 8000 --workers 1 --no-proxy-headers
```

Without `DATABASE_URL` the API serves stateless chat and the no-DB features you enable. The log shows `conversation_storage_disabled reason=missing_database_url`, and conversations, files and memory answer 503 (`storage_unavailable`, `file_storage_unavailable`, `memory_unavailable`).

### 4. Enable features (optional)

Set flags in the environment of the uvicorn command. A flag is on only when set to exactly `1`; every flag defaults to `0`. If an enabled feature lacks its configuration or a prerequisite feature, startup aborts instead of running without it. Flags marked DB take effect only when `DATABASE_URL` is set; without it they are ignored and their endpoints answer 503. Conversations need only `DATABASE_URL`.

| Flag | Enables | Requires |
|---|---|---|
| `ASSISTANT_WEB_SEARCH_ENABLED` | `POST /api/v1/web/search`, cited answers | SearXNG on `127.0.0.1:8889` and CORE at query time |
| `ASSISTANT_WORKSPACE_ENABLED` | Read-only workspace info, inventory, read, search, symbols | `ASSISTANT_WORKSPACE_CONFIG_FILE` (owner-only 0600 JSON) |
| `ASSISTANT_WORKSPACE_EXPLAIN_ENABLED` | Source-cited explanations | workspace |
| `ASSISTANT_WORKSPACE_DIAGNOSE_ENABLED` | Cited diagnoses; nothing is executed | workspace |
| `ASSISTANT_APPROVAL_ENABLED` | Explicit approval requests | workspace |
| `ASSISTANT_PATCH_ENABLED` | Patch proposals and applying approved patches | workspace, approval |
| `ASSISTANT_CHECKPOINT_ENABLED` | Private git checkpoints and recovery | patch; `ASSISTANT_CHECKPOINT_ROOT` (existing 0700 directory outside every workspace root) |
| `ASSISTANT_CHECKS_ENABLED` | Approved snapshot checks | checkpoint; `ASSISTANT_CHECKS_ROOT`, `ASSISTANT_CHECKS_PYTHON_PATH`, `ASSISTANT_CHECKS_PYTHON_SHA256`, `ASSISTANT_CHECKS_STDLIB_ROOT`, `ASSISTANT_CHECKS_RUFF_PATH`, `ASSISTANT_CHECKS_RUFF_SHA256` |
| `ASSISTANT_CODING_WORKFLOW_ENABLED` | Reviewed coding workflow | workspace, approval, checkpoint, checks |
| `ASSISTANT_CODING_WORKFLOW_CONTROLS_ENABLED` | Bounded workflow controls | coding workflow (without it this flag is ignored) |
| `ASSISTANT_FILES_ENABLED` (DB) | File storage, extraction, DOCX/XLSX, OCR | `ASSISTANT_FILES_ROOT` (default `data/files`; 0700, owned by the API user) |
| `ASSISTANT_MEMORY_ENABLED` (DB) | Memory settings, consents, records, export | the least-privilege `local_assistant_app` role |
| `ASSISTANT_INGESTION_ENABLED` (DB) | Indexing files into Qdrant | files; `ASSISTANT_INGESTION_CONFIG_FILE`. Creates a real Qdrant collection, so it needs owner approval first |
| `ASSISTANT_RETRIEVAL_ENABLED` (DB) | Dense retrieval | ingestion and its owned collection |
| `ASSISTANT_GROUNDED_ENABLED` (DB) | Grounded answers | retrieval |
| `ASSISTANT_VOICE_ENABLED` | Voice composition | Keep `0`. Read only by the voice entry point `apps.api.voice:create_app` (with `ASSISTANT_VOICE_MANIFEST`, `ASSISTANT_VOICE_PURPOSE`), never by `apps.api.main:app` |

### 5. Database (optional)

Conversations, files and memory use the existing PostgreSQL container (host port 5433): database `local_assistant`, schema `assistant`, Alembic revision `0006`. API startup runs no migrations.

1. Check that Vault is unsealed. `docker ps` shows the `vault` container as healthy even while it is sealed, because its healthcheck accepts the sealed exit code of `vault status`. Run `docker exec vault vault status` (exit code 2 and `Sealed true` mean sealed) or query Vault's `/v1/sys/seal-status`. Unsealing is an owner action: `docker exec -it vault vault operator unseal`, repeated with different key shares until the threshold is reached.
2. Read the runtime credential from the Vault KV v2 secret `secret/server/local-assistant/postgresql` (fields `username`, `password`, `host`, `port`, `database`), the same path `scripts/full_regression.py` reads. Use only the `local_assistant_app` role. Never use the `home-server` superuser: it can reach every database on the cluster, and with memory enabled the API refuses to start under it because the least-privilege grant check fails. The `home-db` database has no `assistant` schema.
3. Supply the URL through the environment of the API terminal before starting uvicorn, never in command arguments, logs or shell history, and percent-encode special characters in the password:

```bash
read -rs DATABASE_URL && export DATABASE_URL
# format: postgresql+psycopg://local_assistant_app:<password>@<host>:5433/local_assistant
```

The URL must start with `postgresql+psycopg://` (`src/infrastructure/database/connection.py`). If a DB-backed service fails to initialize, the log may show only `conversation_storage_initialization_failed` with the cause hidden (for example a failed memory grant check); restart with fewer DB flags to narrow it down.

Vault TLS note: the Vault CA certificate in the parent infra repository has no `keyUsage` extension. Python 3.13+ default SSL contexts set `VERIFY_X509_STRICT` and reject it, so Vault-reading scripts work only while the environment stays below Python 3.13 (the venv runs 3.12 today). The fix (reissuing the CA) belongs to the infra repository.

### 6. Smoke checks

```bash
curl -s http://127.0.0.1:8000/api/v1/health
curl -s http://127.0.0.1:8000/api/v1/chat/completions \
  -H @"$AUTH_DIR/curl-auth-header" -H 'Content-Type: application/json' \
  -d '{"profile": "core", "preset": "fast", "messages": [{"role": "user", "content": "Xin chào"}]}'
```

Presets (`apps/api/runtime/presets.py`): `fast` (thinking off), `auto` (routes to fast, balanced or deep, never unlimited), `balanced` (the default; thinking budget 4096), `deep` (budget 8192) and `unlimited` (thinking with no budget limit; output may use the remaining context). A request without a valid token gets 401 `authentication_required`. Every route except health answers 403 `local_access_required` to a request with an `Origin` or forwarding header. Browsers add `Origin` to POST and other state-changing requests, so the Swagger UI at `/docs` is read-only from a browser; send real requests with curl on the same machine.

### 7. Stop

Press Ctrl+C in the API terminal first (graceful shutdown closes the services and the database pool), then in the CORE terminal, and confirm with `nvidia-smi` that the VRAM is released. Close the shell that holds `DATABASE_URL`, and delete `$AUTH_DIR` when its token is no longer needed (the step 2 snippet refuses to overwrite existing files).

### More detail

- [Conversation API runbook](docs/CONVERSATION_API_LOCAL_RUNBOOK.md): auth, HTTP contract, leases, recovery
- [File storage runbook](docs/FILE_STORAGE_LOCAL_RUNBOOK.md), [memory API](docs/MEMORY_API.md)
- [Workspace reads and config format](docs/D34_WORKSPACE_READS.md), [reviewed coding workflow](docs/D43_REVIEWED_CODING_WORKFLOW.md)
- [Authenticated web search](docs/D48_AUTHENTICATED_SEARCH_API.md)
- [Incremental ingestion](docs/INCREMENTAL_INGESTION.md), [retrieval](docs/RETRIEVAL.md)
- Example run: the dev log entry "2026-11-08 — MVP walkthrough on the production code (no-DB and DB tiers)" in [dev_log/dev_log.md](dev_log/dev_log.md)

## Safety rules

- Bind to `127.0.0.1` only; never `0.0.0.0`, a public interface or a reverse proxy.
- Run one API worker (`--workers 1`) with `--no-proxy-headers`.
- Never commit `.env` files, Vault credentials, tokens, model weights or database dumps.
- Do not restart shared services (PostgreSQL, Vault, Qdrant, SearXNG) without authorization.
- Model replacements need benchmarks, a resource/migration/rollback analysis and owner approval.

## Branches and CI

Changes go to `develop` by pull request; `develop` is promoted to `staging` and then to `production` by pull request. Commit messages use the `feat:`, `fix:`, `docs:` and `bench:` prefixes.

[`.github/workflows/ci.yml`](.github/workflows/ci.yml) runs on pull requests and on pushes to these branches: Ruff on changed Python files entering `develop`, the hosted-runner pytest scope (plus a non-blocking quarantine job), Node tests and a `ci-gate`. Pushes to `staging` and `production` build a source bundle artifact; the staging deployment job only records that bundle, and a GitHub Release is published only for a `v*` tag. Hosted runners have no GPU, models, PostgreSQL, Vault or Qdrant, and CI never contacts or deploys to the Home Server.

## License

MIT. See [LICENSE](LICENSE).
