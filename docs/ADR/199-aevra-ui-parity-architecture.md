# ADR-199: Aevra UI parity architecture and product chat stream

**Date:** 2026-11-26
**Status:** Accepted for the items marked approved; items marked pending need the owner's decision.

## Context

The owner requires that Aevra's own UI, while it may look different, be architecturally at least as capable as the pinned llama.cpp UI b11557. An inventory of that UI (83 features) showed Aevra lacked a collapsible sidebar with conversation history, a composer with attachments, skills, a reasoning selector, a model selector, a context ring and a microphone, streaming with stop, branching message actions and statistics. The product API had no streaming route: the compatibility stream hard-coded the `fast` preset and failed after about 1 000 tokens, and stopping the non-stream `/chat` request did not stop CORE.

## Decision

1. Rebuild the product UI as plain ES modules without a build step (see `docs/AEVRA_WEB_UI_SPEC.md`), served from a startup allowlist of files under `apps/harness/static/aevra/`. CSP stays `script-src 'self'`; no third-party code is loaded.
2. Add `POST /api/v1/harness/chat/stream` with the same `ChatInput` as `/chat`. It honours preset, context strategy and history policy; sends a `context` event, deltas and usage; emits `[DONE]` only after verified completion and never after an error (ADR-197); holds admission for the whole stream and releases it on disconnect. Byte and time limits scale with the preset's token plan.
3. Extend `ChatInput` with `attachments` (text only, at most 4 files; each evidence block at most 65 536 bytes and all blocks at most 196 608 bytes, passed as untrusted evidence through the existing composer) and `skill` (an installed, owner-reviewed skill authorized exactly like runs).
4. Add `GET /api/v1/harness/models`: lists configured profiles with loaded/online state; only the approved CORE profile is selectable. The UI never loads, unloads or switches models.
5. Store conversations device-locally in IndexedDB as a branching tree (edit and regenerate create siblings), with JSON export/import and delete-all. Import is all-or-nothing: unique ids, acyclic parent links, known fields only, regenerated ids. Nothing is synced to the server.
6. Restrict the `AEVRA_CORE_BASE_URL` override to loopback hosts, matching the host-network container.
7. Electron permits clipboard writes and downloads only for the Aevra origin (exports and generation artifacts); every other permission and download stays denied.

## Pending owner decisions

- **Microphone dictation:** needs an approved local ASR (the evaluated Qwen3-ASR-0.6B path is not activated for the product, ADR-174/175), relaxing `Permissions-Policy: microphone=()` for the shell, and granting `media` in Electron for the Aevra origin only. Browser speech APIs that send audio off-device are excluded.
- **Images and PDF:** product chat is text-only; image chat (ADR-085) and server-side PDF extraction need the sandbox and an approved path; client-side pdf.js would add a vendored dependency.
- **Switching to the unrestricted profile:** both profiles share CORE on port 8080, so switching restarts the shared service and needs owner approval (ADR-031, AGENTS.md).

## Consequences

The UI keeps raw chat text in the browser profile of this device; deleting history is an explicit user action. The compatibility route keeps its previous limits. A historical HAR-006 observation pins `/chat`'s 502 mapping for context overflow, so `/chat` keeps it while the stream route reports `context_overflow` distinctly.

## Validation

Node tests for the message tree, history bounding and request building, Markdown escaping, import validation, the all-or-nothing import (against an IndexedDB stand-in) and paste limits; Python tests for the stream contract, cancellation, attachments, skill and models; browser checks of streaming, stop, regenerate/version navigation, attachments with skill, persistence across reload, settings, themes, panels, collapsed rail, mobile overlay, keyboard focus after re-render, popover and dialog keyboard handling against a fake CORE stub; the container and the Electron shell were smoke-tested against the same stub. Model quality is not measured by these tests.
