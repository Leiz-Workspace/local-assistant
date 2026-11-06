# ADR 151 - Owned CPU partition for CORE-resident original probe

Purpose: test the existing original reranker with CORE genuinely resident while preventing this operator's newly created CORE/monitor/test children from sharing its physical CPU.

Date: 2026-11-02. Status: Accepted for one CORE-resident original-test probe and, only after actual PASS, one separately frozen full.

## Evidence, priority and risk

ADR150solo original test passed1/1in477.05seconds, with exact1080retained scores/ranks and identical original contract/fingerprint. The subsequent actual CORE-resident full retained5836PASS/1FAIL/0ERROR/0SKIP in2160.25seconds: CPU exit152after2rounds. Declared passive waiting/CPU3/original caps were actually observed. CORE exited0/reaped, original native0/15containers and read-only original business/security/schema/vector state preserved, quota timestamp-only drift disclosed.

A read-only two-second observation found the owned operator, pytest and CORE allowed on all16logical CPUs, including CPU3and its SMT sibling11. It does not establish the failure's cause and omits short-lived children. P1 dependency is the retained solo PASS/full FAIL contrast and actual CPU topology. Effort one narrow owned-thread partition/delegate, authored safety controls and conditional probe/full. Risks include remaining host contention, reduced capacity for other owned tests, topology drift and mistaken causal attribution. Do not change host policy or another user's/shared-service process.

## Decision and unchanged gates

Before creating CORE, restrict only the calling operator thread to its original mask minusCPU3andSMT11, validating actual topology `3,11`, sufficient remaining CPUs and applied mask. Subsequently created CORE/monitor/test children inherit that reduced mask. Existing unrelated processes and host policy remain untouched. A distinct exact-command uv delegate restores only the original reranker worker to predeclared onlineCPU3 and sets the already declared passive/zero-spin variables before exec. All other uv commands keep their inherited mask/environment. The kernel still enforces its existing cgroup CPU bounds; this creates no host-exclusive reservation.

Keep CORE loaded with the exact original command, model, context, weights and all original live sampled resource/overlap guards at unchanged cadence. Keep the original reranker graph/profile/fingerprint/two threads/batch4/uncached algorithm/tokenizer/dtype/SDK/corpus/three rounds and every original assertion. CPU480/481seconds, AS8GiB, RSS4096MiB, query60seconds and wall600seconds stay fixed. No new optimization variant is promoted; previous450CPU/parity failures remain rejected.

First perform fresh original-state preflight, load the exact owned CORE, then run exactly the existing original live comparison once with explicit actual-test flag and no database credentials in its pytest environment. Retain current comparison only after actual PASS and fresh timestamp. Require1PASS/zeroFAIL/ERROR/SKIP, actual applied partition, guardNone, COREexit0/reaped, original runtime restored and source bytes unchanged. Any failure prevents the conditional full; no automatic retry.

Only actual probe PASS permits one new complete current-source full under the identical environment, separately frozen with fresh preflight and strict zero-failure/error/skip plus post-join read-only preservation. No coding/web generation retry, model/default/provider/production adoption, source alteration or relaxed criterion. CPU isolation remains a hypothesis until measured, and any PASS is scoped to its actual environment.

## Rollback

All effects belong to the short-lived owned operator and descendants and disappear on exit. Remove the private invocation to restore ordinary launching. No host governor, shared service, model configuration, schema, ACL, stored vectors or release changes.
