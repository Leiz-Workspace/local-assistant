# Aevra Web UI Specification

## Scope

Aevra owns the product shell and chat interface. The pinned llama.cpp/Qwen UI is not the product UI; it remains available only as an explicit compatibility surface when `Aevra_WEB_FULL_CORE=1`.

## Navigation

| Panel | Backend contract | State |
|---|---|---|
| Chat | `POST /api/v1/harness/chat` | Implemented; stream upgrade pending |
| Context | `GET /context/archives`, `GET /context/archives/{id}`, delete, purge summaries | Implemented |
| Memory | Same archive/summary APIs; must explain process-local vs durable state | Implemented contract |
| Skills | `GET /skills`, review, install, inspect, uninstall | Implemented; approval UX pending |
| Runs / Jobs | `/runs` CRUD/cancel and `/generations` CRUD/cancel/artifact | Implemented |
| Personal | local profile/session/theme/preset preferences | UI state pending; no server mutation assumed |
| Hooks / Plugins | no safe mutation API currently | Status-only; never fake enable/install buttons |
| Models | `/v1/models` in explicit full-core mode only | Compatibility-only |
| MCP | `/tools` in explicit full-core mode only | Compatibility-only; disabled by default |
| Reasoning | product preset selector (`fast`, `balanced`, `deep`, `auto`, `unlimited`) | Must map to `ChatInput.preset`; no fake slider |

## Route and session contract

- Pairing starts at `/pair/#code` and redirects to `/aevra-app/` after a one-use same-origin HttpOnly session cookie is issued.
- `/aevra-app/`, `/aevra/app.js`, and `/aevra/app.css` require the paired session.
- Session expiry redirects to `/pair/`.
- UI requests use same-origin credentials and `X-Harness-UI: 1`.
- No bearer token is stored in browser JavaScript.

## UI states

Every panel must render loading, empty, error/session-expired and success states. Destructive operations require a confirm step. Lists must not display raw prompts, answers or credentials.

## Chat contract

- Role set: `system`, `user`, `assistant`.
- Presets are the only reasoning control until a typed reasoning API is added.
- Context strategy is explicit: `evidence-first`, `recent-turns`, or `strict`.
- Stream responses must preserve the existing incomplete-stream contract: failed streams do not emit `[DONE]`.

## Test matrix

- Pairing exchange and session expiry.
- Sidebar navigation and responsive collapsed layout.
- Chat success, validation error, inference failure and incomplete stream.
- Context/memory list, empty state, retrieve and delete.
- Skills list, review/install/uninstall and permission/hash presentation.
- Runs/generations list, detail, cancel, remove and artifact link.
- Personal local preferences without persistence of credentials.
- Hooks/plugins status-only state.
- WebKitGTK desktop loads the same `/aevra-app/` route.
- Explicit full-core mode is tested separately and never assumed by default product tests.
