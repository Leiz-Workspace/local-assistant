# ADR 129 — Explicit bounded visible-failure feedback

**Purpose:** Add an optional owner-requested second proposal after known-applied code fails its originally selected visible tests without widening D44 retry or native action authority.

Date: 2026-10-24. Status: Accepted for opt-in implementation and validation under the owner's continuous engineering instruction. No route/default/production activation or new model campaign is implied.

## Context and assessment

CODE-EVAL-002 measured baseline7/12 and concise7/12 on fresh cases; the issue hint is not adopted. Current D44 allows a second component-free failed proposal only, with five lineage stages. Reusing that retry after an applied edit would violate the accepted contract. Existing known edit, check and source receipts make an independent explicit feedback step possible.

P1 CODE-EVAL-003, dependency original owner/source/checkpoint/check/CORE and first-score evidence. Effort one guarded service/native-test milestone followed by separately frozen quality measurement. Risks: replaying known writes, hidden-test leakage, treating arbitrary stdout as authority, wrong-owner results, stale tests, cancellation races and erasing first failures.

## Decision

Add an unregistered optional subclass of the existing controlled service. Keep ordinary propose/apply/check/cancel behavior and every existing D44 limit unchanged. After one original proposal, known applied patch and complete persisted visible native test exit greater than zero, the authenticated owner may explicitly request one new proposal. The second proposal is a new ordinary workflow with its own fresh reviews, linked by bounded server metadata; the two-workflow feedback path allows at most two model proposal slots and eight ordinary stages. No model, source or test output supplies a grant. Direct independent owner workflows retain their existing limits; this is not a global owner quota or unattended agent.

Only the originally selected test paths/hashes are eligible. Reject uncertain/cancelled/incomplete/persistence-degraded observations, failed scope/profile/source bindings and nonpositive/signal exits. Feedback contains exit status and hashes/paths, **no stdout/stderr or independently held-out job**. Full currently applied target plus unchanged visible tests are recaptured by the original native source guards. Preserve the original system template and budgets; add one bounded metadata note to the explicit child issue. Reject issue overflow rather than truncating data. The original model output/check result stays immutable and separately scored.

Charge the second slot before await; no refund after source/model failure or cancellation. Track child identity during synchronous registration, reject another feedback child or legacy retry of the child. Fail nonqueued on concurrent requests. Recheck parent evidence before publication; if it changes/cancels, retire only the newly pending child capability through the existing joined cancel path. Never roll back the already-applied parent or automatically run the second patch/check.

No HTTP route, API flag, model/default/provider/config/Vault/schema/database/collection or dependency change. Rollback omits the optional class and retains original services/first evidence. A future route/product integration requires separate review and complete applicable regression. Fresh multi-attempt quality evaluation must record first-pass and second-proposal results separately, use new predeclared data and leave hidden tests out of feedback; no old case is regenerated here.

## Verification and acceptance

Test real disposable native first failure, second pending proposal, fresh distinct reviews, known current source and unchanged tests/history; reject third attempts, aliases, foreign scopes, stale captures, malformed/uncertain receipts, passed tests, non-test profiles and chained retries. Verify slot consumption, joined cancellation, parent drift and legacy behavior. Do not mark quality improvement, production adoption or project completion from these service tests.


## Actual implementation and verification — 2026-10-24

Optional subclass implemented in commitfe73da6, existing723source files unchanged.31service controls pass within the new complete728-file/5674-test full suite,1798.59s/0FAIL/0ERROR/0SKIP/exit0. Separate post-join test with a genuinely approved exact child patch grant verifies uncertain retirement denies workflow application before the known first edit can change:1PASS1.16s. Offline production-only import/ASGI smoke and private audit/delivery guards pass. [Final source/runtime/data audit](../evidence/ce003-full-acceptance.json) preserves sameCORE/models/config/data and original review labels, explicitly retaining the established operational quota timestamp delta.

[Separately predeclared fresh campaign](../CODE_EVAL_003_FIRST_SCORECARD.md) completed6cases/7actualCORErequests: first4/6,eventual4/6,one eligible second still fails. No quality improvement or model/default/route/product adoption. Every first reply/native failure/review rejection is retained. This record accepts only the optional local implementation and measured evidence, not general coding quality or release.
