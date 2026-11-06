# ADR 120 — Profile-bound versioned prompts

**Purpose:** Define D80 immutable prompt provenance and host profile isolation without changing agreed model choices, existing chat endpoints or runtime policy.

**Date:** 2026-10-23. **Status:** Accepted for independent composition/tests; no production route activation.

## Decision

Add a stateless optional application composition for exact authenticated owner/workspace and a host-selected CORE or UNRESTRICTED profile. Bind the existing configured model identifier explicitly; do not infer a fallback or load/switch models. Each profile has a distinct committed literal v1 system template whose canonical digest must match the host pin. User payloads contain only one user request and bounded source records, never roles/system prompts/profile/model/endpoint/tool definitions/approval flags/template selection. Encode these records as a separate JSON user message and bind their complete prompt digest to response provenance. Treat source instructions as untrusted data; this is structural separation, not a claim that prompting eliminates injection.

UNRESTRICTED is text-only with zero harness/tool/approval capabilities. The optional CORE prompt composition also grants no tool authority; actual tools remain in D79 and require independent authorization. No shared history, template update channel, executable rendering, cross-profile cache or caller-supplied system messages. Use existing Fast preset/token budget512 and InferencePort; verify exact model, complete result, finite usage and text limits before publication. One nonqueued operation, finite timeout and joined cleanup withhold late/suppressed-cancellation replies.

## Impact and rollback

Existing D80/P1 depends on existing model configuration, inference identity verification and D79 scope controls. Tests exercise both profiles with deterministic ports and retained real CORE text inference only; they must not activate the UNRESTRICTED model or claim actual runtime testing of that profile. Model settings, temperature policy, existing conversation storage/API and permissions remain unchanged. Version changes require a new committed literal/digest and review; never silently rewrite v1. Rollback closes the optional component and retains source/evidence. Remaining product/manual/model/release gates stay open.
