# D44 bounded workflow controls

**Purpose:** Describe finite trusted hooks, exact owner cancellation and one explicit immutable proposal retry on the accepted reviewed coding workflow.

**Status:** PASS (defined local finite workflow-controls scope). **2622 full PASS/1559.31s,0SKIP,exit0**;1264 related PASS/90.68s and74 new focused PASS/17.45s are subsets. Twelve evaluated Python files/128 described functions/classes pass isolated Ruff correctness/import/format;414 sources/488 unique source-protected hashes and clean readonly audit. Earlier70/72 focused,1260/1262 related, two interrupted fulls and four reproduced uncertainty faults remain historical evidence. [Acceptance](../evidence/d44-controls-acceptance.json), [full](../evidence/d44-full-regression.json), [audit](../evidence/d44-final-post-audit.json), [ADR-063](../ADR/063-bounded-workflow-hooks-cancel-and-retry.md), [source freeze](../evidence/d44-controls-freeze.json), [source quality](../evidence/d44-source-quality.json), [related](../evidence/d44-related-regression.json), [retained defect/repair](../evidence/d44-uncertainty-repair.json).

## Enablement and owner APIs

Both `ASSISTANT_CODING_WORKFLOW_ENABLED=1` and the separate `ASSISTANT_CODING_WORKFLOW_CONTROLS_ENABLED=1` are required to select the controller. Both default off; this milestone changes no env/config file or production flag. Without the second flag, the accepted D43 service remains selected. Matching live workspace, approval, checkpoint-patch and check dependencies remain mandatory, with workflow teardown before native authorities.

New local authenticated owner-only actions under `/api/v1/workspaces/{workspace_id}/coding-workflows/{workflow_id}`:

| Action | Body | Result |
|---|---|---|
| `POST /cancel` | `{}` | Signal and join the exact associated task, retire idle pending capabilities and preserve actual edit/check receipts |
| `POST /retry-proposal` | `{}` | At most one distinct second proposal after a component-free failed proposal, using unchanged original issue/path/hash/profile options |

Requests retain strict16KiB JSON bounds, owner/local-client/Origin checks and private/no-store/nosniff responses. No model/command/approval/resource/source override is accepted. Unknown and foreign workflows are masked identically. Enabled progress GET/list reads bounded last-observed owned memory without waiting for normal action admission; it grants no source freshness or action authority.

## Finite policy and explicit retry

Hooks are fixed server-owned metadata events for proposal, apply, check capture, check run and cancellation. They cannot load modules, call a URL/shell/plugin, use model-defined callbacks or approve actions. Reserve a before/after pair before an admitted action. Limits: four ordinary stages/workflow, five/lineage, two proposals/lineage,16 events/workflow and32/lineage; retained workflow limits remain16 globally/four owner/128KiB per record. No automatic retry, refund, eviction or history replacement.

Explicit retry is available only for `proposal_failed` without any published patch/check, cancellation intent or uncertain hook history. The first failed model observation remains unchanged. The second record receives a new workflow identity and fresh native context/checkpoint/diff review. Original source hashes must still match; drift produces a retained failed second record before another inference. Busy/capacity denial before registration consumes no proposal slot. A successful second proposal still requires a concrete patch approval and explicit apply, then a different check approval and explicit run. Third attempts and retries after any published component/action/cancellation are denied. Controlled first-invalid/second-valid tests exercise execution policy and make no live-model quality claim.

## Cancellation and actual effects

Cancellation has separate nonqueued admission and an owned cleanup child. Authorization precedes flags/signals. Bind the exact workflow ID to its actual request before the first native capture await. Signal/cancel and join its associated model/native work before releasing capabilities. Losing the cancellation response or cancelling its request still joins owned cleanup; shutdown joins normal requests, cancellation requests and cleanup children before closing dependencies.

For an idle proposed patch, enter existing component admission, mark that live capability failed with `workflow_cancelled` and join its close. Source bytes, approval event history and the historical ready checkpoint remain unchanged. Do not fabricate an applying intent just to journal cancellation. Check cancellation uses its existing owner signal/join/retirement path. Restart never recovers an old grant; cancellation history itself remains process-local.

An independently invoked component writer may already own its pin or have committed. Busy cancellation keeps intent pending and blocks future workflow actions; a later explicit cancellation may finish cleanup after that writer joins without another event pair. It never closes a live writer pin or claims to undo the edit. Known committed source/consumed approval/checkpoint and observed native start/exit remain visible. Already completed workflows return `already_terminal` without more events. Repeated completed cancellation is idempotent. Close/posthook acknowledgement failures retain explicit cleanup/hook uncertainty and do not rerun actions or hooks.

Native exit0/printed PASS remains an observation, with `quality_evaluated=false`, `output_is_untrusted=true`, `current_source_observed=false`. TCP disconnect alone does not imply request-task cancellation. Controller shutdown alone does not revoke independently owned component credentials. Existing D41/D42 native/runtime/OS/cooperating-writer/crash and D43 process-local/single-target limits remain.

## Actual verification and retained limits

Focused tests use actual disposable source capture, checkpoint-backed atomic writes before/after commit, sandbox child launch/exit, pending/running checks and real TCP/two typed CLI reviews. Inference is explicitly controlled for D44 policy cases. They cover ownership, quotas, source drift, hook and task-creation faults, lost ASGI responses, independent component writers, idempotence and shutdown ordering. Per-command pytest temporary retention keeps failed fixture trees only; product retention behavior is unchanged.

Completed exact-source1264 related and2622 fresh full with existing live credentials held only in memory, followed by successful readonly source/model/config/migration/data/ACL/worker/lock audit. V006/data/quota/vector/probe/worker/native/advisory-lock inventories remain clean; original owners/ACL/narrow grants and invoker fixed-search-path trigger properties match. Prior D43 source provenance is checked against exact accepted Git blobs for the three authorized D44 registration/factory/router changes; other accepted bytes stay current and unchanged. First D43 actual CORE sample and original D38 first4/6/two failures stay immutable; additional full-regression trials use separate unique artifacts and never replace the original measurements. No model download/replacement/deployment or production action is authorized by this evidence. D44 gates now pass; D45 is next. The additional full-regression D43 trial is retained separately from its immutable first sample; see full evidence for its unique artifact/hash. Complete committed file versions are archived privately under data/backups/d44-complete-full-files.zip.
