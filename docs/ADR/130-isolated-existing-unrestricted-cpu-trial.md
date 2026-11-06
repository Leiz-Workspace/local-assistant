# ADR130 — Isolated existing UNRESTRICTED CPU trial

**Purpose:** Fulfill the owner's explicit UNRESTRICTED test request without replacing agreed models, restarting the accepted CORE or changing production configuration.

Date:2026-10-24. Status:Accepted for one bounded existing-model text trial under the explicit owner request. No production/default/route/model adoption.

COREPID37256remains loaded onGPU/32K. Its allocation is about9386MiB and total GPUfree sampled5756MiB, insufficient for another full comparable GPUresidency. Preserve that accepted runtime and all728application source bytes. Load the exact existing pinned Q6_KUNRESTRICTEDGGUF in a temporary CPU-only process/loopback18080, no projector/webUI/download/container/schema or shared-service change. This is testing the established optional profile, not replacing CORE. ADR120's earlier no-load test scope is historical; this explicit request now authorizes the separate trial.

PriorityP1originalD14profile evidence; dependency MQ001frozen30cases/unchanged strict scorer/historicalweights/source/artifact hashes. Effort one bounded comparison/audit milestone. Risks:CPU/GPUandcold/warmconfounding, sampled rather than reserved host RAM, address-space fit, partial/timeout scores, text-policy versus actualtools and same-agent/observed-case bias. Do not compare CPU/GPUlatency as model superiority, normalize70text points to100or infer broad quality/license/human acceptance.

Use unchanged D80UNRESTRICTEDtemplate/fast512/temperature0/60s, one request per MQ001case/max30. Adapter uses its original tokenizer, context/budget/model-alias and completion validation. Only this private trial process temporarily redirects UNRESTRICTEDendpoint to its owned server; production YAML/files/routes/defaults remain untouched and COREprofile requests are rejected. Real HTTPrequest/response hooks retain original completion bytes before gateway validation; no fake model reply, expected-answer field, repair, fallback, retry or action grant.

Hard12GiBvirtual address-space cap, CPU2/affinity2/zeroGPU/context32768; no warmup. Preflight MemAvailable>=12GiB; sample RSS<=10GiB and MemAvailable>=2GiB every0.5s, stop on guard uncertainty. Sampled limits do not reserve RAM or prove hostOOMimpossibility. Startup240s, wholetrial2160s, joined20sTERMgrace before owned-groupKILL. Minimal child environment excludes credentials/runtime overrides. Nativewait4retains exact owned peakRSS/user/systemCPU; originalCOREidentity monitored.

Always stop/reap only the owned sidecar and verify originalCORErecovery/source/protected/data/security after it joins. Keep partial/failed outcomes and consumed slots, do not repeat a model request. Rollback stops that exact temporary process and leaves originalCORE/config/models/data/firstbenchmarks intact. No model/license/product/release or deferredD70listening approval is inferred.

Execution: the one authorized trial completed30first requests/20correct/45of70textpoints; all30native/application reply contracts valid, ten quality failures retained. Whole owned child wait4 peakRSS RAM8,053,576KiB under12GiBAS, GPU layers0, no guard failure, exited0/reaped. OriginalCORE identity/context/GPUunchanged. [Actual paired results/resources/audit](../MODEL_QUALITY_002_UNRESTRICTED_SCORECARD.md). No model/default/config/data or production change; no additional campaign scheduled by this ADR.
