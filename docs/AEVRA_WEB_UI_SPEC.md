# Aevra Web UI Specification

## Scope

Aevra owns the product shell and chat interface served at `/`. The pinned llama.cpp UI (`data/ui/b11557`) is a compatibility surface only. Aevra's look may differ, but its UI architecture must be at least as capable as that pinned UI; [ADR-199](ADR/199-aevra-ui-parity-architecture.md) records the parity decisions.

## Architecture

Plain ES modules without a build step, all served same-origin from `apps/harness/static/aevra/` through a startup allowlist (`browser.py` `product_assets`):

| Module | Responsibility |
|---|---|
| `app.js` | Controller and hash router (`#/`, `#/chat/<id>`, `#/panel/<name>`), streaming orchestration, keyboard shortcuts, session screen |
| `api.js` | Same-origin requests, session bootstrap/recovery, error codes, SSE stream reader |
| `store.js` / `tree.js` | Device-local conversations in IndexedDB (memory fallback) as a branching message tree |
| `history.js` / `markdown.js` | Request history bounded to server limits in whole pairs; escaped Markdown subset |
| `settings.js` | Device-local preferences and the settings dialog |
| `ui/sidebar.js` | Collapsible sidebar: 56 px rail or 280 px panel, mobile overlay, search, pinned/recent conversations, row menu |
| `ui/composer.js` | Composer: `+` menu, attachment/skill/system chips, reasoning selector, model selector, context ring, microphone, send/stop |
| `ui/chat.js` | Messages, reasoning block, statistics, copy/edit/regenerate/delete, version navigator, scroll-to-bottom |
| `ui/panels.js` | Context, Memory, Skills, Runs / Jobs, Hooks / Plugins |
| `ui/dom.js` | Safe element builder, icons, dialogs, menus, popovers, toasts |

## Layout and navigation

- Sidebar: Chat mới (Ctrl/Cmd+Shift+O), Tìm kiếm (Ctrl/Cmd+K), conversation list grouped Đã ghim / Gần đây with a per-row menu (pin, rename, export JSON, delete), workspace tools, Cài đặt, Đăng xuất and connection status. Ctrl/Cmd+B toggles rail/expanded; the state persists. On screens under 768 px the sidebar is an overlay that closes after a selection.
- Topbar: conversation title, status (web and CORE readiness), conversation menu.
- Panels replace the chat view in the same workspace area.

## Composer

| Control | Contract |
|---|---|
| `+` menu | Text/code files (max 4 per turn; each evidence block `Attached file: <name>` plus content at most 65 536 bytes, all blocks at most 196 608 bytes, whole request within 262 144 bytes), installed skill, per-conversation system message. Images/PDF are listed as pending owner approval |
| Paste / drop | Pasted text longer than the configured threshold (default 2 500 characters) becomes an attachment; dropped or pasted files are attached. Text that cannot be attached (attachment limit reached) is inserted inline when the message stays within 200 000 bytes, otherwise it is refused with a notice |
| Reasoning | Presets `fast`, `balanced`, `deep`, `auto`, `unlimited`, stored per conversation, mapped to `ChatInput.preset` |
| Model | `GET /api/v1/harness/models`; only the approved CORE profile is selectable; others show why they are unavailable. The UI never loads or switches models |
| Context ring | Server `context` event (`input_tokens` / `input_limit`) plus an estimate for the draft; popover shows preset, limits, maximum output and last usage; amber from 80 %, red from 95 % |
| Microphone | Shown; dictation requires an owner-approved local ASR and the Permissions-Policy/Electron changes in ADR-199 |
| Send / Stop | Enter sends (IME-safe), Shift+Enter inserts a newline, Ctrl/Cmd+Enter always sends; while streaming the button stops the request |

## Chat contract

- `POST /api/v1/harness/chat/stream` with `ChatInput`: `messages` (system/user/assistant), `preset`, `context_strategy`, optional `history_policy`, `attachments`, `skill`.
- Stream: `event: context` first, then `data:` deltas (`content`, `reasoning_content`, `finish_reason`), then `usage`. `data: [DONE]` only after a verified complete answer. Failures send `event: error` with a finite code and no `[DONE]`.
- Stop aborts the request; the server cancels upstream work and releases admission. The partial answer is kept and marked stopped.
- History sent to the model contains only complete user/assistant pairs ending with the current user turn; failed or empty answers are excluded; the system message is prepended.

## Messages

User messages show attachments and skill chips. Assistant messages show a collapsible reasoning block, escaped Markdown with per-code-block copy, a stopped/error notice with retry, and statistics (tokens, tokens/s, total time, time to first token, input tokens). Actions: copy, edit (creates a sibling branch and regenerates; the editor names the attachments and skill that are kept, and asks before discarding changes on Cancel or Escape), edit answer (local only), raw view, fork, regenerate (sibling answer), delete (subtree, with confirmation), and `‹ n/m ›` version navigation. A re-render keeps keyboard focus on the same action; while an answer streams and the action is disabled, focus rests on the conversation title and returns when the stream ends. An answer whose attachments were omitted by the context budget says so.

## Storage and privacy

Conversations live in the browser's IndexedDB on this device only; they are never synced to the server. Settings › Dữ liệu exports/imports JSON and deletes all history. Import accepts only the Aevra export format and rejects the whole file unless every conversation has unique message ids, acyclic parent links, non-empty user turns, UUID skill references, error codes in `[a-z0-9_]` and timestamps from 2020 to one day ahead; only known fields are kept and all ids are regenerated. Conversation titles in the device-local sidebar come from the first user line; the rule against listing raw prompts applies to server-side listings (archives, runs), not to the owner's own device history. Credentials are never stored by the UI.

## Route and session contract

- `/`, `/aevra-app/` and the shell modules are public static files without user data. Every data request needs the HttpOnly same-origin session cookie; browser requests without a valid cookie get `401 ui_session_required`.
- With `ASSISTANT_WEB_AUTO_SESSION=1` the UI re-establishes the cookie on the first 401; otherwise it shows an in-app connect screen pointing to `aevra ui open`. Logout revokes the session and disables automatic re-creation until "Kết nối lại"; the signed-out state persists on the device across reloads and tabs.
- Mutations require the same `Origin` and `X-Harness-UI: 1`. No bearer token is stored in browser JavaScript.

## UI states

Every panel renders loading, empty, error/session-expired and success states. Destructive operations require a confirmation dialog.

## Test matrix

- Node: `tests/test_aevra_tree.mjs`, `tests/test_aevra_history.mjs`, `tests/test_aevra_markdown.mjs`, `tests/test_aevra_store.mjs` (import validation).
- Python: `tests/test_harness_chat_stream.py` (stream contract, cancellation, attachments, skill, models), `tests/test_product_harness.py` (session boundary, shell assets), `tests/test_aevra_branding.py`, `tests/test_electron_shell.py`.
- Browser: chat stream with reasoning, stop and retry, regenerate and version navigation, attachments and skill in one request, history persisted across reload, settings and themes, panels, collapsed rail, mobile overlay.
- Electron: waits for `/healthz`, loads `/`, permits only same-origin clipboard writes and same-origin downloads.
