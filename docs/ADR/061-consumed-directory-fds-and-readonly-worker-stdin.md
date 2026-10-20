# ADR-061: Consume mount descriptors and attenuate worker stdin

**Purpose:** Repair two native FD authority gaps found while validating D41 isolation, without replacing models, changing shared data/configuration or broadly refactoring accepted workers.

**Date:** 2026-10-20 (Asia/Ho_Chi_Minh)

**Status:** Accepted and validated within D41 local fixture scope:2269 full PASS/1554.97s,0SKIP,exit0;912 related PASS/40.32s, clean exact-source readonly audit. Earlier interrupted/failed checkpoints retained below. No production action or D42 implementation.

## Evidence and priority

P0 within the active isolation acceptance gate, not deferred architecture cleanup. Trusted native canary probes used only explicitly created temporary fixtures; no real credential/project data was accessed. The pre-fix private Git child retained repository/template directory FDs passed for bwrap mount setup. Native openat(fd,"..") reached a canary outside namespace mounts. Absolute-path absence/network denial alone did not establish capability confinement. The original focused tests missed this path; preserve their actual results and invalidate the incomplete full acceptance, never count419 as full2263 PASS.

Whole-system related-FD review found only document request anonymous regular FDs besides the new private Git directories. A separate controlled canary showed that old document-worker stdin could be reopened through `/proc/self/fd/0` for write, modifying the original temporary payload despite its initial readonly open. UID/GID65534 alone did not fix this: inside the user namespace it still represented the host owner. Do not describe a readonly descriptor flag or namespace UID number as an independently attenuated host file capability.

## Decision

Private Git uses bwrap's descriptor-consuming `--bind-fd` and `--ro-bind-fd`, rather than bind path strings under `/proc/self/fd`. Parent retains its pinned descriptors for joined lifecycle and repeated Git commands; bwrap consumes/closes the child copies after mounting and before program execution. Native regression probes original FD numbers and actual parent-canary traversal, plus verifies the parent's capabilities remain valid. No unsandboxed fallback.

For the existing shared document sandbox command, consume stdin FD0 with `--ro-bind-data 0 /payload`, creating one readonly namespace copy of the already bounded input. Direct ro-bind-fd was rejected during verification because anonymous/unlinked TemporaryFile payloads cannot be resolved for bind mounting on this host; preserve the resulting71-failure/128-pass worker checkpoint as an abandoned compatibility failure. Run one fixed trusted isolated/no-site/no-bytecode Python bootstrap that opens the readonly namespace `/payload`, dup2s it onto stdin, explicitly makes FD0 inheritable, closes the extra local FD and execs the original trusted worker argv without a shell. Reopening `/proc/self/fd/0` now refers to the readonly payload mount and fails EROFS for writes. Other source FDs are closed by subprocess setup. Preserve the original source bytes/offset/worker arguments, runtime/code readonly mounts, resource/timeout/output policies and request metadata binds. The readonly data bind adds one bounded in-memory payload copy (existing admitted file limit<=25MiB); do not claim zero-copy behavior. No new model/dependency/image/Vault/database/config migration or host permissions change is needed.

The shared command change necessarily affects verifier/PDF/DOCX/XLSX/page-OCR workers. Keep their algorithms/contracts/result formats and adapters unchanged; run the entire relevant native worker suite and real pipeline/full regression. This is the reason for changing one previously PASS source file. Do not silently apply UID-only mitigation or rely only on fcntl readonly inspection. Writable stdout remains the intentionally granted bounded result channel; it is not a host directory capability.

## Acceptance and limits

Require actual private Git commit/readback after consumed mounts, no open setup directory FD/parent traversal in the child, and unchanged usable parent FDs. For document stdin, verify exact reads, readonly mount status, denied direct/proc-path reopen/truncate/chmod attempts and unchanged host canary bytes/mode; exercise normal shared workers and valid/invalid documents. Retain exact pre-fix repro, interrupted full metadata and fixed-source evidence separately. Re-freeze all changed and previously accepted related source hashes, run appropriate regression and a new completed full/readonly cleanup audit before PASS.

These probes establish the tested descriptor paths under native Linux/bwrap and controlled fixtures. They do not establish absence of all parser/kernel vulnerabilities, power-loss behavior or hostile same-UID host mutation outside the admitted lifecycle. Existing D40 native atomic writer/model choices/applied migrations/old data remain unchanged. D42 must inherit descriptor-consuming mounts and test both filesystem paths and FD-derived authority before exposing untrusted selected-source execution.

## Readonly namespace scaffold correction

A further controlled probe found the ephemeral namespace root writable outside the intended repository. This was a namespace policy gap, not a host-file write or credential access. The second full run was deliberately interrupted before any confirmed pass marker: actual exit2/214.42s. Preserve its eight artifacts and hashes in `data/backups/d41-pre-root-readonly-manifest.json`; neither interrupted run is a full PASS.

After preparing all mounts, remount `/` readonly in both the private Git and shared document sandbox. The Git repository remains its explicitly writable child mount. DOCX/XLSX request metadata must consequently be bound before the final readonly remount; their existing finite descriptor-backed request construction now inserts its mount before the payload mount. This necessary ordering correction changes two additional previously PASS source files without changing parser algorithms, schemas or adapters. Native tests verify readonly root, denied scaffold creation, consumed setup FDs, immutable host payload and ordinary worker compatibility. The corrected focused invocation reports **213 PASS/22.96s,0SKIP,exit0**. A new exact-source related regression, full suite and final audit remain mandatory.

Expanded regression exposed one related D33 test fixture mount-order dependency:911 PASS/1 FAIL/40.21s, before NO_XDEV checks could execute. Its controlled test mounts now precede payload/final root remount; kernel rejection assertions are unchanged. Preserve this failed checkpoint separately. Verifier documentation now explicitly acknowledges the bounded input copy. Final evaluated scope is24 Python files/161 described functions/classes with371 source hashes/377 unique protected targets; no additional runtime behavior change.

Final evidence: [D41 acceptance](../evidence/d41-checkpoint-acceptance.json), [full regression](../evidence/d41-full-regression.json), [post-audit](../evidence/d41-final-post-audit.json). All earlier pending acceptance statements are historical; corrected-source final gate PASS. No broad parser/model/data/config replacement.
