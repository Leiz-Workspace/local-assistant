# D42 approved snapshot checks

**Purpose:** Describe the finite test/lint execution contract, exact approval workflow, retained evidence and limits without suggesting arbitrary host commands or automatic quality approval.

**Status:** PASS (local finite approved snapshot scope). Fresh **2461 full PASS/1536.84s,0SKIP,exit0**,1104 related PASS/62.41s subset,192 new cases;396 source/409 protected hashes and clean readonly audit. [Acceptance](evidence/d42-checks-acceptance.json), [full result](evidence/d42-full-regression.json), [audit](evidence/d42-final-post-audit.json), [ADR-060](ADR/060-approved-snapshot-checks-without-host-execution.md), [freeze](evidence/d42-checks-freeze.json), [related result](evidence/d42-related-regression.json). These are overlapping gates, not additive counts.

## Available behavior

Separately default-off local API composes accepted workspace capabilities, exact process-local approvals and durable private checkpoints. An owner selects1–16 explicit `.py` files and their expected raw SHA256 digests, then chooses one server-owned profile. The service captures private source/runtime bytes and publishes the complete concrete review. Proposal creation and approval review do not execute a program.

| Profile | Fixed command in the namespace | Supported scope |
|---|---|---|
| `python_unittest` | `/runtime/bin/python3.12 -I -S -B -m unittest discover -s /snapshot -t /snapshot -p test_*.py` | Selected self-contained stdlib Python files; no third-party packages or subprocess support |
| `ruff_check` | `/runtime/bin/ruff check --isolated --no-cache --ignore-noqa --no-respect-gitignore --target-version py312 --select E9,F --output-format json /snapshot` | Syntax/static correctness observations; no auto-fix or host configuration/plugin discovery |

Each nonhidden relative path has at most4 components/256 UTF-8 bytes. Each source is valid UTF-8 without NUL, at most8192 raw bytes; aggregate maximum128KiB. Source/root/parent/native metadata and complete selected byte hashes are bound into the review. A changed original needs a new proposal/review even though its earlier snapshot still exists. The live source is never mounted into the executing namespace.

The explicit captured runtime contains the existing trusted Python executable, bounded stdlib inventory and existing pinned Ruff copy. Normal isolated interpreter imports use the captured stdlib; host `.venv`, home and uv cache are not mounted and project startup hooks are not automatically loaded. Read-only trusted `/usr` remains visible for OS support and can contain system packages/tools: this is not a hermetic absence-of-all-host-package-content guarantee. Explicit imports/exec by untrusted source retain the same namespace, seccomp and resource restrictions; additional frameworks are not supported or claimed verified. Existing Ruff seed SHA256 is `20cf97c5db04ca9c51249dec1a54cbc96c24462df280334ada04b8f3c877b746`; capture verifies the operator-declared executable hashes. A uv cache seed with multiple links is accepted only as a stable explicitly hash-pinned seed; the private copy must have one link. No download/install/model change is part of this feature.

## Explicit operator configuration

`ASSISTANT_CHECKS_ENABLED` defaults to0. Enabling requires live workspace/approval/patch/checkpoint services and all settings below. No environment file is changed by implementation or tests.

| Setting | Required value |
|---|---|
| `ASSISTANT_CHECKS_ROOT` | Explicit existing owned0700 native directory outside workspace and checkpoint ancestry |
| `ASSISTANT_CHECKS_PYTHON_PATH` | Explicit trusted existing Python executable path |
| `ASSISTANT_CHECKS_PYTHON_SHA256` | Exact expected executable SHA256 |
| `ASSISTANT_CHECKS_STDLIB_ROOT` | Explicit matching existing stdlib root |
| `ASSISTANT_CHECKS_RUFF_PATH` | Explicit trusted existing Ruff executable path |
| `ASSISTANT_CHECKS_RUFF_SHA256` | Exact expected executable SHA256 |

Storage retains32 jobs globally/8 per owner, reserves512KiB per job/16MiB total jobs and independently bounds the shared captured runtime at64MiB. Admission ceiling80MiB; actual allocated blocks, file/directory counts and canonical record sizes are bounded. Unknown, partial or corrupt entries are retained and fail closed. There is no automatic garbage collection, history deletion, grant refund or resumption.

## Local API and review

All endpoints are under `/api/v1/workspaces/{workspace_id}/checks`, require existing local bearer authentication, reject foreign Origins and enforce owner/workspace scope. Responses use private/no-store and nosniff headers. Inputs reject extra keys, duplicate/nonfinite JSON and oversized bodies through the accepted bounded route layer.

| Method/path | Meaning |
|---|---|
| `POST /checks` | Capture exact selected files and create a new pending `run_checks` request |
| `GET /checks` | List bounded own retained metadata |
| `GET /checks/{job_id}` | Read verified own history and known live observations |
| `POST /checks/{job_id}/run` | Explicitly attempt the exact already-approved linked request once |
| `POST /checks/{job_id}/cancel` | Explicit empty JSON action; cancel own pending/running work and join it |

The table paths are relative to `/api/v1/workspaces/{workspace_id}`. Example proposal body:

```json
{
  "profile": "python_unittest",
  "files": [
    {"path": "value.py", "expected_sha256": "<64 lowercase hex characters>"},
    {"path": "test_value.py", "expected_sha256": "<64 lowercase hex characters>"}
  ]
}
```

Review the returned `approval_id` using the existing CLI:

```sh
uv run --no-sync python -m scripts.review_approval --base-url http://127.0.0.1:<port>/api/v1 --request-id <approval_id>
```

The CLI reads the bearer privately, displays the complete artifact and requires typing `APPROVE <approval_id>` or `REJECT <approval_id>`. No action runs as a side effect. The separate run request body is `{"approval_id":"<linked canonical UUID>"}`. The review binds owner/workspace/job, source/native/private snapshot/runtime versions, command, CPU, budgets and output policy; its process-local proposal lifetime is120s. A prior patch/rollback grant, arbitrary UUID, changed scope, expired request or consumed request cannot run a job.

## Native execution and truthful results

Before launch, durable intent precedes one-shot consumption after fresh source/runtime/private-copy checks. A newly owned launcher thread pins its own CPU before spawning the native process; the caller/file-I/O thread's affinity stays unchanged. The launcher and owned child always join before source/runtime capabilities close. Shutdown drains checks before checkpoint/approval/workspace dependencies.

Strict fresh user/network/process namespaces, actual UID/GID1000, no capabilities, cleared allowlisted environment, nested-userns disable/assert, consumed read-only source/runtime setup descriptors and a read-only root protect the host boundary. A sealed x86_64 filter rejects affinity changes, fork/vfork and non-thread clone, permits bounded shared-address-space threads and returns ENOSYS for clone3 fallback; x32 is denied/unknown architecture killed. No fallback executes on the host. Programs requiring subprocesses are unsupported by this version.

Limits:10s parent wall,512MiB address space,2s soft/3s hard CPU, fixed one allowed CPU,16 threads,64 FDs,1MiB scratch-file size, core0 and16MiB writable private tmpfs. This is an address-space policy, not a measured RSS/RAM/VRAM benchmark or a whole-system kernel-memory bound. OS loader/shared-library support under read-only `/usr` is trusted and is not an immutable OS-image guarantee; privileged OS updates require drain/revalidation.

Output retains exact bounded base64 bytes, SHA256, byte count, encoding/EOF/completeness flags and actual exit/signal/timing/start acknowledgement. Stdout is bounded16384 bytes and stderr4096. Overflow/timeout/cancel kills and joins owned native work. Raw source/output, bearer, nonce and credentials are excluded from audit logs. IDs, outcomes, counts and hashes remain auditable.

**Exit0 or printed PASS is not functional-quality proof.** Test source can forge markers or exit without assertions. `quality_evaluated=false` and `output_is_untrusted=true` remain explicit. No output grants approval, accepts a patch, changes models or completes a roadmap gate. Native host-authored fixtures/oracles establish this boundary milestone; broader coding quality remains D43–D46.

After native completion, close original source pins before terminal journal publication. A terminal recording/send failure preserves the known observation and reports persistence uncertainty; it never reruns to recover acknowledgement. `persisted_state` describes verified disk state separately. Restart reads historical intent/observations without reconstructing source capabilities or old approval grants. A `starting` journal cannot establish whether a program ran or exited.

## Verification and retained failures

192 new cases cover finite schemas, sealed BPF, actual unittest success/failure/forged-success/Ruff, hostile environment/FD/mount/userns/resource/affinity behavior, launcher ownership, timeout/output/cancel/kill fallback, runtime/native source capture, tampering, quota/reopen/history, real approval/replay, journal/close uncertainty, lifecycle and actual HTTP/TCP/CLI. Lost ASGI delivery preserves actual native results. Actual SIGKILL drills cover three acknowledged non-running stages: captured, durable starting before consumption, and completed native exit before terminal publication. They do not prove every crash/power-loss window or authorize cleanup of unknown entries.

The earlier CPU-affinity reset negative test failed1/.13s; retained source/log archive documents the real bypass and correction before acceptance. Initial65/87 checkpoints missed it. The corrected97 checkpoint and later1104 related result include the fixed inherited affinity plus syscall denial. Initial Ruff allocation/thread and nested-userns probes, uv seed hardlink incompatibility and errno assertion failures remain documented in ADR/devlog. HTTP's first14 functional passes also had13 teardown errors because a new fixture asserted enclosing lifespan state too early; actual shutdown assertions now wrap the real callback, followed by14 PASS and expanded gates. That failed invocation is not a completed HTTP gate.

The current complete source archive and earlier failed versions are durable private ZIPs under `data/backups/`; hashes and source maps accompany the evidence. [D38 immutable original4/6](D38_CORE_CODING_BASELINE.md), selected model/config/migration/data and completed D41 evidence remain protected. All executions/approvals use disposable synthetic fixtures, not a production workspace. See [evaluated backlog](CODING_AGENT_BACKLOG.md) for conditional package runtimes, retention, broader patch scopes and durable authority.
