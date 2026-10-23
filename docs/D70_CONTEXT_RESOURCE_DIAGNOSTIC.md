# D70 context and GPU diagnostic

**Purpose:** Investigate the owner's context/VRAM hypothesis after the first ADR-105 service error, distinguish local resources from remote execution, and retain measured limits without altering passed components.

**Date:** 2026-10-23. **Status:** Readonly investigation complete; remote OOM/root cause unconfirmed. D70 naturalness remains open; D71 has not started. [Actual diagnostic](evidence/d70-context-resource-diagnostic.json); [retained first service failure](evidence/d70-specialist-campaign-first.json).

## Measurements and execution locations

| Component | Verified observation | Meaning |
|---|---|---|
| Local GPU | RTX4070TiSUPER; total16376MiB, used10267MiB, free5675MiB at the recorded sample | A current point sample, not the historical failure-time peak or an OOM exclusion |
| Local CORE | PID37256,9386MiB GPU allocation, `--ctx-size 32768`, parallel1; `/props` independently reports32768 | Existing llama.cpp server, not the failing external evaluator |
| Local specialist client | Earlier command maxRSS43276KiB; uploads and HTTPS/SSE only, no neural model loaded locally | Client RSS is RAM, not provider VRAM |
| Earlier local3B evaluator | ADR-104 ran CPU-only within12GiB address space, observedRSS9.723GiB RAM; strict8/12failed | Lowering CORE GPU context does not fix the retained semantic failures |
| External SpeechJudge | Runs on the community Space's ZeroGPU worker; the first complete event contains `GPU task aborted` | Provider execution failure; no provider memory/peak/OOM/cancellation evidence available |

Local kernel logs visible in the retained three-minute window around the first request contain0matches for the selected OOM/NVRM-Xid/CUDA-error terms, command exit0. Absence of kernel messages does not exclude an unlogged local CUDA allocation failure, and cannot say anything about the remote worker. No local GPU peak was measured during that earlier request.

Historical [D67 measurements](D67_EXISTING_MULTIMODAL_BENCHMARK.md) retain successful31563-token prompts under this original32Kconfiguration and81same-process samples of9386MiB GPU allocation. That is earlier local capacity/delivery evidence, not a general OOM or quality guarantee; it does not diagnose the remote Space.

## Controls the remote API actually exposes

Fresh credential-free metadata GETs confirm the same repository/deployed revision `e16fd85d230ac043091476eb78faa6c2e24c5c66` and the exact four API parameters: `target_text`, `audio_path_a`, `audio_path_b`, `num_generations`. The earlier campaign already used one generation, the minimum exposed value. No public parameter controls context length, `max_new_tokens`, GPU duration or GPU size. Adding unsupported arguments to the client cannot configure that backend.

The retained exact [Space source](https://huggingface.co/spaces/Den4ikAI/SpeechJudge-GRM/blob/e16fd85d230ac043091476eb78faa6c2e24c5c66/app.py), SHA256 `5048833ee621a8e6d1e2cb670d622d4b0c12d1aab1ee0f3f4b33334a048d439c`, declares `@spaces.GPU(duration=30)`, moves the model to CUDA inside that decorated function, and fixes `max_new_tokens=1024`. Output-token allowance is not the context-window size. The [official ZeroGPU documentation](https://huggingface.co/docs/hub/spaces-zerogpu) describes provider-side allocation, runtime duration, and recommends module-level CUDA placement rather than moving models inside the GPU-decorated function.

A30-second provider allowance that also encloses transfer/processing/generation is a concrete investigation lead. It is **not proof that duration caused this error**: the78.37-second client wall time also includes metadata, uploads, queueing, SSE and CORE checks. No phase timing, remote traceback cause beyond the retained wrapper error, actual loaded weights or GPU memory telemetry is available. RUNNING metadata still does not establish healthy inference. No user quota or capacity claim is inferred from public documentation.

## Decision and next dependency

Keep the working local32KCORE and all model/config/data/runtime bytes unchanged. Reducing local context can affect a local model's KV/cache allocation, but it cannot reduce another machine's GPU memory or change the remote request's fixed output-token/runtime limits. The amount a local reduction would save is unmeasured; do not claim proportional total-VRAM savings. No restart, GPU reset, model unload, extra download, waveform clipping, prompt reduction, parser repair or new media request was performed. The owner's permission to reduce context if useful is retained; no additional permission is needed merely to inspect or design a local reduction.

The existing P1 `AUDIO-EVAL-REVIEWER-RELIABILITY-001` still needs an available qualified auditory route. Next useful dependency work is provider-side recovery/verified controls or an explicitly assessed controllable evaluator, not a blind retry against this unchanged API. Effort: one source/availability review plus a fresh preregistered evaluation milestone if feasible. Risks: missing provider logs/controls, repeat service failure, unsupported VI, external retention and confusing output caps with context. No new model/replacement/campaign is selected or scheduled. Rollback of this documentation-only investigation requires no service action; original24pending labels and failed first observations remain intact.

Six existing fixed-interface/one-generation/retired-policy controls PASS in0.18s,0FAIL/0SKIP; no new source or tests were written. The prior355related software tests remain historical evidence of the unchanged code, not a fresh355-test invocation. Readonly verification preserves645source files,917protected hashes,176original inputs, prior first raw response and24pending labels; original15services/security/V006/vector/model/data/Brave and sameCORE identity/text recovery pass. No audio quality or human MOS was measured.
