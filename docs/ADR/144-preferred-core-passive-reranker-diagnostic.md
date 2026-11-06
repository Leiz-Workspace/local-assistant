# ADR 144 - Preferred-core passive reranker diagnostic

Purpose: test a distinct owned scheduling hypothesis after the first passive diagnostic missed its preregistered headroom requirement.

Date: 2026-11-02. Status: Accepted for one separately frozen diagnostic; no default/model adoption.

The normal-affinity passive launch completed all36queries/3rounds and every original resource assertion, but total child CPU473.229seconds exceeded the additional450-second eligibility criterion. Wall246.874seconds and unchanged runtime are retained. Do not relabel this result eligible or lower450 after observing it.

P1, dependency completed first diagnostic and original clean baseline. Effort one driver variant and a finite diagnostic. Risk remains host-specific scheduling, narrow headroom, noise and attributing causal improvement from one run. Prior read-only hardware evidence identifies physical cores1and3 as distinct cores with equal highest CPPC preference196; no governor setting is changed.

Run exactly the same passive prototype, original model/SDK/profile/input and all original guards, with the dedicated driver/uv/worker inheriting `taskset -c 1,3` before any Torch/OpenMP initialization. Refuse another inherited mask and retain actual per-core preference/governor metadata. Only the new owned process tree is constrained; no shared process, host quota, power policy, model thread count or score is changed. This avoids the earlier late-pinning race without claiming it fully explains the prior failure.

Freeze the new driver, unchanged prototype, original graph/library/request and first diagnostic result before the one attempt. Keep the same original CPU480/481seconds/AS8GiB/RSS4096MiB/query60seconds/wall600seconds and additional total-child-CPU450-second ceiling. No automatic retries, shorter rounds or cached forward results. Only a result meeting both original gates and unchanged450 criterion may justify a separately versioned public evaluation launcher. Preserve every first result and require final current-source full/data/runtime verification before D46/D60 software closure.
