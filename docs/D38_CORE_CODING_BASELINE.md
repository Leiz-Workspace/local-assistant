# D38 existing CORE coding baseline

**Purpose:** Record case-wise measured repair outcomes and evaluation isolation before application approval/edit/command features.

**Status:** Evaluation gate PASS: all frozen cases actually attempted and measured, with **4 successful repairs and2 failed repairs** retained. This is not an agent MVP gate or a claim that all coding tasks pass. [ADR-056](ADR/056-isolated-core-coding-baseline.md), [acceptance](evidence/d38-baseline-acceptance.json), [case freeze](evidence/d38-coding-case-freeze.json), [source freeze](evidence/d38-baseline-source-freeze.json).

The unused evaluation modules create only new private Git/source fixtures under a generated artifact directory. Trusted fixed Git init/checkpoint/diff commands clear system/global config, disable hooks/signing/fsmonitor/external diff/text conversion and never accept model commands or paths. Actual D35 search/read supplies bounded source context. Existing `qwen3.5-9b-core`/fast, temperature0/max1024 proposes strict JSON containing the complete replacement code only. The host AST-checks descriptions and the solve entry; it never imports/executes candidate source. Proposals can only replace the fixed owned fixture solve.py. No production endpoint, real repository edit, model replacement/download or general command permission is added.

Actual function execution uses bubblewrap with only readonly trusted `/usr` runtime and one worker mount, UID/GID65534, cleared environment, fresh network/PID/user/IPC namespaces, no capabilities, no host home/project/Vault/socket mounts and no writable filesystem. Hard limits:512MiB address space, CPU2s soft/3s hard, file-size0, core0,32 FDs,16 processes; supervised wall8s, request32768 bytes, stdout65536 and stderr4096 bytes. Source8192 bytes, at most16 input calls. Nonblocking bounded pipes and cooperative stop terminate/join the process/namespace before return. These are resource policy caps, not measured RAM/VRAM performance. Uninterruptible kernel work is not claimed to be preemptible.

Trusted expected outputs remain in the host parent, outside worker inputs. Compare exact JSON values/types; printed TESTS_PASSED/exit0 cannot certify results. Candidate code may introspect its isolated worker or hardcode finite inputs, so this is finite authored functional evidence rather than an honest-execution proof or exhaustive sandbox security claim. No weaker fallback is used. Application approval, generalized patch/git rollback/command execution and E2E issue workflows remain D39–D46.

## Actual first unchanged-CORE result

Six tasks and28 oracles were frozen before inference. All original task implementations fail at least one oracle; their original total is10/28 passing oracles and0/6 completely correct tasks. One actual model invocation per task, no retry/score selection:

| Task | Original oracles | Proposed repair | Observed result |
|---|---:|---:|---|
| floor_division |3/5 |5/5 |PASS |
| unique_order |2/4 |4/4 |PASS |
| unicode_palindrome |1/5 |Not executed |FAIL: generated JSON missing its closing object delimiter; strict proposal rejection |
| word_counts |1/4 |4/4 |PASS |
| window_sums |1/5 |5/5 |PASS |
| inclusive_clamp |2/5 |2/5 |FAIL: generated code retained the incorrect clamp expression |

**4/6 repaired tasks.20/23 executed post-proposal oracles PASS,3 FAIL;5 palindrome oracles were not executed because its invalid proposal was blocked.** These are model evaluation outcomes, distinct from pytest SKIP. Raw generated code, native observations, diff/checkpoint and measured model-call seconds are retained in [observations](evidence/d38-core-observations.json). Model calls span approximately0.84–2.42s on these six small cases; this is descriptive, not a throughput/SLO/RAM/VRAM comparison. Synthetic same-agent authored tasks are not independent human review or realistic coding generalization. No specialist evaluated/adopted; original agreed lineup remains unchanged.

The actual live measurement test passes when all frozen cases are attempted under the valid harness and outcomes/failures are retained; it does not assert six successful repairs. [Invocation](evidence/d38-core-invocation.json):1 pytest PASS/9.08s,0 SKIP,exit0. Its original report was preserved; final related regression deliberately did not repeat this baseline for a better score.

## Harness and related verification

Final **589 related PASS/16.84s,0 SKIP,exit0**, plus the separate actual live1 PASS; not one590-case invocation.51 new application tests total, including17 native sandbox and33 contract/Git/controlled-trial cases plus1 actual CORE evaluation. Final related suite also covers477 prior workspace/diagnosis/explanation/auth cases and62 native file-verifier regressions.2028 collected is **not a fresh2028 full run**; historical D34 full1785 remains separate.

Actual native UID/env/host-file/network/write fences, hard CPU/memory/FD/process limits, output/marker/exit/exception rejection, timeout/cancel/no survivor and joined thread cancellation pass. Controlled full reference repairs validate all28 expected oracles; an invalid proposal is retained while other tasks continue, and cancelled generation produces an honest one-attempt partial. Git hook/global-config injection, root/source/link alias denial and independent unrelated-file preservation pass. Ruff correctness/import/format passes10 new Python files/42 described functions/classes. [Final audit](evidence/d38-final-post-audit.json): V006, empty data/quota/vector/worker/lock inventories, no sandbox survivor, original ACLs and321 prior evaluated source/config/dependency/migration hashes unchanged;11 new evaluation files match freeze.

## Follow-up priority and rollback

P2: malformed structured output, dependency D44 bounded failure handling/new held-out tests, estimated half a milestone; risk of retry-driven score selection/overfitting. P2: incorrect clamp reasoning, dependency D46 realistic independent case expansion, estimated one quality milestone; risk that six synthetic tasks do not represent general coding quality. Preserve these first failures and evaluate any later improvements separately. Neither finding authorizes a model switch; MODEL-EVAL-007 remains conditional on the broader approval/sandbox/coding harness and explicit owner approval.

Remove the unused evaluation caller/modules or its private generated artifacts to roll back without model/source/data migration. D39 explicit scoped expiring approval events and user review is next.
