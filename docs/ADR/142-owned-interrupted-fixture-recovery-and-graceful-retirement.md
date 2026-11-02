# ADR 142 - Interrupted fixture recovery and graceful regression retirement

Purpose: correct the operator's interrupted-test cleanup failure without changing production quota rules, deleting foreign data or relabeling an unsuccessful full run.

Date: 2026-11-02. Status: Accepted as necessary recovery within the owner's D46/D60 testing request.

## Actual failure and correction

The first final 745-source suite completed **5836 PASS / 1 FAIL / 0 ERROR / 0 SKIP**, 2122.54 seconds. The pinned reranker comparison and original resource guards passed. The remaining global-bytes test correctly refused every allocation because142bytes from the earlier interrupted intermediate run remained charged against its40-byte synthetic capacity.

The operator's earlier claim that collection meant no test had executed was wrong. Pytest's first test had already uploaded/indexed its first fixture before producing a completed output line. SIGINT to the supervisor caused the old retirement helper to send SIGTERM to the whole full-runner group, bypassing fixture teardown. Original logs, interrupted metadata, the later failed full and dirty read-only snapshot remain preserved. No source-policy bug or successful final audit is inferred.

## Ownership and bounded recovery

The remaining file's exact UUID, owner,142-byte content SHA and storage namespace match the still-present private principal/root artifacts from `pytest-20/test_actual_owner_delegated_ai0`, the first frozen D27 review document and the intermediate run's creation/stop interval. The original zero-usage owner row dates from October18 and is foreign to this recovery; preserve it exactly. Never reset global counters or delete rows by age/name alone.

Require independent principal/root/namespace/content/UUID/time validation, quiet runtime and a retained pre-recovery snapshot. Only after these checks, use the existing inode-locked blob purge, exact metadata-owned removable Qdrant probe and scoped fixture transaction to remove that one interrupted fixture and subtract only its actual142bytes/one-file charge. Refuse extra files, changed hashes, foreign probe metadata or inconsistent counters. Never access another owner, production collection, schema, Vault policy or original model. Keep credential files outside delivery.

## Retirement and verification

Replace only the new private full-run supervisor's cancellation path: signal its exact verified descendant pytest PID with SIGINT first, allow finite fixture teardown while the existing redacting wrapper drains output, then join the wrapper. A bounded TERM/KILL fallback still protects resources and records incomplete cleanup. Do not signal an unrelated/reused PID. Test both ownership denial/fallback and actual tiny pytest fixture teardown without services/models.

Compare recovery against the original pre-task fingerprints/security/quota, retaining timestamp-only drift rather than restoring it. Start a new full only after clean preflight. Keep the earlier5836/1FAIL result and the original CE00511/12 result unchanged. The final source remains745files; no model-quality regeneration or current provider retry is required. Require a fresh complete zero-failure full, joined native runtime and read-only post-audit before closure.
