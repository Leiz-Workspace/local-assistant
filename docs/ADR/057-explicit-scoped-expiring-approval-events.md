# ADR-057: Explicit scoped expiring approval events and CLI review

**Purpose:** Define D39 human-review contracts before application edits or command execution are implemented.

**Date:** 2026-10-20 (Asia/Ho_Chi_Minh)

**Status:** Accepted/implemented after D38 `825966c`:548 related PASS/7.70s,0 SKIP,exit0,71 new cases and clean audit. Actual local TCP CLI explicit synthetic review and thread-safe one-shot grants verified; [acceptance](../evidence/d39-approval-acceptance.json). No production action approved/executed, no new full2099 claim.

## Priority, dependencies and risks

P1 D39 after measured D38; one approval-contract/CLI milestone. Main risks: confusing a model request with human consent, approving changed content or wider scope, stale/replayed approvals, unbounded state, terminal control injection, credential leakage and partial cleanup. Preserve current model/source/data/config/migration/infrastructure. No action is approved on behalf of the owner by implementing or testing this feature.

## Decision

Add a separately default-off bounded in-memory approval service with request-owned server identities, authenticated owner/workspace, a finite action kind (patch or run_checks) and an exact bounded review artifact. Only trusted application composition creates requests after exact catalog owner/workspace authorization; there is no public arbitrary-scope creation or consume endpoint and no model tool for decisions. Human-facing authenticated local routes fetch a complete review and submit only approve/reject, the exact scope digest and unpredictable server review nonce. Unknown/foreign request IDs are indistinguishable. Strict JSON/body budgets and existing bearer/Origin/local-client policy apply.

Server scope digest binds owner UUID, workspace UUID, action kind and SHA256 of the complete review artifact. Canonical typed context/patch/command/source-version artifacts will be supplied by D40–D43 before any real action. D39 alone cannot validate a future patch or grant broad workspace/shell authority. The human must see the full concrete artifact; no approval of a vague task title. Trusted future consumption must match current exact artifact bytes/kind/owner/workspace and use one approved request once before expiry. Source/action changes require a new request. No retries, implicit approval, model-selected approval, decision replay or consumed-grant reuse.

Use a fixed120-second monotonic lifetime, at most32768 UTF-8 artifact bytes, immutable copied scope/artifact, bounded64 request records and bounded server-generated events. Pending/approved approvals expire at the exact deadline; terminal records may be retired when capacity is needed, without reviving grants. UTC display timestamps do not control expiry. Restart/shutdown invalidates all approvals; single-process local scope only. Cross-process/restart durable approval requires a later separately reviewed storage design rather than broad DB grants now. No migration/Vault key/policy is needed.

An operator CLI accepts an explicit loopback API base URL and request UUID, reads bearer token privately in memory, fetches the exact owner review with trust_env/follow_redirects disabled, renders untrusted artifact as escaped JSON, and requires typing APPROVE or REJECT with the complete request UUID. No autoapprove/noninteractive acceptance flag or execution follows. Only the exact displayed digest/nonce is submitted. Token/nonce/artifact/source text never enter audit logs or command-line token arguments. CLI behavior is tested with controlled input and actual local HTTP review flow on disposable synthetic principals, not real production approval.

Events record server event/request UUID, scoped owner/workspace/kind/digest, stable transition and UTC time; no artifact/nonce/credential text. Startup requires configured workspace service, defaults off, and drains approval state before workspace shutdown. Invalidated/expired/rejected/consumed/foreign requests fail closed.

## Acceptance and rollback

Test exact owner/scope/content/nonce/digest/TTL boundaries, approval/rejection/expiry/one-shot consumption/replay, copied artifact immutability, capacity, lazy expiry, shutdown/restart and uniform foreign denial before side effects. Verify strict HTTP auth/Origin/body/default-off, actual local review/decision flow and CLI explicit typing/escaping/token privacy/redirect and URL limits. No source file or command executes. Re-run affected lifecycle/auth/workspace gates, preserve D38 first model failures, audit unchanged protected configuration/data. Disable/drain the feature to roll back; all pending/approved requests invalidate, no database/model/source migration. D40 proposal/atomic-edit gate remains next only after D39 acceptance.
