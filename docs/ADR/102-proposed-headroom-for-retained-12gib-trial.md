# ADR 102 — Proposed host headroom for the retained12GiB load trial

**Purpose:** Separate the unchanged owner-approved12GiB process address-space cap from the18GiB sampled host guard inherited from the rejected16GiB proposal, and present an explicit bounded resource decision.

**Date:** 2026-10-22. **Status: APPROVED FOR ONE LOAD/INTEGRITY TRIAL.** Explicit owner reply: **“Duyệt headroom 14 GiB, giữ cap 12 GiB”**. The14GiB host guard is approved; the process address-space cap stays12GiB. ADR-101 authorizes imports/load/integrity only. This proposal does not approve itself from a generic continuation, resume audio qualification/review or revise D70 acceptance. ADR-100's16GiB cap remains rejected.

## Evidence and reason

ADR-100 introduced sampled host `MemAvailable >=18GiB` alongside its proposed16GiB virtual-address cap. The cap was subsequently restored to12GiB while the host guard stayed18GiB. The first pread attempt at commit28cedf9 stopped before launching an original-weight worker:18,946,437,120bytes available versus19,327,352,832bytes required. No original-weight12GiB pread fit or peak RAM was measured. The inherited threshold is a policy guard, not a measured model requirement.

Current readonly inspection still finds less than18GiB available and almost exhausted swap. Memory pressure counters currently report0.00 for their10/60/300second windows; those observations are not a capacity guarantee. The largest resident process is the preserved CORE; browser/editor/server processes are not owned by this evaluator. Do not close them, unload CORE, change swap or reclaim global caches to manufacture headroom.

## Approved exact change

Retain `ADDRESS_SPACE_BYTES = 12 * 1024**3` and change only the local evaluator host guard to:

```python
MIN_AVAILABLE_BYTES = 14 * 1024**3
```

This carries forward the former twoGiB difference between sampled host availability and process address-space cap. It **reduces the host preflight threshold**, so it is a different resource decision even though the process cap stays12GiB. The explicit answer above authorizes this change; do not infer broader resource or audio permission. Test the exact14GiB boundary, rejection immediately below it, and unchanged12GiB sandbox cap. No CLI bypass or alternate model path.

Check host availability before artifact verification and again immediately before one separately named original-weight load-only worker. Preserve CPU2/inter-op1/affinity0,1, no network/GPU/credentials, original readonly model/SDK/source/samples,128MiB tmpfs,600second wall/1200second CPU and complete first-result retention. Stop on preflight/cap/native-load/fidelity failure. No automatic cap increase, threshold decrease, retry, CORE unload or download. All original first failures, weights, SDKs, audio and pending reviews remain intact.

## Risks, limits and rollback

`RLIMIT_AS` bounds process virtual address space, not reserved host RAM. Sampled `MemAvailable` is not a reservation; other applications can allocate memory concurrently. Kernel, tmpfs and parent-process overhead are outside the child's address-space accounting, and nearly exhausted swap limits fallback. A twoGiB difference is a policy margin, not proof against global pressure or a certified co-residency budget. Either14GiB or18GiB may still precede a failing load. Keep observed resources distinct from the cap and refuse to claim12GiB fit until actual loading, original-byte fidelity and CORE recovery pass.

Rollback restores the18GiB guard, joins only the owned worker and keeps every result. No model/default/data/schema/service/Vault/Docker change or migration is part of this proposal.

## Priority and acceptance boundary

**P2, AUDIO-EVAL-LOAD-12G-001 continuation; one bounded guard/test/load milestone.** Dependencies: explicit headroom decision, retained12GiB cap, unchanged artifacts/runtime, existing221passing TTS controls and fresh source/protocol freeze. This is separate from **P1 qualified auditory review**: the existing evaluator's silence/noise/clipping and strictJSON failures remain unresolved. Loading success cannot authorize control reruns, common24output review, model selection, D70 closure or D71 advance. Any further audio protocol requires its own justified scope and retained first failures.

Actual first result is retained separately in [the14GiB-headroom load evidence](../evidence/d70-pread-14g-headroom-load.json). A successful guard or tiny-fixture test does not establish original-weight fit.
