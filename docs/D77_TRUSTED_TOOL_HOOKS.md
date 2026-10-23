# D77 — Trusted pre/post/error/stop controls

**Purpose:** Document verified generic metadata hooks and owned cancellation without introducing executable user hooks or approval authority.

**Status:** Local control component VERIFIED as independent preparation; D74 manual/product acceptance remains open. [ADR117](ADR/117-trusted-tool-hooks-and-stop-ownership.md).

The host binds immutable owner/workspace/run/CORE/tool/request-digest calls, a fixed read/write effect map and an async authorization policy. Only fixed metadata events exist: a skill/MCP/model cannot supply callback code, return an `approved` flag or mutate the call. Authorization runs before work and before publication; actual write handlers must still use the existing action-specific approval layer. This component creates no mutation endpoint or new production write grant.

`GuardedToolRun` admits one nonqueued owned task covering authorization, invocation and post-check. At most8attempts/16events and65536reply bytes; a finite host call timeout applies. Every admitted call retains a before/after pair and argument hash; raw arguments, outputs, prompts and approval tokens are absent from logs. Unknown scope/profile/tool/hash fails before authorization or hook publication.

Stop requires exact owner/run identity. Caller cancellation, stop and close join policy/handler cleanup before retiring admission; duplicate signals do not re-cancel in-progress cleanup. Closed/stopped/deadline or cancellation-suppressing late replies are withheld. A handler must own its native children; tests also delegate to the already accepted workspace/MCP adapters, which enforce that contract.

After an invoked write errors, times out, loses authority, stops or produces malformed output, the terminal event is **uncertain** and the run stops accepting further calls. No automatic retry or rollback claim. Existing action receipts remain authoritative; a later explicit owner review needs a fresh scope. Read-only errors safely withhold output. Closing from the handler itself avoids self-await deadlock and still prevents publication.

**218related tests PASS10.02s/0FAIL/0SKIP**, including21new controls and existing MCP/skills/workspace/approval/workflow-control tests. Actual integrations execute a disposable kernel-scoped skill read and an inert pinned offline MCP echo through both authorization barriers, then close native resources. Tests also cover forged/immutable calls, boolean non-grants, permission revocation, timeout suppression, repeated caller/owner stop, policy cleanup, uncertain writes, malformed results, bounded event pairs and closed-handler publication. First expanded-test failure was a quota assertion attached to the wrong test; retained log and corrected the test placement without loosening a runtime guard. Ruff/diff checks PASS.

No existing passed source was changed. [Verification/source/log receipts](evidence/d77-trusted-hooks-verification.json). D78's independent planner/budget/checkpoint/resume component is next; it must preserve uncertainty and never automatically repeat a write.
