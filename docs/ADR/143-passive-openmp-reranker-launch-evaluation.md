# ADR 143 - Passive OpenMP reranker launch evaluation

Purpose: evaluate a reproducible CPU-efficiency correction while preserving every failed full, historical execution graph, model and resource guard.

Date: 2026-11-02. Status: Accepted for one isolated diagnostic after the current full retires; no production/model adoption.

## Evidence and hypothesis

Single-CPU scheduling completed one diagnostic and the earlier full's reranker test, but the latest clean full registered another reranker failure. Quota passed. Read the terminal failure before attributing its cause; the latest-comparison file still belongs to the earlier successful run and must not be reused as current success. Affinity is not established as a stable remedy.

The existing pinned CPU Torch SDK contains `torch/lib/libgomp.so.1`. GNU documents that [OMP_WAIT_POLICY=PASSIVE](https://gcc.gnu.org/onlinedocs/libgomp/OMP_005fWAIT_005fPOLICY.html) avoids active waiting and [GOMP_SPINCOUNT=0](https://gcc.gnu.org/onlinedocs/libgomp/GOMP_005fSPINCOUNT.html) specifies zero busy-wait spins. Whether that materially reduces this worker's CPU charge is a hypothesis requiring measurement.

P1 for final current-software verification; dependency terminal current failure, joined original runtime and exact pinned legacy graph. Effort one separately frozen launcher prototype, ownership/protocol controls and one diagnostic. Risks include hidden execution drift, slower wall latency, noisy CPU measurements and mistaking a launcher variant for model adoption.

## Bounded decision

Copy the original bounded launch/join method into a separate prototype; add only the two explicit environment entries. An AST-equivalence control must remove those entries and recover the entire original method. Preserve the legacy manifest/source paths and all original scripts unchanged. Keep weights, SDK/lock, dtype, batch4, two Torch threads, interop1, all36queries/all3rounds/allforward calls, reference-logit parity and every existing quality/resource assertion. No score cache, shortened input, model selection or download.

After current workers retire, freeze the prototype/test/driver, original execution graph, exact request and local library hash. Run one diagnostic on normal inherited CPU affinity, CPU-only/offline, with original CPU480/481seconds, address space8GiB, RSS4096MiB, query60seconds and worker wall600seconds. Retain the first complete output or failure. Measure dedicated child user+system CPU and wall separately. Eligibility for a stable follow-up requires all original gates plus total child CPU at most450seconds; this additional headroom criterion does not relax an original limit. No automatic retries.

Only a successful diagnostic may lead to an explicitly named public launch variant and a new versioned source-binding record. Keep the old launcher and manifests byte-identical; update the current long software integration test to identify the new policy without changing inputs or assertions. Then run a fresh current-source full and read-only audit. Existing CE005 and D60 observations need no new neural generation or provider request.

## Rollback

Omit the new variant and retain the original execution path/results. A rejected diagnostic does not authorize higher caps, governor changes, another model, skipped tests or software PASS.
