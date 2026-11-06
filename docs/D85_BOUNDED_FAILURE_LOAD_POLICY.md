# D85 — Bounded native faults and admission policy

**Purpose:** Report reproducible small-scope memory/disk/load failures and safe recovery limits.

**Status:** Local bounded fault controls VERIFIED. [ADR124](ADR/124-bounded-native-resource-and-admission-fault-tests.md).

Actual fixed stdlib worker in offline read-only bubblewrap, no home/project/credential/network/GPU mounts. Native cap256MiB address space/2CPU seconds/32FD/1MiBfile/10swall; separate private64KiBtmpfs. A512MiBallocation receives MemoryError, followed by successful1MiB allocation; worker0.0393s/RSS15384KiB. Filling only private scratch receives actual ENOSPC, then deletion/recreation succeeds;0.0390s/RSS14524KiB. Both exit0, joined/reaped, full worker hashes/output retained. RSS is whole tiny worker RAM, not model RAM/VRAM. No host OOM killer, host disk fill or cap increase.

Actual100simultaneous native reads through D79: **1accepted,7busy,92attempt-limit denials**,0.0143seconds for this fixture cohort. This is admission behavior, not100successfulrequests/sec, HTTP/model throughput or an SLO. No queue builds, all work/pins join, original fixture bytes/hash receipts unchanged. A fresh explicit run reads successfully after cleanup; exhausted old budgets are not refunded.

**4new/75related PASS1.82s/0FAIL/0SKIP/Ruff PASS** combines native failures/load with existing planner crash/budget/metadata-publication failure/uncertain-write, guard and MCP cleanup controls. [Source/native/log receipts](evidence/d85-bounded-fault-recovery-verification.json). Same original CORE PID/start/command retained.

Recovery policy: reject concurrent/over-budget work; do not enlarge caps or retry automatically. Release/join owned read work before a fresh explicit run. Preserve in-flight write ambiguity if publication fails after a native action; reconcile original authoritative receipts before another proposal. Do not relabel metadata cleanup as rollback of an already committed action. A low-cap MemoryError is not proof of surviving host/model OOM; cgroup/SLO/global capacity remains separately scoped deployment work.

No production runtime/config/model/infrastructure change. D86 UI/release candidate review is next; manual/product/model/license/format gates stay open.
