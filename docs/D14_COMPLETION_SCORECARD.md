# D14 — Completed measurements and retained quality findings

**Purpose:** Close the missing D14 measurement/date/lifecycle work and state the actual model disposition without changing agreed models, criteria or historical results.

Date:2026-10-26. **Measurement COMPLETE; strict-format quality NOT QUALIFIED; no release approval.** [Preregistered protocol](D14_COMPLETION_PROTOCOL.md), [ADR132](ADR/132-d14-existing-profile-domain-completion.md), [independent first-result verification](evidence/d14-completion-first-result.json), [historical date/scope reconciliation](D14_HISTORICAL_RECONCILIATION.md).

## Original weights, complete measured coverage

| Domain | Weight | CORE result | CORE points | UNRESTRICTED result | UNRESTRICTED points |
|---|---:|---:|---:|---:|---:|
| Reasoning, retained first text cases |20|6/8|15|4/8|10|
| Coding text, retained |20|3/8|7.5|2/8|5|
| Agent policy text, retained |20|8/8|20|8/8|20|
| Vietnamese text, retained |10|6/6|10|6/6|10|
| Fresh multimodal, whole strict JSON |10|2/5|4|1/5|2|
| Fresh streaming contract under declared deadline |10|0/3|0|0/3|0|
| Fresh near32K context, whole strict JSON |5|4/4|5|0/4|0|
| Local pinned provenance checks |5|5/5|5|5/5|5|
| Local mixed-date composite |100| |**66.5**| |**52.0**|

Each profile has42model questions (30retained first text cases plus12new), with5additional provenancechecks.26new native generation dispatches total:24scored responses plus2intentional cancellation streams. No repeated CORE/question, score repair, automatic retry or old-answer replacement. The original MQ001/002overall fields remainnull; these new100-weight composite values describe the explicitly operationalized local protocol, **not universal capability percentages**. OldtextCOREwarmGPU/UNRESTRICTEDCPU/template/date differences remain; the new domains alone used identical sequential GPUsettings. This is not a fully matched-hardware rerun of all42questions.

## What the failures actually mean

All24new scored responses completed valid native identity/usage/stop contracts. COREfailed three image cases solely because of Markdownfences; UNRESTRICTEDfailed four image cases because of fences and, for the table, added prose. The visible extracted image values match the supplied references; **they receive no repaired numerical credit** under the frozen whole-response criterion.

COREretrieved allfourreleasecodes in complete near32Kdocuments and returned exactJSON. UNRESTRICTEDalso visibly returned allfourcorrectcodes, but each response was fencedMarkdown, so its frozen strict score remains0/4. Do not describe this result as failure to retrieve the codes or as evidence of universal long-context quality.

Allthreeplanned streaming replicates/profile returned the integer sequence as a bareJSONarray instead of the requested object with key`sequence`. Hence0/3functional contract points. The10-point performance-domain operational criterion included correct complete output under60s; zero points **does not mean zero throughput, timeout or slow inference**. It exposes a format-compliance gap in this particular unconstrained native prompt path. No forcedJSONdecoder, extraction, prompt retuning or second answer was introduced after seeing results.

| Measured quantity | CORE | UNRESTRICTED |
|---|---:|---:|
| Streaming wall times, seconds |2.035 /1.712 /1.623|2.712 /1.698 /1.570|
| First nonempty complete content-frame arrival, seconds |0.542 /0.133 /0.072|1.116 /0.150 /0.077|
| Nativewait4whole-process peakRSS RAM, KiB |8,080,544|7,282,876|
| Approximate whole-process peakRAM, GiB |7.71|6.95|
| Sampled processVRAM peak, MiB |8,882|8,548|
| Actual context retrieval prompt size |30,000–32,000tokens, allfour checked|30,000–32,000tokens, allfour checked|

Frame-arrival times are client-observed upper bounds including buffering/capture/resource-poll overhead. Onlythreeplanned samples/profile; no speedSLO, productionpercentile or statistical superiority claim. RAMnumbers include the full owned server/projector/KV/overhead; VRAMis a separate sampled process allocation and may miss unsampled peaks. No CPU-style address-space cap is claimed for CUDA.

## Lifecycle, provenance and original data

Both actual cancellation probes received nonempty content, closed the client stream and observed the native slot return idle. Both ownedGPUservers loaded exact configured aliases/context32768 and retired with exit0/reaped/no guard failure. This boot began with no native model process after hostrestart; it ends in that same state. HistoricalCOREPID37256was not revived or claimed uninterrupted. Existing original15containerIDs/images/ports and currentboot identity match before/after; no Docker/service/config/default/data/Vault/database/collection changes or access were required.

Five local provenance checks/profile verify completeGGUFcacheSHA/revision, projectorSHA/revision/repository, metadata bytes, pinned runtimeGit/ninebinary hashes and upstreamlicensecopy. Four old UNRESTRICTEDmanifest paths point into a now-absent`upstream_reference`directory. Their already-existing flattened copies, including`UPSTREAM_LICENSE`, match the complete original hashes. The companion receipt discloses both paths; originalmanifest/model files are untouched. **Local declarations are not new remote authentication, reproducible-build attestation or legal clearance.**

Application728files still match the historical5674PASS/0FAIL/0ERROR/0SKIPsnapshot; no new full run is claimed for benchmark-only additions. Original176inputs and pending0/24listening labels unchanged. Of the older917protected-reference files,916are byte-identical; the one delta is the already-authorized MODEL_REGISTRYdocumentation appended before this D14session. That historical reference must not be described as all917unchanged after later registry edits. This report performs no new database/ACL/Vaultaudit and does not relabel older boot-specific audits as current.

## First controller failure and unmeasured continuation

First frozenf33289ecompleted allCOREfirst outcomes/cancel/retirement, then stopped before UNRESTRICTEDload. A finally-path masked the original pre-start exception; exact original cause remainsunconfirmed. Firstresult staysINCOMPLETE. Fix only exception preservation/preflight logging and freeze a never-attempted UNRESTRICTEDsuffix at72cb1ae. Exactpriorhash/12CORErows/13spentCOREdispatches/native-retirement/emptyUNRESTRICTEDdirectory prevent replay. The suffix makes only its13originalplanned requests; originalCORErawbytes are reused unchanged. Firstexecuted source/tests/log and subsequent mock-control failures are retained.

## Model decision and remaining acceptance

Keep the established COREbaseline and isolated optional UNRESTRICTEDprofile, existing32Kconfiguration and server-sideCORE-only tool permissions. This is continuity of the owner's agreed lineup, not adoption/replacement based on these scores. The missing D14weighted measurements, historical reconciliation and bounded lifecycle verification are now complete.

**D14cannot be labeled all-qualityPASS:** the retained text errors and newly observed format failures remain real. No original numeric minimum was located that would authorize a new posthoc acceptance threshold. Broader quality/format integration must be addressed with a separately assessed implementation and fresh frozen evaluation before relevant promotion; oldcases/firstscores cannot be regenerated into success. No new model, campaign or production integration is scheduled here. D70actualhearing/device/voice/model-license/product/release gates remain distinct and unchanged.


## Later authorized quality integration fix — 2026-10-26

[Structural decoding and the explicit functional gate](D14_STRUCTURED_QUALITY_GATE_RESULT.md) are now implemented under ADR133without changing these original scores. New correctedwireformat42/42perprofile and freshCOREstream3/3verifytheformatfix; exactfactualscore31/42CORE/30/42UNRESTRICTEDstillfails thenew42/42qualitycriterion. Do not relabel this earlier66.5/52comparison or its raw firstfailures as passing.


## Later semantic remediation — 2026-10-26

This document's original cohort/first scores remain unchanged. A separately preregistered selected bounded-reasoning/boolean-contract path now verifies freshCORE42/42andUNRESTRICTED42/42 with full lifecycle/provenance/context checks: [actual remediation, retained failures and cost](D14_SEMANTIC_REMEDIATION_RESULT.md).568scopedPASS/0SKIP, all730priorappfiles exact/current732; no newfull732/model/default/release claim.
