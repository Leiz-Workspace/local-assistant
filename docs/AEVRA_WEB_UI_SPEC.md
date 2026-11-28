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
| `history.js` / `markdown.js` | Request building (`buildRequest`) bounded to server limits in whole pairs; escaped Markdown subset |
| `limits.js` | Attachment and paste limits shared by the composer and settings (no DOM, unit-tested in Node) |
| `settings.js` | Device-local preferences and the settings dialog |
| `ui/sidebar.js` | Collapsible sidebar: 56 px rail or 280 px panel, mobile overlay, search, pinned/recent conversations, row menu |
| `ui/composer.js` | Composer: `+` menu, attachment/skill/system chips, reasoning selector, model selector, context ring, microphone, send/stop |
| `ui/chat.js` | Messages, reasoning block, statistics, copy/edit/regenerate/delete, version navigator, scroll-to-bottom |
| `ui/panels.js` | Context, Memory, Skills, Runs / Jobs, Hooks / Plugins |
| `ui/dom.js` | Safe element builder, icons, dialogs, menus, popovers, toasts |

## Layout and navigation

- Sidebar: Chat mới (Ctrl/Cmd+Shift+O), Tìm kiếm (Ctrl/Cmd+K), conversation list grouped Đã ghim / Gần đây with a per-row menu (pin, rename, export JSON, delete), workspace tools, Cài đặt, Đăng xuất and connection status. Ctrl/Cmd+B toggles rail/expanded; the state persists. With "Luôn mở sidebar trên desktop" the sidebar stays open on desktop, the collapse button is hidden and Ctrl/Cmd+B does nothing; the saved rail state is not changed. On screens under 768 px the sidebar is an overlay that closes before a selection acts (so a dialog it opens returns focus to the menu button); Tìm kiếm keeps it open, and Escape in the search field closes only the search and returns focus to Tìm kiếm. Shortcut tooltips name Cmd on Apple platforms and Ctrl elsewhere.
- Topbar: conversation title, status, conversation menu. The status combines the web session with CORE readiness from the model probe on load and from each reply: "Đã kết nối · CORE sẵn sàng", "Web đã kết nối · CORE không phản hồi", or "Đã kết nối · local" while CORE readiness is unknown.
- Panels replace the chat view in the same workspace area. Deleting the open conversation from the sidebar while a panel is shown keeps the panel. The session screen (after logout or a lost session) highlights no conversation.

## Composer

| Control | Contract |
|---|---|
| `+` menu | Text/code files (max 4 per turn; each evidence block `Attached file: <name>` plus content at most 65 536 bytes, all blocks at most 196 608 bytes, whole request within 262 144 bytes), installed skill, per-conversation system message. Files and the skill apply to the next message only and are cleared after it is sent; the system message stays with the conversation. Images/PDF are listed as pending owner approval |
| Draft | Each conversation (and the unsaved new chat) keeps its own unsent text, files and skill in memory; switching conversations or pressing Chat mới stores the current draft and restores the target's. The unsaved new chat also keeps its reasoning preset and system message. Files still loading go to the draft they were chosen in. Forking from a question opens the fork with that question, its files and its skill as the draft. Drafts are not persisted across reloads and are dropped when their conversation is deleted |
| Paste / drop | Pasted text longer than the configured threshold (default 2 500 characters) becomes an attachment; dropped or pasted files are attached. Text that cannot be attached (count, per-file or total limit, whitespace only, or a NUL character) is inserted inline when the message stays within 200 000 bytes, otherwise it is refused with a notice; when the inline text pushes the whole turn over the request limit, the notice says to remove files or shorten the text before sending. A blank or invalid threshold in Settings keeps the saved value; only an explicit 0 turns conversion off |
| Reasoning | Presets `fast`, `balanced`, `deep`, `auto`, `unlimited`, stored per conversation, mapped to `ChatInput.preset` |
| Model | `GET /api/v1/harness/models`; only the approved CORE profile is selectable; others show why they are unavailable. The UI never loads or switches models |
| Context ring | Server `context` event (`input_tokens` / `input_limit`) plus an estimate for the draft; popover shows preset, limits, maximum output and last usage; amber from 80 %, red from 95 %. Activating the control that opened a popover or menu again closes it |
| Microphone | Shown; dictation requires an owner-approved local ASR and the Permissions-Policy/Electron changes in ADR-199 |
| Send / Stop | Enter sends (IME-safe), Shift+Enter inserts a newline, Ctrl/Cmd+Enter always sends; while streaming the button stops the request |

## Chat contract

- `POST /api/v1/harness/chat/stream` with `ChatInput`: `messages` (system/user/assistant), `preset`, `context_strategy`, optional `history_policy`, `attachments`, `skill`.
- Stream: `event: context` first, then `data:` deltas (`content`, `reasoning_content`, `finish_reason`), then `usage`. `data: [DONE]` only after a verified complete answer. Failures send `event: error` with a finite code and no `[DONE]`.
- Stop aborts the request; the server cancels upstream work and releases admission. The partial answer is kept and marked stopped.
- History sent to the model contains only complete user/assistant pairs ending with the current user turn; failed or empty answers are excluded; the system message is prepended.

## Messages

User messages show attachments and skill chips. Assistant messages show a collapsible reasoning block (placed after the speaker heading and before the answer, also while streaming), escaped Markdown with per-code-block copy, a stopped or error notice with a "Thử lại" button, and statistics (tokens, tokens/s, total time, time to first token, input tokens). Actions: copy, edit (creates a sibling branch and regenerates; the editor names the attachments and skill that are kept, and asks before discarding changes on Cancel or Escape, or before opening another message's editor), edit answer (local only), raw view, fork, regenerate (sibling answer), delete (subtree, with confirmation), and `‹ n/m ›` version navigation. The editor's text and caret live in the chat view, so any re-render (raw view, version switch, another conversation, settings, a stream ending) restores the open editor instead of dropping it; an edit the app refuses (busy, too large) keeps the editor open. A re-render keeps keyboard focus on the same action; after Save, "Gửi bản sửa" or "Thử lại" focus moves to the message's edit or regenerate action; while an answer streams and the action is disabled, focus rests on the conversation title and returns when the stream ends. An answer whose attachments were omitted by the context budget or size limits says so; attachments the server dropped as duplicates get their own notice only when the first identical copy was included; otherwise they count as omitted. The history notice counts dropped question/answer pairs.

## Storage and privacy

Conversations live in the browser's IndexedDB on this device only; they are never synced to the server. Settings › Dữ liệu exports/imports JSON and deletes all history. Import accepts only the Aevra export format and rejects the whole file unless every conversation has unique message ids, acyclic parent links, non-empty user turns, UUID skill references, error codes in `[a-z0-9_]` and timestamps from 2020 to one day ahead; only known fields are kept and all ids are regenerated. All conversations are written in one IndexedDB transaction, so a storage failure (for example a full quota) imports nothing and is reported separately from an invalid file. Conversation titles in the device-local sidebar come from the first user line; the rule against listing raw prompts applies to server-side listings (archives, runs), not to the owner's own device history. Credentials are never stored by the UI.

## Route and session contract

- `/`, `/aevra-app/`, the shell modules and `/aevra/manifest.webmanifest` are public files without user data. The shell links the manifest (name, icon, theme colour; no service worker) and the CSP allows it with `manifest-src 'self'`; browsers fetch manifests without cookies, which is why that route needs no session. Every data request needs the HttpOnly same-origin session cookie; browser requests without a valid cookie get `401 ui_session_required`.
- With `ASSISTANT_WEB_AUTO_SESSION=1` the UI re-establishes the cookie on the first 401; otherwise it shows an in-app connect screen pointing to `aevra ui open`. Logout revokes the session and disables automatic re-creation until "Kết nối lại"; the signed-out state persists on the device across reloads and tabs.
- Mutations require the same `Origin` and `X-Harness-UI: 1`. No bearer token is stored in browser JavaScript.

## UI states

Every panel renders loading, empty, error/session-expired and success states. Destructive operations require a confirmation dialog. A skill install whose review is missing or expired returns `review_required` ("Bản review đã hết hạn; hãy review lại.") instead of the generic skill denial. The API audit line logs the same status the client receives. `run_capacity` explains both limits: 8 runs per owner and 64 per server, finished ones included, until they are deleted in Runs / Jobs.

## Test matrix

- Node: `tests/test_aevra_tree.mjs`, `tests/test_aevra_history.mjs` (bounded history, request building), `tests/test_aevra_markdown.mjs`, `tests/test_aevra_store.mjs` (import validation), `tests/test_aevra_store_import.mjs` (all-or-nothing import against an IndexedDB stand-in), `tests/test_aevra_limits.mjs` (paste placement and threshold parsing).
- Python: `tests/test_harness_chat_stream.py` (stream contract, cancellation, attachments, skill, models), `tests/test_product_harness.py` (session boundary, shell assets), `tests/test_aevra_branding.py`, `tests/test_electron_shell.py`.
- Browser: chat stream with reasoning, stop and retry, regenerate and version navigation, attachments and skill in one request, history persisted across reload, settings and themes, panels, collapsed rail, mobile overlay.
- Electron: waits for `/healthz`, loads `/`, permits only same-origin clipboard writes and same-origin downloads.
