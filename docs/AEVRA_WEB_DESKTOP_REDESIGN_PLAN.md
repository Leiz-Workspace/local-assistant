# Aevra Web/Desktop redesign plan

**Status:** Draft implementation plan, 2026-11-25.

## Goal

Make Aevra's own interface the primary product UI. The web app runs as a reproducible containerized service. The desktop app is an Electron shell loading the same Aevra web origin. The pinned llama.cpp/Qwen UI remains an explicit developer compatibility surface only; it is not the product interface.

## Current problems

- The current web entry is an injected shell around the pinned llama UI, so product panels are incomplete and layout ownership is ambiguous.
- Browser pairing is exposed to users as a one-use URL fragment and is lost on reload/prefetch.
- The native GTK/WebKit launcher owns too many lifecycle responsibilities and has repeatedly failed in packaged environments.
- `docker-compose.yaml` only defines CORE; there is no Aevra web/API container.
- The existing product API already has real contracts for chat, context archives, runs, generations and skills, but no complete product UI consumes them.

## Target architecture

```text
Browser :7090 ─┐
Electron shell ─┼─> Aevra web container :7090 ─> CORE :8080 (private network)
CLI ------------┘             │
                              └─ PostgreSQL/Qdrant/etc. through configured internal endpoints
```

### Web container

- New `docker/aevra-web.Dockerfile` builds a runtime image from the locked Python project.
- New `docker-compose.web.yaml` defines `aevra-web`, bound to `127.0.0.1:7090` by default.
- The web container owns authentication/session cookies; local development may use a generated local principal, while production requires the configured auth file/secret volume.
- The container connects to `core:8080` by service name; no browser route exposes CORE management by default.
- Health endpoint: `/api/v1/health`; UI endpoint: `/`.
- A compatibility switch is developer-only and cannot be enabled by the normal release compose file. The variable that `apps/harness/browser.py:193` actually reads is `Aevra_WEB_FULL_CORE=1`, spelled exactly so (environment names are case-sensitive); `WEB_FULL_CORE` and `AEVRA_WEB_FULL_CORE` have no effect.

### Product UI

- New owned static app under `apps/web/aevra/` with explicit modules:
  - `app.html`, `app.css`, `app.js`;
  - `api.js` for same-origin authenticated calls;
  - `state.js` for panel/session state;
  - `panels/chat.js`, `context.js`, `memory.js`, `skills.js`, `runs.js`, `personal.js`, `capabilities.js`.
- No silent fake controls. A panel is either backed by a real endpoint or clearly marked unavailable.
- Reasoning control maps to the real preset enum (`fast`, `balanced`, `deep`, `auto`, `unlimited`).
- Chat uses `/api/v1/harness/chat`; streaming uses the existing finite stream contract.
- Context/memory/skills/runs use the existing harness routes and expose loading, empty, error and session-expired states.
- Hooks/plugins/MCP display capability status and links to the CLI/approval flow until a typed mutation API exists.

### Desktop Electron shell

- New `desktop/electron/` package with pinned Electron version, `main.cjs`, `preload.cjs`, and `package.json`.
- Electron loads the same local Aevra web URL, not a second UI implementation.
- The main process starts/stops only the owned web container/backend process, passes no bearer token in URL or renderer storage, and waits for `/api/v1/health` before loading the window.
- `contextIsolation: true`, `sandbox: true`, `nodeIntegration: false`, navigation restricted to the local Aevra origin, downloads denied unless explicitly handled.
- Linux artifacts: `.deb` and AppImage are separate deliverables; the first acceptance target is `.deb`.
- GTK/WebKitGTK code remains legacy and is not used by the new Electron artifact; it stays available only until Electron acceptance passes.

## Implementation phases

1. **Contract freeze:** inventory API schemas, define UI state/route contract, add tests for session/health and panel endpoints.
2. **Web app:** build owned static UI and serve it from the harness/container; test desktop/mobile accessibility and real API calls.
3. **Container:** build image, compose CORE+web locally, health/readiness checks, non-root user, no host source/model mounts except explicit volumes.
4. **Electron:** implement shell, process lifecycle, security policy and `.deb` build; drive the same web app in a real window.
5. **Release:** run full tests, build `.deb` and source artifacts, install the `.deb` on a clean user profile, verify window opens and chat reaches the configured CORE, then promote and tag.

## Acceptance gates

- Web container starts from a clean checkout with one documented command.
- `curl /api/v1/health` is healthy before UI load.
- Pairing is not exposed in normal local flow; an authenticated local session is created by the container/CLI bootstrap.
- Browser test opens `/`, sees Aevra sidebar and all panels, and exercises chat/context/skills/runs.
- Electron `.deb` installs without `uv`, opens a real window, keeps the web container alive, and logs a bounded startup error if readiness fails.
- `docker compose config`, Python tests, JS tests, Electron packaging and clean-install smoke all pass.
- The release title uses `Aevra <version>` and the Debian asset uses `aevra-linux-amd64_v<version>.deb` while package identity remains `aevra-desktop`.

## Explicit non-goals

- Do not proxy unrestricted CORE model load/unload/tools in the normal web container.
- Do not claim plugin/MCP mutations until a real approval API exists.
- Do not reuse the old one-use fragment pairing as the primary user workflow.
- Do not call the old WebKitGTK-only package the finished desktop architecture after Electron acceptance.
