# D14 — Paired bounded reasoning diagnostic

**Purpose:** Preregister a fresh text comparison to investigate factual failures without replacing models or reusing scored questions.

Date: 2026-10-26. FROZEN BEFORE FIRST LOAD. [ADR-135](../ADR/135-bounded-request-local-reasoning-comparison.md). This diagnostic evaluates a hypothesis; it is not the original42-case acceptance gate.

## Inputs and conditions

Twelve new questions per profile: reasoning3, Python5, source-policy3, Vietnamese1. Include fraction arithmetic, equation, XOR, loop, slice/alias, comprehension, dictionary zero/default, short circuit, exact status labels, authoritative state and a Vietnamese identifier. Arithmetic/Python references are independently checked by tests. Both profiles receive the same corpus. Source labels appear only in legitimate supplied source text, never as enum/const/default/description in schema.

For each question, measure exactly one direct and one thinking response; alternate their order by case index. The entire question, system template, structural schema, fixed model alias, temperature0, max1024, no-cache and reasoning_format=deepseek are matched. Only enable_thinking and its declared budget differ: false/0 versus true/512. No answer repair, label extraction, hidden oracle feedback, model-generated code execution, fallback, neural retry or old-question replay.

The clearer exact-label instruction applies to both conditions. Any comparison with older scores is descriptive only; only the matched fresh pair can inform the reasoning hypothesis. Save first request/native response/measurement separately by profile, case and condition. Never log raw reasoning/answers; only bounded result codes/counts. The native reasoning field must be nonempty in thinking and empty/absent in direct. Missing condition evidence invalidates the paired diagnostic regardless of final correctness.

## Boundaries and acceptance

At most48generations, two sequential owned18080GPU workers using the original configured models/projectors/runtime32K/GPU99/thread2/batch512/ubatch128/reasoningoff/offline. Request-local override only; no configuration/default/production changes. Preflight14GiB RAM and GPU free; retain sampled RSS12GiB/VRAM14GiB/MemAvailable4GiB/freeGPU512MiB, request90s, campaign2400s, owned cleanup20sTERM/10sKILL. Thirty seconds between workers waits only for resource release and never retries a load/generation.

Require both exact twelve-case condition cohorts/profile, one dispatch each, observed native conditions, five distinct passed provenance checks, exit0/reaped/no resource guard and original baseline restored. Report format, exact facts, output tokens and total wall time separately for both conditions/profile. Incorrect typed values fail, even with valid reasoning metadata/schema. A valid diagnostic may show no improvement; process exit0 means valid accounting, not quality PASS.

Only12/12 exact thinking answers per profile with all evidence/cleanup satisfied permits considering a separately frozen full fresh42-case validation. This diagnostic cannot claim42/42 quality, vision/context/stream qualification, universal capability, a model choice change or release. Original first scores, gate FAIL, old freezes and raw outputs remain immutable.

## Execution and audit

Code/test/protocol/ADR, original runtime and model/provenance bindings, current730-file application manifest and the complete corpus are hashed in `docs/evidence/d14-reasoning-trial-pre-inference-freeze.json` before first load. Run once with `uv run --no-sync python -m benchmarks.scripts.d14_reasoning_trial`. Existing output directory refuses execution. First observations go to `data/backups/d14-reasoning-trial-20261026`; failures are retained. This research test does not access Vault/database/Qdrant or alter Docker/services/data. Scoped tests are not a new full-suite result.
