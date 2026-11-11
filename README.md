# Aevra

Aevra (formerly Local Assistant) is a local-first personal AI assistant that runs on one Ubuntu home server with an NVIDIA RTX 4070 Ti SUPER (16 GiB). A locally built llama.cpp server hosts the CORE model `qwen3.5-9b-core` (Qwen3.5-9B, GGUF Q6_K). Around it, a FastAPI application, the `aevra` CLI and a native Linux desktop app provide authenticated chat, documents, memory, retrieval, web research and reviewed coding tools. Everything user-facing binds to loopback; nothing is exposed to the network.

**Status:** engineering candidate, not a release. There is no tag and no GitHub Release, nothing is deployed to the Home Server, and voice stays off by default. Current gates and open owner decisions are in the [release candidate status](docs/progress/RELEASE_CANDIDATE_STATUS.md) and the [outstanding work ledger](docs/progress/OUTSTANDING_WORK_STATUS.md).

## Components

| Component | What it does | Default |
|---|---|---|
| Inference | `llama-server` on `127.0.0.1:8080` with profiles `core` and `unrestricted` (one model serves the port at a time), presets `fast`/`auto`/`balanced`/`deep`/`unlimited` | started by the operator |
| API | FastAPI `apps.api.main:app` on `127.0.0.1:8000`, bearer tokens from a digest-only principal file, loopback/Origin guard | on |
| Conversations, files, memory | PostgreSQL-backed storage in schema `assistant` | off without `DATABASE_URL` |
| Document and media workers | PDF, OCR, DOCX/XLSX, audio, video and report export in bubblewrap sandboxes; a call returns only after the sandbox PID namespace is gone ([ADR179](docs/ADR/179-retire-sandbox-namespace-before-timeout-returns.md)) | with files |
| Retrieval and grounding | Qdrant ingestion, dense retrieval, grounded answers and structured extraction | opt-in flags |
| Web research | Search through a local SearXNG, cited answers | opt-in flag |
| Coding tools | Workspace reads, explanations, diagnoses, approvals, patches, private checkpoints and checks | opt-in flags |
| Aevra harness | `aevra` CLI, read-only task runs, skills, context policies, pinned llama.cpp chat UI and the native GTK/WebKit desktop | opt-in (`aevra serve`) |
| Voice | Separate entry point for evaluation only | off |

The [component documentation](docs/DOCUMENTATION.md) (Vietnamese) describes each part, its limits and its evidence.

## Architecture at a glance

```text
aevra CLI / Aevra desktop / curl  (same machine only)
        │  bearer token, no Origin or forwarding headers
        ▼
API 127.0.0.1:8000  or  Aevra harness 127.0.0.1:7090
        │
        ├── CORE llama-server 127.0.0.1:8080 (GPU)
        ├── PostgreSQL (database local_assistant, role local_assistant_app) ─┐
        ├── Qdrant, SearXNG 127.0.0.1:8889                                   ├─ shared services in ../infras
        ├── Vault (credentials, read in memory only) ────────────────────────┘
        └── bubblewrap workers: no network, read-only payload, resource limits
```

## Prerequisites

The repository expects to live at `<workspace>/ai` next to the shared infrastructure repository `<workspace>/infras`, which defines PostgreSQL, Vault, Qdrant and SearXNG. Some code and runbooks use the relative path `../infras`.

- **OS:** Ubuntu with an NVIDIA driver and CUDA for CORE. The Home Server runs Ubuntu 26.04; CI uses 24.04. Docker is required for the shared services.
- **Python:** system CPython 3.12 and `uv`. Let uv use the system interpreter, not a downloaded one. The sandboxed workers and the Vault TLS handshake both depend on it.

  ```bash
  UV_PYTHON_PREFERENCE=only-system uv sync --locked --dev --python /usr/bin/python3.12
  ```

- **OS packages for the workers:** `bubblewrap ffmpeg tesseract-ocr tesseract-ocr-eng poppler-utils libreoffice-core libreoffice-writer libreoffice-calc git`. This is the same list CI installs, plus `git`. Bubblewrap must be able to create unprivileged user namespaces; on Ubuntu, the `bubblewrap` package's AppArmor profile `bwrap-userns-restrict` allows this.
- **Desktop app:** GTK 3, WebKitGTK 4.1 and PyGObject from the OS (`python3-gi gir1.2-gtk-3.0 gir1.2-webkit2-4.1`). See the [desktop guide](docs/AEVRA_DESKTOP.md).
- **CORE runtime and weights**, neither of which is in Git:
  - llama.cpp built at the commit pinned in [configs/llama-cpp-commit.txt](configs/llama-cpp-commit.txt), at `runtimes/llama.cpp/build-cuda/`;
  - the GGUF files listed in [configs/models.yaml](configs/models.yaml), under `models/`.

## Quick start

From this directory, with the shared services running:

```bash
uv run --no-sync python scripts/start-core.py      # terminal 1: CORE on 127.0.0.1:8080
uv run --no-sync aevra doctor                     # check the local setup
uv run --no-sync aevra init                       # once: create a separate local principal (refuses to overwrite)
uv run --no-sync aevra ui prepare                 # once: fetch the pinned chat UI assets (not a model)
uv run --no-sync aevra serve                      # terminal 2: harness backend on 127.0.0.1:7090
uv run --no-sync aevra desktop                    # terminal 3: native window (or: aevra ui open)
```

`la` is a compatibility alias for `aevra`. The CLI never downloads, replaces or unloads a model. The [CLI and desktop runbook](docs/HARNESS_CLI_DESKTOP_RUNBOOK.md) covers chat, runs, skills, context policies and history.

To run the plain API instead, follow the [API operator guide](docs/README.md). It covers the principal file, the uvicorn command, every feature flag and its prerequisites, the database and Vault steps, smoke checks and shutdown.

There are two ways to start CORE:
- **`scripts/start-core.py`**: native, text-only, and the path the guides use.
- **`docker compose --profile core up -d`**: adds the multimodal projector. The full regression uses this path, and so does OCR in `vlm` mode.

Start only one of them.

## Tests

```bash
# Hosted-runner scope, as in CI: no GPU, database, Vault or Qdrant needed
PYTHONPATH=.github/ci HOSTED_TEST_MODE=main \
  uv run --no-sync python -m pytest tests benchmarks/tests -p hosted_exclusions -q

# Lint changed Python files
uv tool run --offline ruff check --isolated --select E4,E7,E9,F <files>
uv tool run --offline ruff format --check <files>

# JavaScript tests
node --test tests/test_*.mjs
```

A plain `pytest tests` needs the real services. In particular, `tests/test_core_acceptance.py` calls CORE at import time. The full regression with PostgreSQL, Vault and CORE (D87) has its own [runbook](docs/progress/D87_FULL_REGRESSION_20261106_RUNBOOK.md); start it on an idle host. A green test run is software evidence, not a model-quality measurement.

## Documentation map

| Where | What |
|---|---|
| [docs/DOCUMENTATION.md](docs/DOCUMENTATION.md) | Component documentation (Vietnamese) |
| [docs/README.md](docs/README.md) | API operator guide: auth, flags, database, smoke checks |
| [docs/AEVRA_DESKTOP.md](docs/AEVRA_DESKTOP.md), [docs/HARNESS_CLI_DESKTOP_RUNBOOK.md](docs/HARNESS_CLI_DESKTOP_RUNBOOK.md) | Aevra desktop and CLI |
| [docs/HARNESS_PRODUCT_DESIGN.md](docs/HARNESS_PRODUCT_DESIGN.md), [docs/CONTEXT_MANAGEMENT_STRATEGIES.md](docs/CONTEXT_MANAGEMENT_STRATEGIES.md) | Harness design and context strategies |
| [docs/ADR/](docs/ADR/) | Architecture decision records |
| [docs/progress/](docs/progress/) | Roadmap, status ledgers, day results, protocols and runbooks |
| [docs/evidence/](docs/evidence/) | Public receipts for measurements and acceptance runs |
| [dev_log/dev_log.md](dev_log/dev_log.md) | Append-only development log |

## Safety rules

- Bind to `127.0.0.1` only. Never use `0.0.0.0`, a public interface or a reverse proxy. Run one API worker with `--no-proxy-headers`.
- Never commit `.env` files, Vault credentials, tokens, model weights or database dumps. Model weights (`models/`), the llama.cpp build (`runtimes/`) and local data (`data/`) are ignored by Git.
- Do not restart shared services (PostgreSQL, Vault, Qdrant, SearXNG) without authorization.
- Model replacements need benchmarks, a resource, migration and rollback analysis, and owner approval.

## Branches and CI

Changes reach `develop` by pull request. `develop` is then promoted to `staging` and on to `production`, also by pull request. Commit messages use the prefixes `feat:`, `fix:`, `docs:` and `bench:`.

[CI](.github/workflows/ci.yml) runs on pull requests, on pushes to those branches and to `v*` tags, and on manual dispatch. It runs:
- Ruff on the changed Python files entering `develop`;
- the hosted-runner pytest scope, plus a non-blocking quarantine job;
- the Node tests;
- `ci-gate`.

Pushes to `staging`, `production` and `v*` tags build a source bundle artifact. Only a `v*` tag publishes a GitHub Release. CI never contacts or deploys to the Home Server.

## License

MIT. See [LICENSE](LICENSE).
