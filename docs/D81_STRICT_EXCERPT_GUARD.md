# D81-FMT-001 — Strict excerpt admission

**Purpose:** Describe the optional deterministic output guard, its verified behavior and remaining model-format gate.

**Status:** Guard component VERIFIED; original model-format evaluation remains OPEN. [ADR 125](ADR/125-host-pinned-profile-excerpt-validation.md), [actual verification](evidence/d81-excerpt-guard-verification.json).

The previous CORE response quoted whole source paragraphs for code and web. The new guard can withhold such a reply when the host already knows the allowed fact-only source spans. It returns a receipt only for unchanged JSON with exactly those excerpts. It does not create a better answer or change the original 1/3 format score. There were zero new model calls.

Use `ProfileExcerptGuard` with the authenticated owner/workspace, explicit existing profile/model, exact expected prompt digest, immutable `(source_id, text)` tuples, `(source_id, start, end)` Unicode codepoint spans and expected top-level answer field names. The template digest is bound to the existing committed profile template. Call `validate(owner, workspace, reply)` on the trusted `ProfilePromptRun` result before publishing it. A rejection must withhold output; automatic retries/repair are not part of this component.

One to eight sources, each at most 4096 characters and together at most 16384 UTF-8 bytes, and replies at most 16384 UTF-8 bytes are admitted. Spans must be nonempty, unique even with overlapping matches and exact under original whitespace/Unicode. Citation order may differ, but missing/duplicate/foreign citations, invented quotes, extra fields, malformed/duplicate-key/nonfinite JSON, model/owner/workspace/prompt/source changes and incomplete completions fail closed. Logs contain finite codes and counts, not prompt/reply text or actor IDs. Receipt offsets are codepoints, not UTF-8 byte offsets.

This is a format/provenance check. The host still chooses the permitted spans, validates answer values/semantics and maintains source lifetime/authorization. A receipt is neither a factual correctness certificate nor a capability. Existing grounded-answer behavior/templates/routes remain unchanged; no production route uses this new component yet.

## Executed verification

66 new tests and 161 related tests: **227 PASS, 0 FAIL, 0 SKIP in 1.56 seconds**, Ruff PASS. Related checks cover profile composition, retained/native cross-domain fixtures, deterministic harness routing/load, plans/checkpoints, hooks and existing grounded-answer/service logic. Six independent positive text cases cover Vietnamese, code, identifiers, astral Unicode, decomposed accents and original CRLF/tab sequences. Negative cases include overlapping `aa` in `aaa`, source/prompt tampering, duplicate citations, longer literal source text and malformed output. The original D81 fixture is unchanged and rejected; no edited alternative model reply is presented as a benchmark.

Reproduce with:

```sh
uv run --no-sync python -m pytest tests/test_profile_excerpt_guard.py tests/test_profile_prompts.py tests/test_cross_domain_scenario.py tests/test_cross_domain_retained_grounding.py tests/test_harness_tools.py tests/test_harness_load_scenario.py tests/test_run_planner.py tests/test_plan_checkpoints.py tests/test_tool_hooks.py tests/test_tool_hooks_integration.py tests/test_grounded_answer.py tests/test_grounded_source_groups.py tests/test_grounded_service.py -q
```

All 707 existing D87 snapshot files, 917 protected files and 176 original inputs match retained hashes. The only original D70 source exception remains the previously reviewed ADR 121 stateless-chat fix; the other 660 source files match. Actual D70 listening remains 0/24. The prior full 5405-test result is preserved as snapshot evidence; this follow-up has related regression coverage, not a new full-suite claim.

The remaining D81 task is to demonstrate model adherence to a separately reviewed protocol on frozen cases and then integrate an appropriate admission policy with product source authorization. This guard alone does not complete that task. It proposes no model replacement and does not change release gates.
