# ADR-055: Source-backed diagnosis and reproducible plans without execution

**Purpose:** Define D37 structured diagnosis/plan and manual reproduction contracts on accepted D36 source ownership.

**Date:** 2026-10-20 (Asia/Ho_Chi_Minh)

**Status:** Accepted/implemented after D36 `512c42b`:477 related PASS/7.22s,0 SKIP,exit0,54 new cases and clean audit. Original CORE1/1 source-cited diagnosis/manual reproducer and1/1 absent refusal; [acceptance](../evidence/d37-diagnosis-acceptance.json). Proposed steps not executed; no fresh1977 full claim.

## Priority, dependencies and risks

P1, one bounded diagnosis milestone after D33–D36. Reuse explicit source selection, strict D35 reads, fixed CORE, root pins and D36 post-model/pre-header validation. Risks are invented execution claims, unsupported diagnoses, vague irreproducible steps, generated command/patch authority and duplicating resource ownership. No model/config/infrastructure/database/source data changes or command/write capability.

## Decision

Expose a separately default-off authenticated `/workspaces/{id}/diagnose` endpoint for a bounded symptom and1–3 explicitly selected source files. A new service subclasses D36 ownership/model behavior, overriding only prompt construction, result resolution and blank-source shape through three small documented default hooks. Existing explanation behavior must remain unchanged and its complete related gate must pass.

Generated strict JSON has exactly status, diagnosis, citations, plan and reproduction. A supported diagnosis requires exact D36 line quotes,1–5 ordered plan steps and one manual reproduction description. Step kinds are fixed: inspect_source, compare_expected_actual, manual_reproduction, propose_fix, verify_after_approval. Each step supplies bounded details and expected observation; ordering is server-derived. Reproduction supplies bounded input description, manual steps and expected result; there is no model-supplied executed/actual-result/shell/patch field. The server always marks execution_status=not_executed and source content/diagnosis untrusted. Missing evidence requires null diagnosis/reproduction and empty citations/plan. Exact quote validation is mechanical; correctness/usefulness of the proposed diagnosis/reproducer is separately checked against frozen synthetic bug oracles.

Source text, symptoms, generated plans and reproduction steps are data. They are never executed, written to source, adopted as tool calls or promoted into approval. There is no automatic test command, shell/git/subprocess evaluation or generated patch. Actual command reproduction and approved edits need later D39–D45 gates. A plan may propose a future fix/review, but this endpoint cannot apply it. User-visible output explicitly distinguishes a manual plan from a completed runtime reproduction.

Question/prompt/model/output/source/receipt/cancellation limits remain D36; additional plan/reproduction text limits must fit the existing response budget. Startup requires the workspace service, defaults off, and drains diagnosis before workspace. Logging retains stable counts/status only. Preserve all selected models and prior accepted bytes except the necessary three prompt/result/blank-source hooks and router/lifecycle composition.

## Acceptance and rollback

Verify strict malformed/extra/executed/patch/unknown-step rejection, abstention, ordered bounded plans, exact source citations, explicit not_executed status and actual source bytes unchanged. Test native source/root/delivery mutation and cancel/timeout/send/startup cleanup through inherited ownership; rerun D36/D35/workspace/auth tests and actual original CORE explanation cases. Run the unchanged CORE on frozen synthetic diagnosis/reproducer cases with authored expected bug location and input/result; retain every failure, do not claim those generated manual steps were actually executed. Disable/drain the diagnosis endpoint to roll back; no model/data migration. D38 coding baseline remains next after actual D37 acceptance.
