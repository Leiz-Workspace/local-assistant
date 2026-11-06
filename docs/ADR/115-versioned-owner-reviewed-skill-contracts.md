# ADR 115 — Versioned owner-reviewed skill contracts

**Purpose:** Define D75's independent skill schema/install trust without granting tools, advancing unaccepted voice gates or changing passed workflows.

**Date:** 2026-10-23. **Status:** Accepted for independent implementation/tests under the owner's continuous project-work instruction; D74 product/manual acceptance remains open.

## Decision

Add a strict bounded version1JSON manifest: exact ID/version/description/instructions/permission fields; reject duplicates, unknown fields, invalid versions, excess bytes and capabilities outside the trusted host catalog. Initial executable permissions are the existing finite read-only workspace tools. A manifest cannot register tools, callbacks, packages, URLs, models, shell access or approval rights. Adding another adapter later requires its own server-owned contract/allowlist.

Separate review, explicit trust confirmation and installation. The trusted application binds review to exact owner/workspace/raw manifest digest and declared permissions, with a finite monotonic expiry and one-shot consumption. Model text has no approve/install tool. Approval is a host action, not a `trusted` field inside a manifest. Installed capabilities are exact immutable registry-owned objects; serialized/forged copies, another owner/workspace, uninstalled or stale objects cannot execute. Any version/content/permission update requires fresh review; no auto-upgrade, arbitrary callbacks or recovered install grants after restart.

Runtime narrows the unchanged D35 `WorkspaceToolRun` to the installed permission subset and its existing owner/workspace/budgets. Installation trust approves prompt use/capability admission only; it is not permission for a patch/check/other side effect. Existing action approvals are not extended or bypassed. Initial skills can only call existing read-only tools and never widen those source capabilities.

## Priority, dependencies, validation and rollback

Existing D75/P1, one contract/runtime validation milestone. Depends on accepted workspace tool validation/owner scope and host-originated explicit trust. Risks: self-trusting manifests, stale digests, permission drift, cross-owner installs, stale/replayed review tokens, automatic version promotion and treating prompt instructions as authority. Test negative schemas, expiry/replay/scope/content changes, permission subsets, shutdown/uninstall revocation and actual narrowing through the existing dispatcher. No dependency/model download, database/config change, plugin install or public endpoint.

State is bounded process-local metadata; shutdown/restart clears grants and installations. Logs contain finite lifecycle IDs/digests, never skill prompt/source/token contents. Rollback closes this registry and drains its owned tool runs while preserving earlier runtime/code/data. Preparing this independent component does not close D70/D74 or release any product gate.
