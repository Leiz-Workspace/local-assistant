# MODEL-QUALITY-002 — Actual UNRESTRICTED and retained CORE text comparison

**Purpose:** Report the authorized existing-profile trial, paired first outcomes and measured resources without changing agreed models or claiming complete quality acceptance.

Date: 2026-10-24. Status: MEASUREMENT COMPLETE; D14 PARTIAL. [Protocol](MODEL_QUALITY_002_UNRESTRICTED_PROTOCOL.md), [ADR130](ADR/130-isolated-existing-unrestricted-cpu-trial.md), [actual results and all first evidence bindings](evidence/mq002-first-paired-result.json).

| Historical category | Retained CORE | UNRESTRICTED | Weight | CORE points | UNRESTRICTED points |
|---|---:|---:|---:|---:|---:|
| Reasoning |6/8|4/8|20|15|10|
| Coding text |3/8|2/8|20|7.5|5|
| Agent policy text |8/8|8/8|20|20|20|
| Vietnamese supplied-source reading |6/6|6/6|10|10|10|
| Text total |23/30|20/30|70|52.5|45|
| Other original domains |Unscored|Unscored|30|null|null|

30 first UNRESTRICTED adapter requests produced30 real native generations and30 complete profile-valid responses. Exactly one attempt per case; no retry, output repair, oracle feedback or discarded response. All response contracts passed; ten answers were incorrect. Overall100-point scores stay null. Paired cells:19 both correct,4 CORE-only correct,1 UNRESTRICTED-only correct (coding01),6 both failed. This is a small same-agent authored comparison of configurations; original templates differ and CORE is warm GPU while UNRESTRICTED is CPU. No causal model-only, latency, broad capability or independent-human-review claim follows.

All ten UNRESTRICTED failures remain: coding02 returns0 instead of-2; coding03 returns[4,7,10] instead of[2,5,8]; coding05 returns[9] instead of[1,2]; coding06 returns[1,3] instead of[1,9]; coding07 returns7 instead of0; coding08 returnsfalse instead oftrue; reasoning02 returns51 instead of57; reasoning03 returns15 instead of17; reasoning04 returnstrue instead offalse; reasoning07 returns98 instead of70. No same-case rerun or scoring repair. Original CORE23/30, D46first7/10, CE0027/12perarm and CE003first/eventual4/6 stay unchanged.

## Actual memory and isolation

Existing exact UNRESTRICTED GGUF SHA matched unchanged configs before load. Temporary loopback18080, context32768, CPU2, device none, zero GPU layers, no projector/download/default switch. Whole child process **wait4 peak RSS RAM8,053,576KiB, approximately7.68GiB**; sampled peak8,053,328KiB. Hard address-space cap12GiB is a virtual-memory cap, not measured RAM or VRAM. UserCPU385.701855s/system4.302177s. Guard failure null; childPID2873767 exited0 and was reaped. These measurements include runtime/KV/overhead and are not weights-only costs.

Original CORE stayed PID37256/start63900/same command/32K, with its existing GPUallocation9386MiB. No UNRESTRICTED GPU offload was configured; no claimed GPU benchmark. Original CORE recovery passed. 44private preflight controls,104separate profile/tool-authority regressions and19audit-policy controls PASS; independent publication recomputation8controls PASS. These are separate scopes, not additions to the accepted full5674tests. All728application/source/config/test files remain byte-identical to that full snapshot.

[Post-trial audit](evidence/mq002-post-trial-readonly-audit.json) and [joined final web audit](evidence/mq002-web-final-readonly-audit.json) retain original917protected/176inputs/services/data/security/schema/collections and0of24listened labels. Only the previously diagnosed quota updated_at bookkeeping delta remains explicit. No timestamp restoration/restore probe or model/provider/default/data change.

The requested paired text measurement is complete. Missing original multimodal/performance/memory-context/provenance domains, broader quality, rights and owner/product acceptance remain open; no production promotion or agreed model replacement. D70actual listening remains owner-deferred0/24.
