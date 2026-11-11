# D80 — Profile isolation and immutable prompt provenance

**Purpose:** Describe verified optional profile-bound text composition without new model selection or permissions.

**Status:** Independent local composition VERIFIED. [ADR120](../ADR/120-profile-bound-versioned-prompts.md). Existing chat/conversation endpoints and model configuration remain unchanged; this optional component is not registered in production.

Authenticated host code supplies exact owner/workspace/profile/model identifier and committed v1 template digest. CORE and UNRESTRICTED have separate immutable literal system templates/digests. Model/user payloads cannot override role, profile, template, endpoint, tools or approvals. Only request text and bounded source-ID/text records enter a separate JSON user message. Full prompt/source digests and exact model identity bind complete responses. Structural separation does not guarantee prompt-injection resistance or verify source truth.

Both compositions are text-only and grant no tool authority. UNRESTRICTED cannot use the D79 harness; existing harness components independently require CORE. There is no shared history, cross-profile cache, dynamic template rendering or automatic model fallback/switch/load. Host version changes require a new reviewed literal/digest. One nonqueued request, Fast512token ceiling, finite deadline, strict complete/model/usage validation and joined cancellation/close withhold late or truncated replies. Default60seconds/max120; overall raw payload16384bytes with at most8sources/4096characters each. No prompts/source bodies in component logs.

**20new/53related PASS1.05s/0FAIL/0SKIP**, covering both profile contracts with deterministic inference ports, foreign owners/workspaces, template pin mismatch, extra authority fields, model mismatch, truncated/malformed replies, history separation and suppressed-cancellation/deadline cleanup. Initial runtime errors arose from passing a top-level message list to the existing object-only canonicalizer; corrected the new caller to hash a messages object. Retained the failed log and interrupted the waiting fixture test; fixture waits now have explicit deadlines. No existing helper/guard was loosened. Ruff PASS.

One actual existing CORE inference completed in0.538seconds: “The Cedar fixture color is blue (source: doc-cedar).” Exact model qwen3.5-9b-core, Fast,113input/14output tokens, stop; original PID/start/command unchanged. This is a neutral functional check, not a performance benchmark or actual UNRESTRICTED runtime evaluation. No other model was loaded or tested. [Source/native/log receipts](../evidence/d80-profile-prompts-verification.json).

Original661source bytes unchanged; D70 listening/D74 product/model/license/release gates remain open. D81 cross-domain orchestration is next.
