# ADR 140 - Owned reranker CPU scheduling for current verification

Purpose: complete current software verification without rewriting historical execution sources or increasing model resource guards.

Date: 2026-11-02. Status: Accepted for the owner's current D46/D60 verification; no product/runtime adoption.

## Evidence and assessment

The first 742-file full run and a focused CORE-absent run both killed the unchanged two-thread reranker at CPU exit152 after two rounds. A separately recorded two-physical-core affinity diagnostic failed identically. These failures remain retained. The subsequent single-physical-CPU scheduling diagnostic completed the exact existing live test: **1 PASS, 471.83 seconds**, with the original two configured threads, all three rounds and all existing resource/quality assertions. Sources and profile remained byte-identical. This supports a bounded scheduling workaround, not proof of a specific OpenMP cause or broad performance stability. CPU headroom remains narrow.

P1 for the current full; dependency successful original-guard diagnostic and unchanged model/source graph. Effort one private ownership-checked scheduling helper with tests. Risks include PID reuse, accidentally touching an unrelated process, kernel scheduling variation and recurrence near the CPU cap.

## Decision and limits

Keep frozen reranker source/manifests, model, dtype, batch, two threads, corpus, scores and every acceptance assertion unchanged. Keep CPU soft/hard480/481seconds, address-space8GiB, RSS4096MiB, query60seconds and worker wall600seconds. Do not change host governor, CPU quotas, shared services or another user's process.

During one current full, the private owner polls only descendants of its exact root PID/start identity. Only the exact existing reranker worker command is eligible. Pin eligible workers and their current threads to logical CPU3, record PID/start/original/selected masks, and retain terminal observations. Decline absent CPU3, changed root identity, unrelated ancestry, cycles and different commands. No alternate model, shortened rounds, cached forward scores or skipped tests. The full remains FAIL if an original gate fails.

## Verification and rollback

Authored ownership controls reject unrelated/reused/cyclic roots and wrong workers, and refuse an unavailable target CPU. Require final current-source full with zero failures/errors/skips plus unchanged sources, joined owned CORE, original native/container inventory and read-only data/security checks. All scheduling effects disappear when the owned workers exit; dropping the private helper restores ordinary scheduling. No production scheduler or model-selection change is authorized.
