# D46/D60 resource verification record

Purpose: preserve unsuccessful full-regression and optimization observations separately from the verified coding/web functional evidence.

Date: 2026-11-02. The unchanged reranker is an integration-test dependency. These experiments never authorize a model, SDK, provider, production or default replacement.

## Preserved software failures

| Execution | Actual outcome | Disposition |
|---|---|---|
| First742-source full | 5810PASS/1FAIL/0ERROR/0SKIP | Original reranker CPU guard terminated the worker |
| Intermediate745-source full | Interrupted after collection; first fixture had started | No software acceptance; exact142-byte owned residue recovered under ADR142 |
| First final745-source full | 5836PASS/1FAIL/0ERROR/0SKIP | Reranker passed; quota rejected the interruption residue |
| Clean745-source full | 5836PASS/1FAIL/0ERROR/0SKIP,2124.37seconds | Quota passed; late-pinned reranker exhausted original CPU guard. Read-only original-state preservation independently verified |
| Inherited-original745-source full | 5836PASS/1FAIL/0ERROR/0SKIP,2147.54seconds | Original worker inherited CPU3 but exhausted CPU480after2rounds. Joined CORE and read-only original DB/security/runtime/Qdrant preservation verified |

A collection line is not proof that fixture execution has not started. The correction, exact owner/namespace/content/time recovery and graceful descendant-pytest retirement are retained in [ADR142](ADR/142-owned-interrupted-fixture-recovery-and-graceful-retirement.md). Original business/security/runtime match with only quota updated_at drift; no original counter/timestamp is restored to manufacture equality.

## Distinct bounded diagnostics

All use the existing pinned model/weights and offline SDK. Original CPU480/481seconds, AS8GiB, RSS4096MiB, query60seconds and worker wall600seconds stay fixed. Candidate promotion additionally requires total child CPU at most450seconds, all1080score differences at most1e-6 and identical rankings. No criterion was relaxed after observation.

| Diagnostic | Actual outcome | Promotion |
|---|---|---|
| ADR143 passive waiting, original2threads/batch4 | 473.229182child CPU seconds; original resource gates passed | Rejected:450CPU criterion |
| ADR144 passive waiting, physical cores1and3 | 482.272573child CPU seconds; original resource gates passed | Rejected:450CPU criterion |
| ADR145 one thread/batch4 | 465.299037child CPU seconds; all1080scores/ranks exact | Rejected:450CPU criterion |
| ADR146 batch10/original positions | Three-query micro max delta0.00016407319344580173 and changed rankings | Rejected;0full dispatches |
| ADR147 original2threads/batch4, selected-class projection | Micro and full1080scores/ranks exact;473.443637child CPU seconds | Rejected:450CPU criterion |
| ADR149 fixed-system-prefix KV reuse | Micro max score delta0.03632059693336487 and changed rankings | Rejected;0full dispatches |

ADR147 also retains two zero-worker prelaunch invocation/binding errors and a corrected independently frozen binding. Its full ran exactly once after the micro gate; no failed score was regenerated. The original full vocabulary weights stayed resident for actual reference controls. No selected-head variant was promoted despite exact scores.

## Original-runtime verification policy

[ADR148](ADR/148-inherited-original-reranker-scheduling-for-final-full.md) uses only the original reranker graph. A private argument-exact uv delegate selects CPU3 before the original worker exec/thread creation and forwards every other command unchanged. It replaces late scheduling within the owned full invocation, with original limits and assertions. The earlier inherited single-CPU diagnostic passed in471.83seconds; this remains narrow headroom, not general stability evidence.

The new full and post-run read-only audit must finish before current-source software acceptance. The D46exact-first-output12/12 and D60observed-source/native/all-page QA are separate functional gates. D70listening0/24, product/device/rights and release approval remain independent.


2026-11-02 original-environment continuation: ADR148full FAILED as recorded above; do not treat pre-exec scheduling as an established correction. [ADR150](ADR/150-original-worker-passive-inherited-verification-environment.md) freezes one original live-test probe with exact-command process-local passive waiting and CPU3. All original480/481CPU/8GiBAS/4096MiBRSS/60query/600wall assertions remain. Failed optimization candidates remain rejected under their additional450CPU/parity criteria; this separate original-source probe claims no variant-promotion eligibility. Only actual probe PASS permits one same-environment full, with fresh preflight and post-join preservation checks.


ADR150original-source probe completed **1PASS/0FAIL/0ERROR/0SKIP in477.05seconds**. All three original rounds/resource assertions passed; total dedicated probe child CPU477.828508seconds includes pytest/uv overhead and is not a worker-only CPU measurement or450CPUoptimization eligibility. Original native0/same15containers restored,745application files unchanged. The conditional same-environment current full is now running against a separately frozen196-input record; no current full acceptance yet.


The ADR150CORE-resident full finished **5836PASS/1FAIL/0ERROR/0SKIP in2160.25seconds**, again CPU exit152after2rounds. Its actual passive/CPU3 snapshot is retained; all original data/security/runtime and current authenticated empty-Qdrant inventory were independently preserved. The solo PASS does not establish loaded-run reliability.

[ADR151](ADR/151-owned-cpu-partition-for-core-resident-original-probe.md) separates only the calling operator thread and its subsequent CORE/monitor/test children from CPU3andSMT11, leaving unrelated processes/host policy untouched. Actual simultaneous snapshot confirms CORE threads avoid the pair and original reranker threads useCPU3. One genuine CORE-resident original comparison **PASS1/1/0FAIL/ERROR/SKIP in473.40seconds**, native COREexit0/reaped/guardNone and original runtime restored. This is one bounded environment observation, not a proven cause or broad performance claim. The separately frozen235-input same745-source full is now running; all original caps/assertions and failed-variant promotion rejections remain unchanged.


Inference-count scope correction: zero new requests refers to CE005exact-output revalidation only. Unfiltered full runs include existing actual CORE coding/traffic tests, so no global zero-inference claim is made. Their repeated fixture observations do not replace first-study scores or become a fresh independent quality campaign; see [accounting clarification](D46_D60_REMEDIATION_RESULT.md#inference-accounting-clarification--2026-11-02).
