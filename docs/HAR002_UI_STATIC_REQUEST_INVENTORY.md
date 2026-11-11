# HAR-002 — pinned llama-ui static request inventory (build b11557)

## Purpose and status

- **Date:** 2026-11-11. **Status:** static analysis (file reads and greps), followed by a live browser capture on 2026-11-12 that confirmed 4 of the 8 open points. See *Live capture results*.
- **Purpose:** list every request the pinned UI can make, how the Aevra harness answers it, and whether any path reaches native llama.cpp authority. None does. The only upstream call is the CORE chat stream that the server builds.
- **Notation:** `B` = `/home/korosaki-ryukai/Workspace/Server/ai/data/ui/b11557/_app/immutable/bundle.dxrg9fom.js`. Evidence patterns are `grep -oF` against `B` unless noted. `br` = `apps/harness/browser.py`.

## Build and pin

Version `b11557`, source pin `5c8854fd88319125125dc4b836c98b1b215b0f23`, 70 files (`receipt.json` read with `python3 -I`). The build is one 9.0 MB JS bundle plus one CSS file. The directory is owner-private and git-ignored.

**Harness boundary.** `browser_boundary` (br:169-222) skips `/api/`, `/docs` and `/openapi`. Every other path goes through these checks in order:

1. Query check: only `/props` may carry a query, with keys `autoload`/`model`. Other keys give 403 `unsupported_query`.
2. `local_browser`: any other query, a non-loopback peer or a foreign Origin gives 403 `local_session_required`.
3. CSRF check for methods other than GET/HEAD: 403 `ui_csrf_required`.
4. Session check: 401 `ui_session_required`.
5. SECURITY headers and the CSP (br:136-151): `connect-src 'self'`, `script-src 'self'` plus hashes, `style-src 'self' 'unsafe-inline'`, `img-src 'self' data: blob:`, `worker-src 'none'`, `frame-src 'none'`.

The catch-all route (br:431-490) returns 403 `unsupported_capability` when the method is not GET/HEAD, when the first path segment is one of `models, slots, tools, cors-proxy, v1, ui, api`, or when the name is `receipt.json` or `sw.js`. Otherwise it serves receipt files whose SHA-256 matches, and returns 404 `verified_ui_assets_required` for anything else.

The served routes are GET-only (`fastapi/routing.py:1053-1054`), so a HEAD request gets the catch-all result. The UI never sends HEAD.

`bridge.js` wraps only `fetch`. It:
- allows same-origin URLs only,
- deletes `Authorization` and adds `X-Harness-UI: 1`,
- strips `tools`, `tool_choice`, `functions` and `function_call` from chat bodies,
- hides the Models, MCP and Reasoning buttons with CSS.

## Request inventory

| Endpoint | Method | UI feature | Harness handling | Native authority risk | Evidence |
|---|---|---|---|---|---|
| `./props?autoload=false`, `./props?model=…`, `${rl}/props` | GET | startup, retry, API-key dialog | Served: fixed JSON (`role:"model"`, `cors_proxy_enabled:false`, `ui_settings`). Allowed query keys are ignored | None | `Tbe("./props",r,{authOnly:!0})`; br:176-181, 324-344 |
| `/v1/models` | GET | model selector | Served: one CORE entry | None | `LIST:"/v1/models"`; br:310-322 |
| `/models/load`, `/models/unload`, `/models` (download), `/models/sse` | POST, GET | router-mode manager (inactive) | 403 `unsupported_capability` | Blocked | `JV(JE.LOAD,n)`; br:451-457 |
| `/models?model=<id>` | DELETE | delete from disk | 403 `local_session_required` (because of the query) | Blocked | `E6t(JE.DELETE` |
| `/tools` | GET | tools panel | Served: `[]` | None | `HI={EXECUTE:"/tools",LIST:"/tools"}`; br:346-349 |
| `/tools` (including streaming) | POST | server tools, file read | 403 `unsupported_capability` | Blocked | `G2(HI.EXECUTE,` |
| `./v1/chat/completions` | POST | send, regenerate, continue, agentic, title, pre-encode | Served after translation (see *Chat contract*) | CORE stream only | `BV={COMPLETIONS:"./v1/chat/completions"`; br:367-429 |
| `./v1/chat/completions/control` | POST | Skip reasoning | Has no query, so it passes the boundary, then gets 403 `unsupported_capability` in the route error shape | Blocked | `fetch(BV.CONTROL,` |
| `./slots[?model=]` | GET | pre-encode (off by default) | 403 `unsupported_capability`; with a query, 403 `local_session_required`. The UI treats the error as idle | Blocked | `xye={LIST:"./slots"}` |
| `./v1/stream?conv_id=…&from=N` | GET | resume, probe | 403 `local_session_required` | None | `` return`${Aye.BASE}?${n}${i}` `` |
| `./v1/stream?conv_id=…` | DELETE | Stop | 403 `local_session_required`. Stop relies on the client abort (inferred) | None | `fetch(Un.buildStreamUrl(n),{headers:ov(),method:"DELETE"})` |
| `./v1/streams/lookup` | POST | on mount and on visibility change | Served `[]` while there are 64 conversations or fewer. Above that, 422 `invalid_stream_lookup` every time; the only effect is a console warning | None | `e=(await fn.getAllConversations()).map(s=>s.id)`, `syncRemoteRunningStreams lookup failed`; br:351-365 |
| `/cors-proxy?url=…` | GET/POST | MCP proxy, favicons | 403 `local_session_required`. Not attempted, because `cors_proxy_enabled` is false | Blocked | `Ste="/cors-proxy"` |
| MCP preset and user URLs, OAuth `.well-known/*` | HTTP/SSE/WS | `#/mcp-servers` | Blocked by the bridge and by CSP `connect-src`. A same-origin URL lands on the catch-all | Blocked in the client; no server route | `static createTransport(e,r,n)` |
| `huggingface.co` API, avatars and search; `llama.app` catalog | GET, img | `useHuggingFaceHub` (off by default). Search and catalog have no call site | Blocked by the bridge and the CSP | None | `aF="https://huggingface.co"`, `g4t="https://llama.app/v1/catalog.json"` |
| heic-to CDN; external favicons | `import()`, img | HEIC attachment; MCP and search cards | Blocked by `script-src` and `img-src` | None | `pVt="https://cdn.jsdelivr.net/npm/heic-to@1.5.2`, `uGt="/favicon.ico"` |
| `/recommended-mcp/*`, `/_app/version.json`, `/build.json` | GET | preset icons, version poll | Served from the receipt | None | `iconUrl:"/recommended-mcp/`, `` fetch(`${rl}/build.json` `` |
| `./sw.js` | GET, register | PWA | 403 by name. Registration is also blocked by `worker-src 'none'` | None | `new p("./sw.js",{scope:"./",type:"classic"})` |
| pdf.js blob worker and fake-worker fallback | Worker, `import()` | PDF attachments | The worker is blocked by `worker-src`. The fallback `import(blob:)` is blocked by `script-src`, which has no `blob:`. The likely result is "Setting up fake worker failed", so PDF attachments most likely fail. cMap, font and wasm URLs are null | None | `QC.workerSrc=URL.createObjectURL(e)`, `get _setupFakeWorkerGlobal` |
| `./pdf.worker.mjs` | GET | pdf.js default, set only under `Fu&&` and overridden by the blob URL | Normally unused. 404, because it is not in the receipt | None | `QC.workerSrc\|\|="./pdf.worker.mjs"` |
| `run_javascript` srcdoc iframe (`jsSandboxEnabled` off by default) | iframe | JS tool | Blocked by the CSP the srcdoc document inherits: `script-src` has no `unsafe-inline`, and `worker-src` is `'none'`. `frame-src` may not apply to srcdoc | None | `d.setAttribute("sandbox","allow-scripts"),d.style.display="none",d.srcdoc=a` |
| HTML code-preview srcdoc iframe (not gated by a setting) | iframe | code-block preview | Inferred: static HTML and CSS render; scripts are blocked by the inherited CSP | None | `code-preview-iframe" sandbox="allow-scripts"` |
| `/health` | — | appears only in the sw.js regex | 404 if requested | None | `data/ui/b11557/sw.js` |
| Not used by the UI: `/lora-adapters`, `/tokenize`, `/completion`, `/embeddings`, `/metrics` and similar | any | — | GET gives 404; other methods give 403. `/v1/completions` and `/v1/embeddings` give 403 | Not reachable (denied by default) | catch-all |

**Harness-owned routes.**

| Route | Handling |
|---|---|
| GET `/`, `/index.html` | Serves the receipt `index.html` rewritten by `brand_index`: the bridge script comes first, and the upstream manifest and icon links are removed. Session required |
| GET `/pair/`, `/harness-pair.js`, `/harness-bridge.js`, `/aevra/brand/{name}`; POST `/ui/pairings` | No session required. The CSRF check still applies to the POST (br:224-298) |
| POST `/ui/logout` | Session and CSRF required |
| GET `/aevra/brand.js`, `/aevra/brand.css`, `/aevra/manifest.webmanifest` | Session required, because these are not under `/aevra/brand/` |
| Icon aliases (`favicon*`, `apple-touch-icon-180x180.png`, `pwa-192/512`) | Served through `resource()` with no receipt check. Session required |
| `/api/*` (including POST `/api/v1/harness/ui-pairings`) | The page can reach these same-origin, and they skip the middleware: no CSRF check, no session check, no SECURITY or CSP headers. The base auth rejects them. `require_local_client` rejects any request with an Origin header (`apps/api/conversations.py:35-38`), and `authenticate_principal` needs a bearer token, which the bridge deletes. XHR is not wrapped, but the page holds no token |
| GET `/openapi.json` | Confirmed by code. FastAPI's default `openapi_url` applies (`fastapi/applications.py:240`, route added at 1143-1157), and `compose()` disables only docs and redoc (`apps/harness/main.py:55-61`). The route skips the boundary, so the Host check never runs: a DNS-rebinding page could read every route, including `/api/v1/harness/*` |
| WebSocket | The middleware is HTTP-only, but there are no WebSocket routes in `apps/` or `src/` |

### Chat contract

- **Accepted requests** need:
  - `stream:true`,
  - system, user or assistant messages with text content,
  - `model` absent or equal to the CORE model,
  - no truthy `tools`, `functions` or `function_call`,
  - `max_tokens` from 512 to 4096 (null, -1 and 0 become 4096).

  The server rebuilds the upstream body from role and content only (`inference.py:194-238`).
- **customJson** is merged into the top level of the body (`Object.assign(ce,ae)}catch(ae){console.warn("Failed to parse custom parameters:"`). Unknown keys are dropped, but keys the server validates are still enforced. For example, `{"stream":false}` gives 422 `stream_required`, `{"max_tokens":256}` gives 422 `invalid_output_budget`, and `{"model":"x"}` gives 422 `unapproved_model`. `messages` is validated too. The bridge strips `tools` and `tool_choice` after the merge, so customJson cannot add them. Title generation's `chat_template_kwargs` arrives as a top-level key and is dropped.
- **Dropped without an error:** sampling settings, `X-Conversation-Id`, `chat_template_kwargs`, `lora`, `id_slot`, and continue-final-message semantics.
- **Request errors** (br:104-133, 367-423):

  | Status | Code | When |
  |---|---|---|
  | 422 | `stream_required` | `stream` is not true; also hit by pre-encode |
  | 422 | `text_only` | non-text content, such as images |
  | 422 | `unapproved_model` | `model` is not the CORE model |
  | 422 | `browser_tools_not_supported` | truthy `tools`, `functions` or `function_call` |
  | 422 | `invalid_output_budget` | `max_tokens` outside the allowed range |
  | 422 | `invalid_messages` | 0 messages or more than 256 |
  | 422 | `unsupported_tool_choice` | unreachable through the bridge |
  | 422 | `invalid_json` | invalid JSON, including duplicate keys |
  | 415 | `json_required` | body is not JSON |
  | 413 | `request_limit` | body above 262144 bytes; long chats or pasted text can hit this |
  | 500 | none | a body read that times out after 10 s raises an uncaught `TimeoutError` |

- **Stream errors:** `inference.py:220-221` stops a stream above 262144 total bytes with `stream_limit`. Every exception inside `events()` is caught at br:420-423 and sent as the generic SSE `inference_unavailable`. That includes `unexpected_tool_call` and `stream_limit`, so the UI never sees the specific code.
- **Stop (inferred):** cancellation depends on Starlette 1.8.0 passing the client disconnect through `@app.middleware("http")`. br:417-419 shows only what the handler does if a cancellation arrives.

## Settings and storage

- localStorage key `LlamaUi.config` holds all settings, including the `apiKey` and the `mcpServers` headers in plaintext. The UI also stores `LlamaUi.userOverrides`, `.streamResume.<convId>` and `.buildVersion` (`,al="LlamaUi"`). Settings export leaves out secrets unless the user turns that option on (`exportSettings(e=!1)`).
- IndexedDB `LlamaUi` has `conversations` and `messages`, with the full chat content. The bundle does not use `sessionStorage`, `caches.` or `document.cookie`. The harness session cookie is HttpOnly.
- `ui_settings` is read on the first visit (`uiSettings(){return this.props?.ui_settings??this.props?.webui_settings}`, `syncWithServerDefaults(){const e=this.getServerDefaults(),r=_n.uiSettings`). But `enableMcp` is not a config key in this build: `grep -c enableMcp` gives 0, and the `cr={AGENTIC_MAX_TURNS:` table has no MCP on/off key. The key is copied into `LlamaUi.config` and has no effect. MCP is driven only by `mcpServers`.
- Hiding the buttons is cosmetic. The user's `customCss` is injected (`N.textContent=jr.config.customCss`), and `style-src 'unsafe-inline'` allows it, so the user can show the buttons again. What actually blocks MCP is the bridge's cross-origin rejection and CSP `connect-src 'self'`.

## PWA and service worker

- `brand_index` replaces the upstream manifest link with `/aevra/manifest.webmanifest`. The upstream file is still served if requested directly.
- `sw.js` would register with a 60-second update fetch (`WI={CHECK_INTERVAL_MS:6e4`). The harness returns 403 for it and the CSP blocks registration. So, by inference, there is no precache, no update loop and no offline shell. `workbox-b3c04f83.js` is never used.
- Even if the service worker ran, its runtime `api-cache` routes would never match. The regexes are anchored at `^\/`, but Workbox tests them against the full `url.href` (`const s=t.exec(e.href)`).

## Base-path behaviour

- `index.html` derives `__sveltekit_11x8523.base` from `new URL('.', location)`, and `B` reads it as `const rl=globalThis.__sveltekit_11x8523?.base`. The UI is served at `/`, so `rl` is `""`.
- Request paths are built three ways: `G2()` adds the `${rl}` prefix, `./` literals go straight to `fetch`, and `Tbe()` resolves with `new URL(t,window.location.href)`. All three stay same-origin. There is no setting for a server base URL.
- Routing is hash-based (`Bo={CHAT:"#/chat"`). `"/search"` is a hash route (`i1t={`) and `"/properties"` is an Ajv schema path; neither is a server call. `/recommended-mcp/*` would 404 if the UI were served under a sub-path.
- Coverage: a re-grep found no other server endpoint besides `./pdf.worker.mjs`. It covered every `fetch(` call site, slash literals in quotes and backticks, and the `${rl}/…` and `${y0t}/…` templates.

## Gaps and follow-ups

The live capture must confirm:

1. The requests on first load in a paired session, with their status codes and body shapes.
2. `./v1/streams/lookup` returns 422 with more than 64 conversations.
3. PDF attachments fail because both worker paths are blocked.
4. In `run_javascript` and the code preview, scripts are blocked and static content renders.
5. An aborted stream logs `harness_ui_stream_cancelled`, releases admission and closes the upstream request. Add a regression test for this.
6. customJson collisions give 422, long chats give 413, and `stream_limit` shows up as `inference_unavailable`.
7. No service worker registers, and Cache Storage stays empty.
8. `customCss` can show the MCP button again, and MCP connections still fail with CSP violations.

Code follow-ups, for a separate authorised task:

- Set `openapi_url=None` in `compose()`, or put `/openapi` under the boundary.
- Replace the misleading `local_session_required` returned for URLs with a query string. `bridge.js` handles only 401.
- The native CORE on `127.0.0.1:8080` (`scripts/start-core.py`) runs without `--api-key`, so other local processes can reach it.

## Live capture results (2026-11-12)

**Setup.**
- **Backend:** an isolated Aevra backend, `aevra serve --port 7093`, using a **session-only test principal**. Its token was generated locally, never printed, and deleted afterwards.
- **Model:** the approved CORE (weights and runtime pin verified), started with the unchanged `scripts/start-core.py`.
- **Browser:** the in-app browser, paired through the normal one-time `/pair/#code` flow.
- **Teardown:** both processes were stopped afterwards, and ports 7093 and 8080 were free. The shared desktop backend on 7090 was not touched.

| # | Check | Result |
|---|---|---|
| 1 | First-load requests in a paired session | Confirmed. `/pair/`, `/ui/pairings`, `/`, brand assets, the bundle, `/tools` (GET 200), `/build.json`, `/props`, `/props?autoload=false`, `/props?model=…&autoload=false`, `/_app/version.json` and `/v1/models` all return 200. **New:** the UI also sends `POST /tools` at startup, which gets 403 as designed. |
| 3 | PDF attachments | **Confirmed broken, and the failure is silent.** The console shows the pdf.js blob worker blocked by `worker-src 'none'`, the `blob:` module blocked by `script-src`, then "Error converting PDF to text: Setting up fake worker failed". The file chip is shown, but the message goes out without the PDF content (27 input tokens), and CORE replies that it cannot see any attachment. No error is shown in the chat. |
| 5 | Stream abort | Confirmed. Stop aborts the fetch, and the backend logs `harness_ui_stream_cancelled`. The UI's `DELETE /v1/stream?conv_id=…` gets 403, as predicted, so Stop relies on the client abort alone. A follow-up message was answered normally, so admission was released. |
| 7 | Service worker and cache | Confirmed: no registration (`sw.js` blocked by CSP), and Cache Storage is empty. |
| — | Browser storage | Only `LlamaUi.*` and theme keys in `localStorage`, plus the `LlamaUi` IndexedDB. No token-like value; the session cookie is HttpOnly and not visible to JavaScript. |
| — | Chat | Real CORE answers through the UI ("READY", "OK"). Every completion shows `net::ERR_ABORTED` in DevTools after the backend logs `product_stream_completed`: the UI closes the reader after `[DONE]`, which is benign. |

**Not covered by the live capture:**
- the 64-conversation lookup limit (checked by code only);
- sandboxed iframes;
- error mappings (`customJson` 422, long-chat 413, `stream_limit`);
- `customCss`/MCP.

The test conversation stays in the in-app browser's IndexedDB.

**Owner decision.** PDF attachments fail silently. There are two fixes:
- allow the pdf.js worker (for example `worker-src blob:` together with a `script-src` exception), a CSP relaxation that needs its own review;
- hide or disable PDF attachments in the UI bridge.

Either choice is the owner's.
