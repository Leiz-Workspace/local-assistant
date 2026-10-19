# ADR-051: Explicit read-only workspace capabilities

**Purpose:** Define D33 repository/workspace discovery and a filesystem boundary before adding coding tools.

**Date:** 2026-10-20 (Asia/Ho_Chi_Minh)

**Status:** Accepted design; local adapter acceptance requires actual negative filesystem tests. No API/tool deployment is authorized by this ADR alone.

## Scope and priority

D32 commit `9928957` accepts the defined local knowledge gates. D33 is P1, depends on existing owner UUID policy and D32; estimated one foundational milestone. Risks include traversal, symlink/magic-link/mount escape, hard-link aliases, root replacement, accidental git execution and path/content leakage. There is no existing workspace module to extend. D34 will add bounded inventory/search with source-line provenance; no D34 implementation or model change is folded into this foundation.

## Decision

Add immutable owner/workspace UUID specifications with explicit absolute root paths and display names. No cwd/home/repository-parent inference, environment expansion, URL/path import or automatic registration. At most8 roots per catalog; no shared mutable global catalog. Authorize exact owner and workspace ID before any filesystem open. Unknown and foreign IDs fail identically.

The Linux adapter opens each absolute root beneath `/` without following symlinks, then pins its directory FD. All relative targets resolve beneath that FD through `openat2` with BENEATH, NO_SYMLINKS, NO_MAGICLINKS and NO_XDEV. The checked local x86_64 Linux syscall ABI is437. Other architectures/platforms and kernels without this primitive fail closed; no weaker resolve-then-open fallback. Configured roots may themselves reside on a mount; traversal to a different mount beneath the root is forbidden. Kernel flags are enforced, not a user-space path-prefix comparison.

Public relative paths are bounded clean POSIX paths: no absolute paths, traversal/dot/empty components, backslashes, control characters, hidden components or excessive length/depth. Root and each admitted FD are read-only/CLOEXEC; NONBLOCK plus fstat rejects FIFO/socket/device targets, and regular hard-linked files are rejected. Root identity is reopened and compared before entry admission; replacing/moving its configured pathname invalidates that handle. Handles are explicitly joined/closed by context managers. Existing authorized FDs represent admission-time capabilities; this is not a sandbox against arbitrary same-UID host processes or an atomic guarantee against file movement after admission.

Discovery only classifies an owned configured root as a directory, a git directory marker or an unresolved regular git worktree-pointer marker. It never reads `.git` content/pointers, follows gitdir paths, invokes git/hooks/config, scans parents or executes repository instructions. A symlinked/unsafe `.git` marker fails closed. Hidden entries are excluded from the future public read interface; the discovery-only internal `.git` inspection cannot be requested by a user path.

The returned descriptor contains only workspace UUID, configured display name, repository marker kind and read-only status, not absolute root, principal credentials or file contents. Error/log events contain stable codes and workspace IDs only. This library has no HTTP route, CLI identity shortcut, automatic startup, database writes, credential access, model invocation or production flag. D33 acceptance is the tested local capability/discovery foundation; authenticated application exposure belongs to D34 and needs its own tests.

## Compatibility and rollback

All D16–D32 accepted source/model/config/database/infra files remain byte-identical. New modules are unused until explicit composition in a later task. Rollback removes their imports/registration without changing repository files or data; no migration, reindex or model download is required. `MODEL_REGISTRY.md` remains authoritative. Before coding tools can execute or modify, later D35/D39–D45 permissions, approval, budgets, sandbox and injection gates are mandatory.


## Local verification

[D33 acceptance](../evidence/d33-workspace-acceptance.json) records63 new filesystem/contract cases within288 related PASS/7.02s,0 SKIP/exit0 and clean current system audit. Actual same-device bind mount receives native EXDEV, boundary-time symlink swap is denied, and readonly/owner/root/cleanup gates pass. One missing-import error in the strengthened child test harness is retained and fixed without changing the runtime guard or oracle. Acceptance is the local unused capability/discovery foundation; authenticated inventory/search is D34, execution and writes require later gates.
