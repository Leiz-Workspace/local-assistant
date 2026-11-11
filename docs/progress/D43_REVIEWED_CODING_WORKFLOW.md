# D43 reviewed coding workflow

**Purpose:** Document the finite issue→CORE plan/full-file proposal→diff→separate edit/check approvals→snapshot tests→trusted summary workflow and its actual evidence limits.

**Status:** PASS (defined local finite reviewed workflow scope). **1190 related PASS/72.99s,0SKIP,exit0**, plus separately preserved first actual CORE sample **1 PASS/4.61s**;87 new cases,405 source/434 protected hashes and clean readonly audit. Not one1191-case invocation.2548 collected is not a fresh full; accepted D42 historical full2461 remains separate. [Acceptance](../evidence/d43-workflow-acceptance.json), [related](../evidence/d43-related-regression.json), [audit](../evidence/d43-final-post-audit.json), [ADR-062](../ADR/062-finite-owner-reviewed-coding-workflow.md), [freeze](../evidence/d43-workflow-freeze.json), [first live sample](../evidence/d43-core-live.json).

## Finite behavior and limits

The owner explicitly selects an issue, one existing eligible Python target,1–3 distinct selected test files with expected raw hashes and one existing D42 profile. Source path/file/UTF-8 limits remain unchanged; complete selected bytes and native context are revalidated after generation and again after checkpoint preparation before publishing a pending workflow. No generated path, shell command, model routing, owner, runtime or resource override is accepted.

Established CORE/fast/temperature0/max_tokens2048 generates one exact JSON object containing `plan` and `replacement`. No new model is loaded or selected by this feature. Issue<=2048 UTF-8 bytes, sources<=32768 bytes, full prompt<=32768 bytes, completion<=16384 bytes,1–5 plan strings<=512 bytes and complete replacement<=8192 bytes. Prompt overflow fails before inference without truncating sources. Generation is joined and bounded60s. Syntax/module/function/class descriptions are checked without importing or evaluating generated source on the host; this is not security sanitization or a correctness proof.

One workflow has at most one model-port attempt, one admitted edit attempt, one check-capture attempt and one admitted native attempt. Wrong/pending linked-approval preconditions allow the owner to finish the pending review; admitted failures do not authorize retries/refunds. Failed/cancelled workflow histories stay charged:16 globally/4 owner,128KiB canonical JSON each/2MiB retained records. Component approval, source, storage and runtime ceilings remain independently enforced. There is no eviction, implicit rollback, old-grant resume or shared durable workflow authority.

Model observations retain exact bounded base64 raw prefixes with SHA256, byte counts, truncation and encoding metadata; invalid/oversized/truncated/extra-field completions are retained as failed attempts, without extraction/repair retries. Source, raw model/program output, bearer and nonces are excluded from audit logs; IDs/states/counts/hashes remain auditable.

## Explicit API stages

`ASSISTANT_CODING_WORKFLOW_ENABLED` defaults to0. Enabled startup requires the same live workspace/approval/checkpoint-patch/check services. No config/env file or production root is changed. Drain workflow operations before checks→checkpoint→approval→workspace.

All routes are local authenticated owner-only under `/api/v1/workspaces/{workspace_id}/coding-workflows`, with bounded strict JSON, foreign-Origin rejection, private/no-store and nosniff headers. Unknown/foreign workflow lookups are masked. Every normal operation uses nonqueued admission.

| Method/path relative to the collection | Meaning |
|---|---|
| `POST /` | Read exact selected context, call CORE once and publish the complete checkpoint-backed pending diff; no edit/check execution |
| `GET /` | List bounded own workflow identities and last-observed states |
| `GET /{workflow_id}` | Read own bounded untrusted plan/model observation and component receipts/summary |
| `POST /{workflow_id}/apply` | Attempt only the linked already-approved patch UUID once |
| `POST /{workflow_id}/checks` | Explicit empty JSON action: capture the known applied target SHA plus unchanged originally selected test hashes and create a different pending check approval |
| `POST /{workflow_id}/run-checks` | Attempt only the separately approved linked immutable check snapshot once |

The collection endpoint itself has no trailing slash requirement. Proposal example:

```json
{
  "issue": "Fix the selected integer addition while retaining unaffected statements and audit logs.",
  "target": {"path": "sample.py", "expected_sha256": "<64 lowercase hex characters>"},
  "tests": [{"path": "test_sample.py", "expected_sha256": "<64 lowercase hex characters>"}],
  "profile": "python_unittest"
}
```

Review the returned patch's `approval_id` using the existing [CLI](D39_EXPLICIT_APPROVAL_REVIEW.md). Type its exact UUID; then explicitly call `/apply` with `{"approval_id":"<that UUID>"}`. A successful known applied receipt does not run tests. Explicit `/checks` creates a new complete D42 review of updated target/test/runtime/policy hashes. Type this second UUID in the CLI and separately call `/run-checks` with it. A patch grant never approves a check, model text never approves either, and reading a summary never executes an action.

Typical states:generating→awaiting_patch_review→applied→awaiting_check_review→completed. Actual failed/cancelled/uncertain stages retain known component IDs/receipts independently. Model/source failure is a failed proposal DTO, not a hidden successful repair. A failed later check capture keeps an already applied edit/checkpoint; there is no automatic restore or retry. Request-task cancellation and shutdown join owned model/native work. TCP disconnect alone is not claimed to be an automatic cancellation hook. D44 defines additional hooks/retry/cancellation semantics.

## Truthful summary

Summary fields come from trusted component receipts: known applied SHA/checkpoint, tested snapshot source version, actual native start/outcome/exit and uncertainty data in the component result. `quality_evaluated=false`, `output_is_untrusted=true` and `current_source_observed=false` remain explicit. Native exit0/printed PASS is not general correctness or permission. The test applies to its captured snapshot; another owner operation may subsequently change live files. Process-local last-observed history is not renewed action authority, source freshness or durable grant recovery.

The original D41 edit/restore and D42 direct APIs remain independently owner-authorized. Cancellation of a workflow/request does not retroactively revoke a separately approved component grant. No pending-workflow revocation endpoint, cross-worker history, production shell/framework support, larger/multifile transaction or all-crash recovery is claimed.

## Actual visible sample and verification

The [sample/oracle artifact](../evidence/d43-visible-sample-case.pending.json) was frozen before inference and keeps its original planned label as historical provenance. The separate [actual report](../evidence/d43-core-live.json) records the first original CORE application-port call, four host-authored native assertions, two typed fixture approvals, checkpoint-backed edit, isolated unittest and retained summary. No score selection or model replacement.

The independent bounded structural oracle verifies that the generated module AST equals the frozen original with exactly subtraction changed to addition; all descriptions, audit calls and unaffected statements remain. Actual generated bytes differ from the reference formatting, so `candidate_bytes_match_reference=false` is retained; byte equality is not the frozen structural gate. The exact actual candidate SHA is bound into patch review and subsequent snapshot. Fixed trusted test bytes remain unchanged, native exit0/one completed unittest confirms the four fixed assertions, and controlled final source inspection is separate from the API's general no-freshness claim. This is a visible authored sample composition demonstration, not unseen/independent-human evaluation or general model quality.

Other tests disclose controlled inference while using real native roots/Git/checkpoints, exact approvals, source context drift, quota, cancellation after native start and after commit, component expiry, default-off startup, dependency mismatch, later startup failure, TCP/CLI, strict/auth/Origin/foreign/body gates and actual lost ASGI edit delivery. [D38 original4/6 and two failures](D38_CORE_CODING_BASELINE.md) remain immutable. Complete current and historical file versions are retained privately under `data/backups/`. [Evaluated backlog](CODING_AGENT_BACKLOG.md) preserves conditional runtimes, larger edits, explicit retention and durable authority dependencies.

First related invocation1188 PASS/2 FAIL/exit1 is [retained](../evidence/d43-core-unavailable-regression.json): the pre-existing CORE process was absent on8080, same boot and unchanged source hashes; cause of stopping is unobserved. Resuming the exact configured existing CORE/vision restored health; required related rerun1190 PASS. No skipped test, altered model choice, failed-score replacement or rerun of the first D43 sample.
