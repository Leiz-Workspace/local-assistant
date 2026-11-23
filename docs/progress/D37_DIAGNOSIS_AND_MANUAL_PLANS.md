# D37 source-backed diagnosis and manual plans

**Purpose:** Describe bounded source-cited diagnostic plans and the explicit distinction between a proposed reproduction and executed checks.

**Status:** PASS within the source-selected manual-diagnosis scope. [ADR-055](../ADR/055-source-backed-diagnosis-without-execution.md), [acceptance](../evidence/d37-diagnosis-acceptance.json), [source freeze](../evidence/d37-diagnosis-freeze.json).

Explicitly enable `ASSISTANT_WORKSPACE_DIAGNOSE_ENABLED=1` only with a configured D34 workspace service. Default off; the explanation flag is independent. No host workspace/production flag is enabled by implementation or tests. The local bearer/Origin-protected endpoint is:

```text
POST /api/v1/workspaces/{owned-workspace-uuid}/diagnose
```

```json
{
  "symptom": "The supplied double(3) returns4 but should return6.",
  "sources": [{"path": "calc.py", "start_line": 1, "end_line": 20}]
}
```

The symptom describes user-supplied observations; this endpoint has not verified runtime behavior. D36 source selection, exact line citation rules, prompt/model/budget/root pin/freshness/cleanup constraints remain unchanged. At most3 distinct selected files,4096-byte symptom,32768-byte prompt, existing CORE/fast/temperature0/max768,60-second model-only deadline. No source execution, shell/git/tool-call loop, patches, file writes or another model. Source/diagnosis/plan text remains untrusted.

Supported generated JSON must supply a diagnosis, exact source citations,1–5 plan steps and a manual reproduction with concrete input/setup,1–5 steps and expected result. Step kind is only inspect_source, compare_expected_actual, manual_reproduction, propose_fix or verify_after_approval. Server assigns sequential step numbers. Details/expected observation/manual step at most512 UTF-8 bytes; reproduction input/expected result1024 bytes each; diagnosis4096 bytes; strict model JSON16384 bytes. No model-supplied executed, actual_result, command, shell, patch, locator or identity field is accepted. The server always returns `execution_status: "not_executed"`. Planned fixes/checks do not grant approval or run anything. Missing evidence returns null diagnosis/reproduction and empty citations/plan; blank sources return the corresponding no_sources diagnostic shape without inference.

The service inherits D36 ownership and specializes three default-preserving hooks for prompt, output and blank-source shape. Actual D35 reads capture native hash/stat receipts/root pins; fresh source fences after model delay and before headers reject changed/replaced/deleted sources or roots. Diagnosis drains before explanation/workspace. No database, model, source data or infrastructure migration.

## Observed verification

**477 related PASS/7.22s,0 SKIP,exit0**, including54 new D37 cases and423 prior D36/D35/workspace/auth/API/startup cases.11 evaluated Python files/53 described functions/classes pass Ruff correctness/import/format.1977 collected is **not a fresh1977 full run**; historical D34 full1785 remains separate.

Actual unchanged `qwen3.5-9b-core` on [frozen synthetic cases](../evidence/d37-core-case-freeze.json):1/1 arithmetic defect diagnosed at the expected native source line with exact quote/hash, concrete input3/expected6 manual reproduction, and1/1 absent retry question refused. [Raw synthetic observations](../evidence/d37-core-observations.json) retained. The proposed `double(3)` step was **not executed** by this gate. Authored/same-agent synthetic oracles and a supplied symptom are not independent human review, actual bug reproduction or a general coding benchmark. Existing D36 actual CORE explanation cases still pass after the hooks.

Strict malformed/authority/execution/patch/unknown-step and bounded text/plan validation, actual unchanged source bytes, native source mutation/final-header fence, model cancel/shutdown, actual HTTP/TCP/auth/Origin/scope, default-off dependency and ordered three-service startup rollback pass. Inherited D36 timeout/pin-transfer/send cleanup cases run in the same related suite. Controlled inference/failure tests remain distinct from actual CORE/native/TCP observations. [Final audit](../evidence/d37-final-post-audit.json) verifies V006, empty source/memory/quota/vector/probe/worker/lock inventories, original owners/ACLs/grants and protected hashes.310 unchanged baseline files and11 D37 evaluated files match freeze.

Disable/drain the optional diagnostic service to roll back without data/model migration. D38 separately evaluates the existing CORE plus deterministic tool coding baseline. Approved edits and application command execution remain their later gates.
