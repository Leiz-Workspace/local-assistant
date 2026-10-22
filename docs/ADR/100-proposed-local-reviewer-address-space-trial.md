# ADR 100 — Proposed16GiB virtual-address trial for the approved audio evaluator

**Purpose:** Present a bounded, concrete response to the original loader's actual mmap failure without silently exceeding the owner's approved ADR-098 limits.

**Date:** 2026-10-22. **Status: PROPOSED — NOT APPROVED OR EXECUTED.** ADR-098's original local evaluation is approved; its12GiB address-space trial failed. D70 remains open, D71 unstarted, ADR-097 rejected.

## Observed failure and distinction

The exact approved original Qwen2.5-Omni-3B16-artifact checkpoint and separate23382-entry SDK are provisioned and frozen. Genuine imports pass6.065s/415440KiB lifetime process RSS. The first native Thinker-only BF16/eager load exits1 after6.459s, no timeout, with `unable to mmap4999787448bytes` on the second original shard under `RLIMIT_AS=12884901888`. Original CORE identity and literal text recovery pass before/after. No control or common waveform has been reviewed.

`RLIMIT_AS` limits virtual address space, including file mappings; the error is not a measured minimum RAM/VRAM requirement. Original header inspection totals9,406,928,896Thinker tensor bytes,769,209,856Talker and1,796,205,184token2wav bytes. These are checkpoint tensor bytes, not live RSS or evidence that all components are executed. Full original shards are retained, no tensor extraction/rewriting or substitute checkpoint. The exact virtual peak and failure-time RSS were not collected by the first worker; do not invent them. [Layout evidence](../evidence/d70-local-reviewer-checkpoint-layout.json).

ADR-098 explicitly requires stopping if its cap is infeasible and forbids a silent increase. The trial stopped accordingly. No automatic second load or raised cap was executed.

## Proposed bounded change, only after owner approval

Change the owned reviewer's single static `prlimit` argument from `--as=12884901888` to **`--as=17179869184` (16GiB virtual address space)**. Keep CPU-only original Thinker/BF16/eager, original full artifacts/model roles/CORE loaded, affinity0,1/two threads, private tmpfs128MiB, qualification600s, review7200s/14400CPU and no network/credentials/GPU. There is no new download, new model selection, production configuration or data migration.

Before this separately named load-only trial, require sampled host `MemAvailable` at least18GiB alongside the unchanged CORE. This is a preflight headroom condition, not reserved memory or a new measured model RAM requirement. If unavailable, stop before launch. Add actual worker RSS/virtual-size snapshots before/after loading and final resource usage even on failure; distinguish point samples from lifetime peak RSS and virtual peak. Freeze new source/tests/protocol before executing. Keep all first sources/results/freezes, no rewrite of12GiB outcome.

Only if native load and missing/unexpected-parameter/device accounting succeed may the unchanged nine frozen controls run. Only if every first control passes may the24original benchmark outputs be reviewed once. No prompt/label/audio tuning, synthesis retry, language-certification/MOS claim or D70 closure from load/JSON success. A failed16GiB trial stops; no further automatic cap increase, CORE unload, GPU substitution or tensor/loader patch.

## Priority, dependencies, effort and risk

P1, existing D70 capability blocker; one bounded load/qualification milestone. Depends on owner approving this precise cap change, unchanged pinned bytes/runtime/control protocol, host headroom, tests and CORE recovery.16GiB may still be insufficient and no successful Vietnamese judgement is guaranteed. Risks include page-fault/host-memory pressure, confusing mapped bytes with physical allocation and mistaking a larger cap for proof of capability. Preserve first failures and all measured limits; failure is not permission to waive AC.

Rollback joins only the owned evaluator and retains artifacts/evidence. Production roles/services/index/source/audio stay unchanged. Rejection retains the stopped12GiB trial and D70 open; a functioning audio API/reviewer remains another possible path, not an assumed available dependency.
