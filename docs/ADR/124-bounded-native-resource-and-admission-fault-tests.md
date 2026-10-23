# ADR 124 — Bounded native resource and admission fault tests

**Purpose:** Define D85 reproducible fault/load evidence without exhausting host memory/storage or changing production caps.

**Date:** 2026-10-23. **Status:** Accepted for owned fixtures/tests, not production capacity certification.

## Decision

Use fixed stdlib workers in offline read-only bubblewrap namespaces, no project/home/credentials/network/GPU mounts. Bound address space256MiB/CPU2seconds/32FD/file1MiB/wall10seconds and private scratch tmpfs64KiB. Deliberately request512MiB so the process receives MemoryError under RLIMIT_AS, then verify a1MiBallocation succeeds. Fill only the private64KiBtmpfs to actual ENOSPC, remove the owned file and recreate a small file. Parent joins the child and retains exact first output/source hashes. Do not trigger the host OOM killer, fill host disks, unload CORE or raise any existing cap. These are real process/private-filesystem faults, not proof of a model surviving host OOM.

Run100simultaneous actual disposable native workspace reads through D79. Assert one active admission, seven busy denials and92attempt-limit denials, no queue; await cleanup, retain unchanged source receipts and require an explicit fresh run before another read. This documents bounded admission rather than claiming100successful requests/second or global HTTP/model throughput. Combine with D78's checkpoint-publication failure/uncertain-write and D77/MCP cancellation tests for application recovery policy.

## Impact and rollback

Existing D85/P1 depends on accepted bwrap/workspace/guards/checkpoints. Effort one fixture/measurement milestone; risks host pressure, runaway child, misleading rate claims and duplicated side effects. Fixed tiny private resources, read-only actions, parent timeout/reaping, source snapshots and exact admission counts constrain them. No new model/runtime/dependency/infrastructure setting or production load. Close/join owned fixture operations; preserve first failure logs and application ambiguity rather than auto-retrying uncertain writes. Larger workload/SLO/cgroup-host-OOM experiments require separately scoped capacity work.
