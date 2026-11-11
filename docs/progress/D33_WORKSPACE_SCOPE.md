# D33 explicit workspace discovery and scope boundary

**Purpose:** Document the read-only local workspace capability foundation and the precise boundary required before D34 repository reads.

## Ownership and configuration

[ADR-051](../ADR/051-readonly-workspace-capabilities.md) defines this new unused foundation. `WorkspaceSpec` requires exact owner/workspace UUIDs, an explicit clean absolute root and a bounded display name. `WorkspaceCatalog` accepts at most8 immutable specifications; an empty catalog authorizes nothing. There is no current-directory fallback, automatic repository-parent search, environment/home expansion, external repository import or global runtime registration.

Authorization precedes root access. Foreign, unknown and incorrectly typed UUIDs produce the same `workspace_not_found` error. The caller must supply the authenticated owner from the future application composition; a client must never choose it. No HTTP/CLI/tool identity shortcut or runtime flag is introduced in D33. All existing application wiring, accepted source/configuration, models and database state stay unchanged.

## Actual filesystem boundary

A clean configured root opens beneath `/` without symlink ancestors and remains pinned by a directory FD. `openat2` resolves relative entries with BENEATH, NO_SYMLINKS, NO_MAGICLINKS and NO_XDEV. This blocks traversal, internal/external symlink indirection and mount/bind-mount crossings beneath the allowed root. The root itself can reside on its explicitly configured mount. The checked local x86_64 Linux ABI is required; unsupported platform/kernel fails closed without a weaker fallback.

Public relative paths are exact bounded POSIX paths (4096 UTF-8 bytes,64 parts), without absolute/dot/traversal/empty components, backslashes, control characters or hidden components. Hidden secrets and `.git` are therefore excluded from the future public read interface. File handles open read-only/CLOEXEC/NONBLOCK; only regular single-link files and directories are admitted. FIFO/socket/device and regular hard-link aliases are refused. Every root/entry FD closes on success, caller interruption, native inspection error and unsupported-kernel failure.

The configured root pathname is reopened and its inode compared before entry admission. Root replacement or movement invalidates further use. Open FDs represent admission-time capabilities: this library does not prevent arbitrary same-UID host processes from changing files, nor promise atomic path membership after admission. Directory FDs are internal runtime objects; they must never become user-selectable handles or a way to pass arbitrary OS flags. This is an allowlisted library interface, not an execution sandbox.

## Discovery only

`discover()` returns workspace UUID, configured display name, `read_only=true` and one marker classification:

| Kind | Meaning |
|---|---|
| `directory` | No `.git` marker at the explicit root; no parent search |
| `git_directory` | The root has a safely admitted directory marker; its contents are not read |
| `git_pointer_unresolved` | A regular marker exists; its gitdir pointer is not read or followed |

Unsafe/symlinked markers fail closed. No git command, hooks/config load, model, file mutation, test execution or repository instructions run. The classification is not a complete git-validity check and does not authorize access to external worktree metadata.

Discovery and errors expose no absolute root or source text. Logs contain stable event/error codes and workspace IDs; configured display names are returned intentionally. D34 must build bounded inventory/text search with current root/source checks, verified file/line provenance and authenticated composition. D35/D39–D45 must separately establish tool budgets, explicit approvals, edits, rollback, execution isolation and injection defenses.

## Verification

```sh
uv run --no-sync python -m pytest tests/test_workspace_policy.py tests/test_readonly_workspace.py -q -rs --tb=short
```

Tests use disposable roots and a synthetic outside canary. Actual kernel cases cover in-root reads, readonly writes denied, owner-before-open, symlink ancestors/targets, hard links, FIFO/socket, configured-root replacement, a symlink swap exactly before kernel admission and descriptor cleanup. A credential-free bubblewrap private namespace mounts the synthetic outside directory beneath the root to verify actual NO_XDEV enforcement. No host mount or repository file is changed. Controlled platform/ENOSYS/fstat failures are distinguished from actual kernel cases.

**D33 PASS for the defined local capability/discovery foundation.** [Acceptance](../evidence/d33-workspace-acceptance.json):63 new cases are included in **288 related PASS/7.02s,0 SKIP, exit0**. Actual same-device private bind mount is rejected by native EXDEV; a boundary-time symlink swap cannot expose the outside canary. Readonly FD/owner/root replacement/hidden paths/descriptor cleanup and existing blob/parser sandbox policies all pass.

The strengthened mount harness initially produced287 PASS/1 FAIL/7.03s because its child code lacked `os`/`errno`/helper imports. Only the child test imports were corrected; the stronger native EXDEV/same-device oracle and runtime guard were retained. Earlier59 and63 focused/288 related checkpoints remain historical subsets. Application collection1684 succeeds; no fresh1684 full run is claimed. D31 full1608 and D32 focused99 remain separate baselines.

[Post-audit](../evidence/d33-final-post-audit.json) confirms V006 inventories/security unchanged and no app/pending/vector/worker/lock residue. All accepted D32 runtime/config/model/dependency/migration bytes remain unchanged; only new unused workspace modules/tests/docs are added. D33 has no authenticated repository endpoint; **D34 inventory/search and application exposure remain next**, not implicitly implemented.
