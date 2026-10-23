# ADR 111 — Owner-deferred TTS listening and explicit local recording

**Purpose:** Record the owner's new scheduling decision and define D71 recording boundaries without claiming that unreviewed audio passed acceptance.

**Date:** 2026-10-23. **Status:** Accepted by explicit owner instruction: “Vậy thì viết tài liệu để tôi test sau và bắt đầu ngày tiếp theo đi, xong hết mới được dừng”.

## Decision and effect on earlier decisions

The owner now defers the missing D70 auditory review to their later manual test and authorizes starting D71. This supersedes ADR-097's scheduling prohibition; its original rejection and all previous observations remain historical evidence. D70 becomes **MACHINE MEASUREMENTS COMPLETE / MANUAL LISTENING DEFERRED**, not naturalness PASS. Preserve all24first outputs, six explicit-Vietnamese refusals, null review labels, original AC and failed evaluator campaigns. No further evaluator research is scheduled. The [manual test guide](../D70_MANUAL_LISTENING_TEST.md) describes the retained offline player, per-output review, uncertainty and completion criteria.

Independent implementation may proceed. Deferred listening remains a release/model-selection gate: do not claim accepted voice quality, select/deploy TTS, or close the final voice/release gate without its evidence. This is an explicit sequencing exception for D70, not permission to waive other milestones, licensing, model selection, safety or tests. Current model roles, registry, production services, resource caps, Vault, databases and collection data remain unchanged.

## D71 implementation

Add an isolated loopback browser recording surface and a small read-only static ASGI application, without altering the existing API's passed authentication/origin rules or introducing an audio upload endpoint. Recording begins only through the visible start action and browser microphone permission. Visible stop ends capture and permits local playback; cancel, Escape, hidden page, page exit, track loss, permission failure and timeout discard the recording and stop every acquired track. Late permission resolutions after cancellation must also stop their tracks. Never record on load, recover automatically or restart after device loss.

Capture mono16k PCM through the browser's native AudioWorklet, at most30seconds/480000samples. Hold PCM and preview only in this page's memory. Produce a local WAV after stop; explicitly release object URLs and all capture resources on discard/replacement/page exit. No transcription, model loading, network transmission, localStorage, IndexedDB, server audio storage or automatic download. Browser OS permission is not perpetual application consent.

The optional surface serves only its fixed static resources on loopback with Host/origin validation, CSP, frame denial, no-store and a microphone permission policy. No credentials or models are exposed. D72's authenticated processing and model choices remain separate work.

## Priority, dependencies, validation and rollback

D71 is existing P1 roadmap scope, one implementation/validation milestone. Dependencies: secure loopback browser context and existing uv/FastAPI; AudioWorklet/browser permissions are verified against native browser behavior. Risks include late acquisition after stop, background capture, suspended audio contexts, bounded buffers, permission dialogs left unanswered, accidental transmission and leaked preview URLs. Tests cover those transitions, native WAV bytes and read-only HTTP restrictions; a real browser with an explicitly fake test microphone verifies acquisition and track release without recording the user's device. A user-device check is documented separately and is not represented as executed.

No model/data/database migration. Rollback stops the optional UI process and removes only the new surface, retaining test evidence and the owner's deferred D70 task. Existing API/inference services are unaffected.
