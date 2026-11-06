# D75 — Versioned owner-reviewed skill contracts

**Purpose:** Document the verified independent skill schema/install-trust component without claiming that the open D74 product gate or any deployment passed.

**Status:** Local contract/runtime VERIFIED; independent preparation while D74 manual/product acceptance remains open. [ADR115](ADR/115-versioned-owner-reviewed-skill-contracts.md). No production skill was installed and no public install endpoint was added.

## Contract

The strict UTF8 JSON schema has exactly `schema_version`, `id`, `version`, `description`, `instructions`, `permissions`. Version1uses a lowercase bounded identifier, numeric three-component version with no leading zeros, bounded text and one to five distinct existing read-only workspace tools. Maximum manifest32768bytes/instructions24000UTF8bytes. Unknown fields, duplicate keys, invalid Unicode/control characters and noncatalog permissions are rejected. [Complete inert example](../configs/skills/source-reader.v1.json).

The trusted application first creates a review bound to owner/workspace/exact raw SHA256/permissions, then requires an explicit host trust confirmation of that digest before installation. Reviews expire at120monotonic seconds and are one-shot; at most32pending reviews/64installations exist. Updating content/version/permissions needs a fresh review. Author authenticity is not inferred from a self-declared ID or a SHA256: this is exact-content owner trust, not publisher signature verification.

An installation is a registry-owned immutable object. Copies, other owners/workspaces, uninstalled handles, stale reviews and state serialized across restart grant no tool authority. Shutdown clears metadata/grants. A host using an active `SkillToolRun` must also await its context exit/close to drain work; registry revocation blocks admission/publication but does not pretend to synchronously kill an already executing native read.

## Runtime narrowing

`SkillToolRun` delegates only the reviewed subset to the unchanged D35 workspace dispatcher. Exact owner/workspace/source validation, argument schemas, byte/time budgets and native cleanup remain there; the outer skill run also charges at most8attempts, including denied calls. A post-call installation check withholds output if trust was revoked during the call. `async with` guarantees joined closure. Manifest instructions, model text and a claimed `trusted` field cannot add tools, shell, URLs, callbacks, packages, models or action approvals.

Initial permissions are only the five existing read-only workspace operations. No MCP server or mutation permission is automatically installed; later adapters need explicit host contracts. Existing patch/check approvals are unchanged. No package execution, default selection, persistence/database/config mutation or production skill activation accompanies this component.

## Actual verification

**234related tests PASS0.87s/0FAIL/0SKIP**, including39new skill cases and existing workspace policy/reader/service/tools/approvals/workflow controls. Two actual disposable native workspace reads run through the existing dispatcher, including revocation after native completion before publication. Negative tests cover schema/bounds/duplicate keys, self-trust, arbitrary endpoints/tools, exact digest changes, truthiness, cross-owner/workspace, expiry/nonfinite clock, replay, forged objects, version permission separation, bounded pending reviews, uninstall/restart/shutdown and all denied-attempt charging. Ruff/diff checks PASS.

No earlier passed source files were edited. The shipped example is inert; all test installations use disposable identities/fixtures. [Acceptance and complete source/log hashes](evidence/d75-skill-contract-verification.json). D76's independent MCP allowlist/adapter work is next; D74 and final product/manual gates stay open.
