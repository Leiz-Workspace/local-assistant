# HAR-008 — Opt-in source JSON contract result

**Purpose:** Record actual native output-contract measurements, integration failures and software validation without replacing the model or historical scores.

**Date:** 2026-11-10. [Decision](ADR/183-opt-in-source-bound-json-output-contract.md), [frozen protocol](HAR008_OUTPUT_CONTRACT_PROTOCOL.md), [public receipt](evidence/har008-output-contract-20261110.json). HAR-008-R1 mechanics remediation is implemented and measured on a fresh R3 cohort. Broader specialist promotion remains **NOT_QUALIFIED**.

## 1. Behavior delivered

`la run --output-contract source-value-quote-v1` selects a finite source-backed JSON mode. Default remains text; the CLI omits the new field in text mode for compatibility with an already running v1 server. Only explicit `workspace.read` calls are admitted. Unknown contracts/caller schemas/mixed tools are rejected.

The host builds a bounded quote catalog from actual retained read snapshots, verifies their hashes/metadata and removes ASCII indentation/trailing spaces from **source lines before generation**. All admitted source lines are grammar alternatives, including irrelevant lines; no oracle answer is used. The mandatory host context declares exact value/quote JSON and null/null for an unsupported answer. The pinned native parser receives `response_format.json_schema.schema`; the host independently validates the untouched first output, types, null pairing, quote membership, complete finish and absence of tool calls.

Validation does not strip fences, trim a model quote, cast values, repair an answer or retry. Rejected native output is owner-only in-memory diagnostic evidence on a failed run; no successful result is published. Signed metadata history keeps only hashes/state and its existing finite failure code. A valid source quote does not establish correct meaning or entailment.

## 2. Retained integration failures

| Campaign | Observed first outcomes | Disposition |
|---|---|---|
| R1 | Three API submissions, two text completions; third failed before constrained generation | INCOMPLETE: synthetic fixture lacked real run/call IDs and workspace/trust/omission metadata. Fixed exact envelope parsing, added native tool regression; did not resume or regrade. |
| R2 | 48 completions; text strict 7/12, 6/12; constrained labels 8/12, 7/12; nine host contract rejections | **Invalid schema-enforcement treatment**: flat schema copied from the README silently became generic-object JSON. The actual pinned C++ parser requires the nested wrapper. Scores and raw outputs remain, and cannot support a schema-enforcement claim. |
| R3 | 48 completions on a new frozen cohort after correction | Measurement complete; results below. |

R1 elapsed 1.888 s; R2 elapsed 31.376 s. Corrected client binding according to `runtimes/llama.cpp/tools/server/server-common.cpp:1312`, not by changing upstream, the schema domain or the score oracle. Two positive development pilots and three adversarial format controls are excluded from scores. The latter requested an outside quote, null with text quote and an indented quote: all three produced valid constrained outputs with the corrected binding.

The original [v1 result](HAR008_PAIRED_EVALUATION_RESULT.md), baseline **5/12**, skill **6/12**, remains unchanged. R1/R2/R3 inputs, first requests/responses/scores and summaries remain under their separate owner-private `data/evaluations/20261110-har008-output-contract-r*` directories. The public receipt records their hashes and dispositions.

## 3. R3 native measurement

Twelve new controlled cases: six source questions, including one Vietnamese case, and six source reviews; four null controls and one source-instruction control. Corpus: `benchmarks/fixtures/har008-source-review-r3.json`. No previous cohort ID/source/question is reused; task families remain controlled and related. Four arms per case, cyclic order with each arm in each position three times. Same approved Qwen3.5-9B CORE/Q6_K, runtime b11557, Fast preset, 512 output tokens, strict context, unchanged skill manifests and one explicit native read.

| Arm | Exact JSON shape | Exact typed value | Exact oracle quote | Strict success | Host contract rejected |
|---|---:|---:|---:|---:|---:|
| Text baseline | 12/12 | 12/12 | 8/12 | **8/12** | Not enabled |
| Text + skill | 12/12 | 11/12 | 8/12 | **8/12** | Not enabled |
| Constrained baseline | 12/12 | 12/12 | 12/12 | **12/12** | 0/12 |
| Constrained + skill | 12/12 | 12/12 | 12/12 | **12/12** | 0/12 |

Within this cohort, each constrained arm has four strict gains and zero strict regressions against its matching text arm. Adding a skill to text produces one strict gain and one regression, net zero. Both constrained arms saturate, so this panel establishes **no additional skill benefit**. Text failures include indentation/null-quote violations; the text-skill undefined-name case incorrectly returns null/null. All are retained.

Campaign wall time **30.657 s**, 48 first completions, zero retries/cleanup failures/unidentified submissions, 12 complete four-arm blocks. All 24 constrained responses independently match the frozen catalog/schema/content hashes and quote origins. Frozen measured source/config bytes remained unchanged. No TTFT, peak RAM/VRAM, load/resource or broad quality acceptance was measured. System instructions and decoding schema change together; their separate effects are not isolated. Same-author synthetic cases, one small source-instruction control, one stochastic draw and development feedback limit generalization. Do not infer cross-cohort causal improvement, independent validation or parity with larger models.

## 4. Software verification

Final invocation: **323 passed, 0 failed, 0 skipped in 3.89 s**, no model calls in pytest. Includes actual filesystem/tool envelopes, default CLI compatibility, output validation/negative boundaries, owner-only diagnostics, history privacy, crash/restart and existing auth/tool/preset regressions.

```bash
uv run --no-sync python -m pytest \
  tests/test_product_context.py tests/test_product_cli.py \
  tests/test_product_assets.py tests/test_product_harness.py \
  tests/test_product_inference.py tests/test_product_browser_scripts.py \
  tests/test_product_generation.py tests/test_harness_history.py \
  tests/test_conversation_context.py tests/test_harness_tools.py \
  tests/test_skill_contract.py tests/test_skill_tools.py \
  tests/test_tool_hooks.py tests/test_run_planner.py \
  tests/test_plan_checkpoints.py tests/test_mcp_adapter.py \
  tests/test_mcp_stdio.py tests/test_inference_observability.py \
  tests/test_application_logging.py tests/test_conversation_auth.py \
  tests/test_stateless_security.py tests/test_runtime_presets.py \
  benchmarks/tests/test_har008.py benchmarks/tests/test_context_priority_probe.py \
  tests/test_source_output_contract.py benchmarks/tests/test_har008_contract.py -q
```

Ruff check and format (18 files), offline lock check and offline wheel build passed. Packaged contract/inference/CLI bytes match source. This is related verification, not a new full D87 regression. Earlier invocations are not added to the final count. Total native completions in this follow-up: 103 (R1 two + R2 48 + R3 48 + five development calls), not 103 independent quality cases.

## 5. Current use and next gate

See [runbook](HARNESS_CLI_DESKTOP_RUNBOOK.md#8-source-backed-json-opt-in). The primary desktop on 7090 was not restarted and still runs its previously loaded v1 code; the new mode needs a process started from the updated checkout. Trial server 7092 was stopped after confirming empty owned runs/skill grants. CORE remained loaded and healthy; no model/config/provider/weights/SDK/Docker/Vault/database/Qdrant change, commit, promotion or release occurred.

HAR-008-R1 bounded mechanics slice is verified; HAR-008 as a whole remains partial. Next: HAR-008-Q2 broader frozen specialist evaluation with unsupported/cross-source/long-context and realistic review cases, separate semantic scoring and actual resource measurements. Skill gain, semantic compaction/memory binding, durable execution/catalog, native installers, production media adapters and release gates remain open. No automatic default activation or model adoption follows from this panel. Rollback: omit the output-contract option and retain all evidence.
