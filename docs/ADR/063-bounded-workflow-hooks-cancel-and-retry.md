# ADR-063: Bounded workflow hooks, cancellation and explicit proposal retry

**Purpose:** Define D44 finite server-owned policy hooks, owner cancellation and lineage retry ceilings without widening commands, models or existing action approvals.

**Date:** 2026-10-20 (Asia/Ho_Chi_Minh)

**Status:** Accepted and verified D44 local finite controls:2622 full PASS/1559.31s,1264 related subset/74 new cases,0SKIP/exit0;414 sources/488 unique source-protected hashes and clean readonly audit. [Acceptance](../evidence/d44-controls-acceptance.json). Both interrupted fulls/four reproduced faults retained; no production action/approval, model/config/data change or original measurement replacement.

## Priority, dependency, effort and risk

D44 is the existing P1 milestone after D33–D43. Estimate one bounded controller/policy/native-cancellation milestone with unit/native/API/lifecycle/fault/related/full/audit gates. Risks: foreign cancellation, lost actual edit/check results, releasing pins before joined native work, silently retrying a write or using an old grant, cancellation races with separately invoked component APIs, unbounded hook/retry history and presenting program output as policy. No new model/download/dependency/database/Vault/Docker/config-file change.

## Separate default-off trusted controller

Add a subclass of the accepted D43 service selected only when `ASSISTANT_CODING_WORKFLOW_CONTROLS_ENABLED=1` and the existing workflow flag/dependencies are enabled; both flags remain operator opt-in. Keep native patch/check/approval primitives unchanged. The same application state/lifecycle drains this controller before checks→checkpoint→approval→workspace.

The D43 base needs a small `register(record)` extension point replacing its direct dictionary insertion with equivalent registration/logging. This lets the trusted controller bind a newly allocated workflow ID to its owning task before the first native/model await. Otherwise cancellation during initial capture cannot identify the correct operation without copying the entire PASS implementation or cancelling an unrelated task. Also select the subclass in the existing initializer and include new control routes. These are necessary reviewed related changes; do not refactor unrelated PASS files.

Progress GET/list on the enabled controller may read bounded owned last-observed in-memory snapshots without entering normal action admission, allowing the owner to discover/cancel a generating workflow. Authorize before lookup; these reads neither inspect live source nor expire/consume/recover grants. Existing D43 behavior remains the default when controls are disabled.

## Finite hooks and ceilings

Hooks are hardcoded typed server policy events, not shell/plugin/module/URL callbacks or model-defined functions. Record bounded before/after events only for admitted proposal/apply/check-capture/check-run stages and explicit cancellation; do not charge invalid UUID/approval/owner precondition denials or reads as action attempts. Use existing domain approvals/fences at every action. A hook log/event can never create approval or execute another stage.

Each workflow has at most four ordinary stages and16 bounded metadata events; each lineage at most two proposals/five total stages/32 events. Event fields are finite server-owned IDs/stage/phase/outcome/sequence, no raw source/model/program output/credentials. Reserve completion-event space before admitting side effects so post-action logging cannot erase a known receipt. All public/retained JSON must remain inside D43's128KiB record budget and16-global/4-owner record ceiling. No eviction/GC or optional hidden unlimited counters.

Bind stage/task associations by typed owner/workspace/workflow and clear them only after the joined model/native/component outcome. Hook failures before an action fail closed; terminal hooks retain actual receipts and explicit uncertainty. Pre/posthooks never change command/profile/source/resource/approval scope.

## Explicit proposal retry only

Automatic retry budget is0. A new explicit empty-body owner endpoint may retry only `proposal_failed` with no patch/check component ever published and no cancellation request. Derive the unchanged issue/target/test hashes/profile from immutable original options; no client/model override. Create a distinct workflow record/ID in the same lineage, retaining the first failed completion/source hashes and all history. Reserve the second proposal slot at actual record registration before native/model work; a rejected busy/capacity request before registration consumes no slot. Maximum two proposals per lineage, hence one explicit retry. Another retry or retry after a pending patch, applied/unknown edit, check capture/run or cancellation is denied.

Fresh native reads/revalidation and a new checkpoint/diff/review bind any successful retry; an old approval is never reused. Changed raw source hashes fail rather than silently changing inputs. Native metadata may be freshly observed and must be bound into the new concrete review, not falsely presented as the old native version. Every write/check retains its existing separate fresh approval and one-shot ceiling. These are execution-policy tests, not permission to rerun a model benchmark until it passes; D38 and first D43 measurements remain immutable.

## Owner cancellation and truthful boundaries

Use a separate nonqueued bounded cancellation admission path, authorize the exact owner/workspace/workflow before touching flags/tasks/pins. Mark cancellation intent first, signal/cancel only the associated owned operation and join it with the accepted cancellation-safe ownership helpers before pending-capability cleanup. A generating workflow is discoverable through the bounded status list. Do not release native source/runtime pins while a task/launcher/child still owns them.

For an idle associated patch, enter the existing patch service admission and atomically retire only a still-`proposed` native capability to existing `failed` state with `workflow_cancelled`, then join its close. Preserve its checkpoint/source bytes and original approval event history. The durable checkpoint remains a historical `ready` snapshot: existing transition requires an actual applying intent, so do not fabricate that intent solely to journal cancellation. Process-local failed/closed capability cannot apply; restart invalidates old grants. No durable cancellation-authority claim.

Use the accepted check service's owner cancel to stop/join a linked running check or close a pending source and persist its existing cancellation history. No check output or past approval can restart it. Unknown/partial histories stay retained.

If a linked edit was independently invoked through the existing component API and is currently applying, cancellation cannot revoke or undo that atomic action. Return explicit busy/uncertain pending cancellation rather than closing its live pin or asserting no edit; block future workflow stages and allow an explicit later cancellation/inspection after it joins. A separately started linked check can be cancelled via its existing owner cancel because that domain already exposes safe signal/join ownership.

Already applied edits and observed checks are retained exactly. Cancellation after native commit/exit does not rollback, refund, erase receipts or claim no effect. Report cancelled-before-action, cancelled-with-known-applied/observed evidence, already-terminal or cleanup uncertainty accurately. Repeated completed cancellation is idempotent and adds no unbounded events. Cleanup/fsync/response/caller cancellation failures retain known component state and explicit uncertainty, without another write/run attempt. Cancellation of the controller does not retroactively change an approval event; retiring its pending action capability prevents that action from running.

Shutdown cancels/joins normal and cancellation tasks without cycles, before the existing component lifecycle closes remaining caps/grants. Controller-only shutdown is not revocation of independently owned component credentials. TCP disconnect alone is not automatically treated as task cancellation unless a separately tested hook implements it.

## Acceptance before D44 PASS

During exact-source full supervision, static review identified that cancellation could upgrade a prior native `applied_cleanup_uncertain`/`outcome_unknown` receipt to clean completion. Interrupt only the owned pytest with SIGINT; preserve its actual exit2/330.58s and all original source/evidence/log bytes. Two actual native fault cases reproduce this before repair. The D44 controller now classifies trusted patch state/error/receipt uncertainty, including applied=null, in both stage hooks and cancellation; native primitives stay unchanged. Repaired72 focused cases PASS/0SKIP/exit0; fresh1262 related/2620 full and final audit still required. Earlier70/1260 gates remain historical, not final-source acceptance.

The same review found pending-check close/journal uncertainty stored in existing DTO state/error fields. Two more actual fault cases reproduce the omitted aggregation; preserve the second explicitly interrupted full exit2/62.84s and intermediate1262 related evidence. Central D44-only component classification now handles state/error/receipt/observation/persistence uncertainty. Final74 focused and1264 related PASS/0SKIP/exit0,12 evaluated files/128 descriptions,414 sources/488 unique source-protected hashes; fresh2622 full and final audit remain pending. Native patch/check/approval primitives and original measured artifacts remain unchanged.

Test typed finite policy/event/step/lineage quotas; no dynamic callback/command/model inputs; wrong-owner/unknown cancellation without side effects; cancellation during actual source capture, held model, pending reviewed/unreviewed patch, native write before/after commit, pending/running check, result/send and shutdown. Prove joins/actual receipts, independent-component busy behavior, idempotence and cleanup uncertainty without silent deletes/rollback/retry. Test explicit first-invalid/second-valid controlled model proposal with immutable first attempt, fresh concrete patch/check reviews, denied third/after-action/cancelled retry and charged record quotas. Disclose controlled inference; no fabricated live-model quality claim.

Exercise real local TCP/auth/Origin/private responses and existing typed CLI reviews on disposable fixtures, source/model/old-grant injection denials and default-off startup/lifecycle. Run affected D33–D44 regression plus a fresh exact-source full suite for the new cancellation/action policy, then readonly DB/Qdrant/ACL/model/config/worker/lock/source audit. Preserve first D43 sample and D38 original4/6; any additional full-regression trials are unique separate artifacts, not score replacement. No PASS from code/collection/partial/skip counts. D45 remains next only after these gates pass.

## Verified final gate

Final unchanged source passes2622 full/1559.31s,1264 related/90.68s and74 focused/17.45s,0SKIP/exit0; focused/related are subsets, not additive. All414 sources/488 unique source-protected hashes match. Readonly audit confirms V006, zero app transactions/pending/data/quota/vector/probe/worker/native/advisory locks, original ACL/owner/grant/trigger properties and agreed model/config/dependency/migration data preserved. Existing CORE is healthy and left running. Original D43 first sample and D38 first4/6/two failures remain immutable; the full rerun adds only unique separate actual trial artifacts. Three prior source changes are exactly the registration/factory/router composition described above; native primitives are unchanged. Full [evidence](../evidence/d44-full-regression.json), [audit](../evidence/d44-final-post-audit.json), [retained faults](../evidence/d44-uncertainty-repair.json). D44 PASS within the defined local finite scope; D45 NEXT.
