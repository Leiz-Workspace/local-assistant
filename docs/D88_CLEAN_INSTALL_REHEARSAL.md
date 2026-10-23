# D88 — Clean-install rehearsal

**Purpose:** Provide a reproducible reference install and report the actual failed and successful install attempts.

**Status:** Reference CPython3.12 local install/startup VERIFIED; full D87/product/model acceptance remain separate. No running environment, lockfile, Docker, Vault, database or model changed.

## Observed attempts

1. Default CPython3.11.14, fresh environment, locked production-only offline install: FAILED because the required NumPy2.4.6 wheel was absent from the shared cache. An offline install requires the correct interpreter-specific wheel cache; this is not a successful Python3.11 acceptance.
2. Same fresh3.11environment, locked online attempt: FAILED with “Metadata field Name not found” for cached typing-extensions4.16.0. The observation does not establish a project bug or a diagnosis of cache corruption. Shared cache and incomplete environment were retained, not cleaned or overwritten while full tests use existing SDKs.
3. Explicit existing `/usr/bin/python3.12` (3.12.3), separate fresh environment **and isolated cache**, exact existing lockfile/production dependencies: SUCCESS,44packages. Ordinary already-declared locked application wheels were downloaded; no neural model, new dependency/version or Python interpreter downloaded.
4. A second fresh3.12production environment installed **offline** from that now-complete isolated cache: SUCCESS,44packages, no pytest/dev packages or user-site imports.

Actual isolated first-reference startup imported packages from its new prefix, disabled inherited feature/Vault/database overrides and used the real FastAPI app: health200,55OpenAPI paths, missing-auth stateless chat503/auth_unavailable before model work. No database connection or model generation. Lock SHA256 remained84ebcd30727cbb47bd8279f11ab79ca1e0c3271500734222c49e10fa93e00795. Full versions/log hashes in [evidence](evidence/d88-clean-install-verification.json). Failed artifacts remain beside successful ones under data/backups/d88-clean-install-first.

## Reference commands

From the repository's ai directory, use an **existing** compatible Python3.12 interpreter and separate new output/cache paths. The recorded reference did:

```sh
UV_CACHE_DIR="$PWD/data/backups/d88-clean-install-first/isolated-cache" \
UV_PROJECT_ENVIRONMENT="$PWD/data/backups/d88-clean-install-first/venv-reference" \
uv sync --locked --no-dev --python /usr/bin/python3.12
```

After the cache is complete, another new environment can use `--offline`; never call an incomplete cache an offline bundle. Keep the existing application environment and protected SDKs unchanged. Do not delete global uv cache as a routine fix. This is a source-checkout app; run from ai with the matching locked environment. Native optional workers/models, GPU/CUDA, bwrap, FFmpeg, shared PostgreSQL/Qdrant and private credentials are separate prerequisites, not downloaded/initialized by this basic install.

The API remains optional/default-off for persisted resources. Existing private operator auth/database settings follow [local runbook](CONVERSATION_API_LOCAL_RUNBOOK.md); do not put tokens in URLs, chat, Git, debug output or browser persistent stores. Start a configured local API with `uv run --no-sync uvicorn apps.api.main:app --host 127.0.0.1 --port 8000 --no-proxy-headers`. Port8080 remains the operator-only native model backend. A health200without configuration is not proof of authenticated chat/model/database readiness.

Recorder/device/manual checks: [D71guide](D71_EXPLICIT_RECORDING.md), [D70listening](D70_MANUAL_LISTENING_TEST.md). Deployment/OIDC/proxy/TLS/multiworker, reference3.11install, fresh-host model provisioning and off-host restore are unaccepted here. Model provenance/quality/license status is in [scorecard](D88_MODEL_PROVENANCE_SCORECARD.md).
