# ADR 181 — Opt-in checkout CLI, desktop UI and readonly specialist runs

**Purpose:** Record the implemented first product slice and its narrower scope than the complete HAR backlog.

**Date:** 2026-11-10. **Status:** Accepted for staged implementation under the owner's “Vậy làm những thứ tôi đã bảo đi”; generation model selection/adoption, production activation and release remain unapproved.

## Decision and rationale

Implement `la` as an editable uv console script using argparse/httpx, with explicit initialization, private authentication files, status/chat, readonly runs, context inspection, exact-hash skill lifecycle, UI preparation/opening and Linux desktop launching. Preserve dependency versions; only make the root project editable in uv.lock and add the build backend/entry point. This runs from the checkout, not an independently configured standalone wheel.

Compose a new default-off factory around the unchanged base routes/lifespan. Keep the default app object identical when `ASSISTANT_HARNESS_ENABLED` is absent/0. A single process-local admission lock serializes new task/chat/generation requests; existing unrelated app processes and native operator access are not claimed to be covered by this lock.

The initial task coordinator admits at most four explicit readonly evidence calls followed by one CORE completion, with a 120-second total deadline. Reuse original HarnessToolRun or SkillToolRun and the existing v1 skill trust registry; no patch/check/write surface, model-selected tools, automatic retries or recovered grants. Keep runs/events/results bounded in memory, make deletion of terminal runs explicit and cancel/join active tasks on shutdown. Durable plans/checkpoints remain available as independent earlier components but are not wired to product resume yet.

Bind exact reviewed skill instructions below host policy, authorize before evidence/inference and recheck before publication. Keep the unchanged tokenizer/preset whole-turn implementation, adding explicit evidence-first/recent-turns/strict history policies, deduplication and omission receipts in a separate composer. Do not introduce lossy summaries, automatic memories or a claim of large-model reasoning equivalence.

Reuse the exact pinned upstream prebuilt UI archive, retain checksum/file digests/license and serve verified bytes. Use a separate local cookie/Origin/CSRF boundary and one-use CLI pairing fragments, never expose the app bearer to JavaScript. Revalidate sessions against current principal digests. Implement real native SSE and text-only CORE/Fast compatibility, deny native tools/MCP/router/proxy/model management, strip browser tool declarations in the owned integration bridge and still reject direct malicious declarations server-side.

Desktop v1 is Chromium/Brave app-window mode with a private profile and optional explicit `.desktop` shortcut, using the same local assets. It does not add a second UI codebase, change the user's global browser profile or install Tauri/Electron. Backend and runtime processes remain separately operated. Upstream IndexedDB is the actual UI history store for this slice; server Conversation synchronization, stream replay, native installers and broader UI settings are not implemented by implication.

Add model-neutral generation request/backend/output contracts, bounded jobs and owner-scoped ephemeral artifacts with no production adapters. Unconfigured capabilities fail before work starts. Synthetic adapter tests prove software lifecycle only; native media validation, measured GPU/RAM admission and durable artifacts are required before any real generation activation.

## Consequences and validation

This is a usable optional engineering slice, not completion of HAR-001–015 or the existing release. Partial task status remains in the backlog. Process restart loses product run history, installations and sessions; recovery is explicit fresh review rather than resurrected authority. The 120-second software bound may refuse long reasoning/media tasks; changing it requires an assessed resource/time policy rather than silent extension.

The [runbook](../HARNESS_CLI_DESKTOP_RUNBOOK.md) records exact software/native/browser smoke results and retained failures. Old D87 evidence is preserved on its original source scope and does not certify the new additions. No new model weights, model/provider replacements, Docker, Vault, database migrations/contents or Qdrant data were changed. The approved existing CORE was started only after a digest/resource check; no shared service was restarted.

## Rollback

Stop the owned harness process to cancel/join its tasks and invalidate ephemeral grants/cookies. Use the unchanged default API entrypoint. Keep old evidence and any generated terminal receipts, do not delete existing stores or change model defaults. Removing the new console entrypoint later requires only an assessed packaging rollback; it is not an instruction to revert unrelated working-tree changes.
