# ADR 150 - Original worker passive inherited verification environment

Purpose: verify the existing original reranker under a declared process-local scheduling environment without promoting a failed optimization candidate or changing original acceptance limits.

Date: 2026-11-02. Status: Accepted for one original-test probe and, only if it passes, one current-source full.

## Retained evidence and scope

Original active-wait scheduling exhausted CPU480after two rounds even when CPU3 was selected before exec. ADR149fixed-prefix caching failed its three-query numeric/rank micro gate (max score difference0.03632059693336487), dispatched0full runs and is rejected. All prior diagnostics that missed the additional450CPU optimization-promotion criterion remain rejected. None becomes a model/profile/runtime/default recommendation through this decision.

P1 dependency is those joined first failures and unchanged original graph. Effort one private argument-exact launch environment plus focused and full verification. Risks remain narrow CPU headroom, scheduling variance and OpenMP implementation behavior. GNU libgomp documents passive waiting and zero spin count; no causal speedup or stability is assumed before measurement. The installed library and original SDK stay pinned.

## Decision

Keep the original public runtime, worker, profile, fingerprint, two configured threads, batch4, weights, dtype, tokenizer, SDK, uncached algorithm, full corpus/rounds and every original assertion byte-identical. The private uv delegate changes only its own environment for the exact original absolute worker command: `OMP_WAIT_POLICY=PASSIVE`, `GOMP_SPINCOUNT=0`, then selects CPU3 before exec/thread creation. All other uv commands/environment receive no adjustment. Do not change a shared service, host governor, another process or an agreed model choice.

First run exactly the existing original live comparison test, once, offline and without CORE or database credentials. Require onePASS/zeroFAIL/ERROR/SKIP, all original resource assertions, exact application bytes and joined original runtime. Keep CPU480/481seconds, AS8GiB, RSS4096MiB, query60seconds and wall600seconds unchanged. The450CPU criterion belongs to eligibility for a new optimization variant; this probe/full does not claim or grant such eligibility. A probe failure remains failure and prevents full dispatch.

Only if that original-test probe passes, freeze the existing745-source graph and one full using the same private environment. Require fresh DB/security/runtime/authenticated-Qdrant preflight, complete unfiltered suite with zero failures/errors/skips, graceful fixture teardown and joined CORE retirement, then independent read-only preservation. No source mutation, inferred PASS from an old comparison, quality-score rewrite or repeated coding/web generation. This is current-source software verification in an explicitly declared environment, not general performance qualification or model adoption.

## Rollback

The private environment and affinity disappear with the owned invocation. Dropping the delegate restores ordinary launch behavior. No public source/config migration, provider/model change, production activation or release is authorized.

Primary documentation: [GNU OpenMP wait policy](https://gcc.gnu.org/onlinedocs/libgomp/OMP_005fWAIT_005fPOLICY.html), [GNU spin count](https://gcc.gnu.org/onlinedocs/libgomp/GOMP_005fSPINCOUNT.html).
