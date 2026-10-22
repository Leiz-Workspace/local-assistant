# D67 existing multimodal resource and context observations

**Purpose:** Report actual unchanged CORE warm sequential context/media/RAM/VRAM observations with tested metrics and honest scope before resource/model decisions.

**Date:** 2026-10-22. **Status:** PASS local existing-model matrix after full4495 and final readonly audit. [ADR-093](ADR/093-existing-multimodal-resource-and-context-measurements.md).

Original qwen3.5-9b-core/Q6_K/mmproj/PID37256 stays loaded, context32768/parallel1/GPUlayers99/loopback8080. No model/config/resource limit/cache/runtime/package/service change or download.34 new metric controls/6 private evaluator cases PASS/.41s;389 related PASS/22.95s/0FAIL/0SKIP. Three separate full-runner guard controls PASS/.28s. The only historical guarded-document difference is AUDIO_BACKLOG's legitimate post-audit D66 progress closure, exact prior bytes/hash archived and accepted Git2d93d98 bytes pinned separately; all596 prior source and every other protection unchanged/current599.

## First actual matrix

All predeclared phases PASS/18.853s:3 text-before;5 context sizes×3;1 expected overflow refusal;3 native real-speech/provided-reference sparse-frame operations;3 text-after.21 successful text completions/1 app-budget refusal and9 original CORE image completions,3 native audio/video and9 image normalizations. Each media operation uses its own declared synthetic principal and original quotas. All transports/admissions/operations/sampler retired. No outcome-dependent retry, context/source/prompt/oracle repair or alternative model. The literal echo is delivery/capacity under actual token load, not long-context reasoning/retrieval accuracy. Media speech text is supplied/unverified, not ASR.

| Warm sequential phase (3 observations) | Actual template tokens / workload | Min seconds | Median seconds | Max seconds |
|---|---:|---:|---:|---:|
| text-before | 24 | 0.112 | 0.117 | 0.171 |
| context-128 | 191 | 0.086 | 0.090 | 0.176 |
| context-2048 | 2111 | 0.097 | 0.100 | 0.564 |
| context-8192 | 8255 | 0.119 | 0.120 | 1.293 |
| context-16384 | 16447 | 0.150 | 0.152 | 1.776 |
| context-31500 | 31563 | 0.207 | 0.208 | 3.417 |
| text-after | 24 | 0.112 | 0.115 | 0.214 |
| media-provided-transcript-frames | native audio/video +3 images | 2.811 | 2.821 | 3.329 |

Tokenizer count equals reported backend prompt usage for all successful text observations, including31563 near-capacity tokens.34063-token input is rejected by unchanged context_overflow guard in0.049s, no successful generation claimed. Original max512 text output reserve and256 context reserve remain. Standalone current turns are not silently truncated. These are original adapter-layer observations; public HTTP body/UI limits and application concurrency/SLO are not established here.

Times are complete unchanged application-port wall durations, including its internal template/token checks. Separate preflight counting cost is retained per row, outside that wall measure. Original prompt cache/warm sequential behavior remains; repeated near-capacity requests show0.207–3.417s, so the median must not be presented as uncached prefill/cold performance. Three repeats support descriptive min/median/max only. TTFT and decode TPS are NOT MEASURED because responses are nonstreaming. Output tokens/full wall is explicitly an end-to-end output rate; media output-token rate is not measured. No statistically established population p95, load/concurrency/OOM or SLO claim. Text-after marker3/3 confirms observed recovery, not a guarantee for every workload.

## Separately measured resources

81 same-PID/starttick points: process RSS RAM9283.812–10017.594MiB; NVIDIA compute allocation VRAM9386.000MiB throughout. Largest single matching native process observed RSS53.039MiB across20 native process identities. No sum of shared pages is called private RAM; RSS includes shared/mapped pages, GPU allocation includes model/KV/workspace. Native512MiB is address-space policy, not measured RAM requirement. CORE was already resident during CPU audio/video work; its GPU allocation is not audio decoder cost.

The target wait between samples is0.200s; actual completion-to-completion cadence min/median/max is0.231/0.234/0.249s. Collection wall min/median/max is0.031/0.034/0.047s; observer work is not subtracted from workload wall. CORE CPU counter delta1459ticks at100Hz equals14.59 process-CPU seconds, not GPU utilization. Short native processes may be missed between samples. All maxima are finite sampled observations, not true peaks, unique/private RAM, minimum hardware requirements or just model weights. No cold-load/alternative-model resource ranking is inferred.

## Current closure

After the matrix/sampler/native/model work fully retired, a distinct full4495 application regression completed4495 PASS/1737.73s pytest,1738.87s wrapper/0FAIL/0SKIP/exit0 using accepted in-memory readonly Vault paths/live flags/redacted durable logs.244 private final-audit controls PASS/.62s. Final readonly audit PASS599 current source/all596 prior bytes unchanged, exact preserved MD progress-closure exception only, same original CORE PID/start/parameters, original model/config/data/V006/zero source-memory/quota/vectors/probes/workers/locks/ACL-grants-triggers/15 services preserved. D67 local scope is accepted; historical full4265/562-source D62 and original running-status matrix snapshot stay immutable. D68 may now begin after actual closure. D68 registry candidates remain NOT EVALUATED; no download, selection or deployment from this matrix.

[Original result](evidence/d67-first-existing-multimodal-result.json), [measurement freeze](evidence/d67-existing-multimodal-first-freeze.json), [current full freeze](evidence/d67-4495-full-freeze.json), [single progress-document transition](evidence/d67-d66-progress-document-transition.json).

[Completed full](evidence/d67-4495-full-regression.json), [final readonly audit](evidence/d67-full4495-multimodal-readonly-audit.json), [acceptance](evidence/d67-existing-multimodal-acceptance.json).
