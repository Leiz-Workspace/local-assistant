# ADR 148 - Inherited original reranker scheduling for final full

Purpose: verify D46/D60 source changes with the original reranker by selecting its permitted CPU before thread creation instead of changing an already running worker.

Date: 2026-11-02. Status: Accepted for one original-runtime current full; no production scheduling or model adoption.

## Evidence and priority

The clean745-source full completed5836PASS/1FAIL/0ERROR/0SKIP: quota passed after the exact owned interruption recovery, but the late-affinity reranker exhausted its original CPU guard. Original business/security/runtime preservation was independently verified. The prior inherited single-CPU diagnostic passed the unchanged original live test in471.83seconds. These observations do not prove repeatability or a particular library fault.

P1 dependency is the preserved first diagnostics and graceful fixture retirement. Effort one private argument-exact uv delegate, authored isolation tests and one fresh unfiltered full. Risks are narrow CPU headroom, host scheduling variance, unintended command matching and interruption residue. Do not repeat native coding generations, web searches or report exports.

## Decision

Use a private PATH delegate only in the owned full process tree. It delegates all arguments directly to the installed uv. Only the exact original absolute worker command `run --offline --frozen --script <original qwen_reranker_worker.py>` selects logical CPU3 before exec; fail closed if CPU3 is unavailable or the mask is not applied. It preserves PID, original parent supervision, arguments and every worker/profile/source byte. Other uv commands receive no affinity change. No polling or late thread mutation remains.

Keep original two Torch threads, batch4, dtype, tokenizer, weights, SDK, corpus and every assertion. CPU480/481seconds, AS8GiB, RSS4096MiB, query60seconds and wall600seconds remain unchanged. Do not promote a diagnostic variant that failed its additional450CPU/parity gate. ADR147 is a separate experiment; any result is retained without using it in this original-runtime full.

Freeze the delegate, supervisor, tests, execution inputs and complete current745-source inventory before launch. Require an independent original DB/security/runtime and authenticated empty-Qdrant preflight, zero failures/errors/skips, graceful fixture teardown and joined CORE retirement, then a new read-only preservation audit. A failure stays a failure; absence of a completed-test line never proves absence of fixture execution.

## Rollback

The private PATH exists only in this owned invocation. Removing the invocation restores ordinary launching; no shared service, host policy, public source/config, default, provider, model or database change is involved.
