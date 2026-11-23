# HAR-008-Q2 — Controlled maintenance and resource protocol

**Purpose:** Freeze fresh semantic cases and observed resource/timing definitions before native answer generation. [ADR-184](ADR/184-controlled-maintenance-and-observed-resource-evaluation.md).

## Corpus and first outcomes

`benchmarks/fixtures/har008-q2-maintenance-v1.json`: 24 new same-author controlled cases, four in each category: source-supported, source-unsupported, source-long, review-defect, review-safe and review-cross-file. Twelve source tasks/twelve reviews; ten null controls. Thirty-four source files, including early/late target placement in four roughly 8 KiB records, obsolete distractors and source instructions. Review fixtures represent UTF-8 quotas, inactive administrators, zero/None, chunk boundaries, cancellation and caller preconditions. Source snippets are never executed. Exact integer/string values, unique target review line numbers and complete canonical quote oracles are defined before generation; uncertainty/conflicting evidence requires null/null. These remain controlled cases, not independent human annotations or actual user-repository defect findings.

Four arms per case: text baseline, text skill, constrained baseline, constrained skill. Rotate order by case index: each arm occupies each position six times. Same approved CORE/Q6_K/runtime pin, Fast, 512 output tokens, strict context, unchanged skill manifests, one or two actual native reads. Catalog uses all retained lines, including distractors. Freeze corpus/oracles/source/skill/runner/product/config hashes and options in a new exclusive private directory before any completion. Exact-shape, typed-value, quote and strict scores use the unchanged first response without extraction, coercion or repair. Contract failures retain raw diagnostics, remain failures, and are not retried. Transport/software/context-binding/drift stops the campaign and retains partial receipts.

Quality bound: 96 first calls, 1,200-second campaign, existing 120-second product task deadline. Each completion must retain every requested source and exact skill binding. Save per-attempt request/response/score/raw resource samples; delete only the retained campaign terminal run and newly created grants. Never overwrite prior cohorts or promote from pytest results.

## Resources

Require an explicit native PID and start ticks. Observe `/proc` RSS and lifetime HWM in KiB plus summed nvidia-smi process allocation in MiB. Resource sampling occurs before/during/after each request; interval 0.2 seconds plus query overhead. API latency excludes baseline/final queries but includes concurrent sampling and 0.1-second polling quantization. A failed sample is INCOMPLETE; PID changes never become a new silently accepted target. Sampled maxima are not absolute peaks. Lifetime HWM predates this campaign, GPU allocations can include preallocated weights/KV/cache, and other host work can affect timing. No unload, cache reset, runtime cap/context/config change or new model/SDK.

## Separate streaming timing replay

Predeclared case IDs: `approved-retry-delay`, `long-maintenance-2`, `review-safe-cancellation`, `review-caller-stale-token`. Replay each twice: constrained baseline and constrained skill, alternating which arm goes first, eight calls total. Use the same frozen sources, task, prepared messages, exact skill bytes, schema, Fast512 and loaded CORE, with native `stream=true`. Preserve exact request/raw SSE events; this is benchmark-only transport replay after quality measurement, not an additional quality outcome or deployed product streaming contract.

Measure wall time from native request start to first nonempty `delta.content`, ignoring null/role-only deltas, plus final DONE. Require complete stop and independent reconstructed output-contract validation; retain partial events and stop on invalid/incomplete streams. Record prepared input tokens and resource samples. Existing KV/cache/weight residency remains; descriptive first-text timing is not cold-start, physical GPU token generation, SLO or task-API TTFT. Bound eight calls/no retries, 120 seconds per call and 1,000 seconds overall.

## Disposition

Report all category/arm results, paired gains/regressions and failure examples, resource sample availability/units, timing scope and missing prerequisites. A complete bounded measurement does not close broad specialist qualification, establish larger-model parity or adopt a model. Skill and model choices/defaults remain unchanged. Stop owned probe7092 only; keep primary desktop7090 and CORE8080 available. Preserve all historical scores and prior release gates.
