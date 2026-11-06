# ADR-059: Private Git checkpoints and newly approved byte rollback

**Purpose:** Define the D41 checkpoint/rollback gate without executing an existing workspace's Git hooks/configuration or reusing an old write grant.

**Date:** 2026-10-20 (Asia/Ho_Chi_Minh)

**Status:** Accepted and validated within D41 local fixture scope:2269 full PASS/1554.97s,0SKIP,exit0;912 related PASS/40.32s, clean exact-source readonly audit. Earlier interrupted/failed checkpoints retained below. No production action or D42 implementation.

## Priority, dependencies, effort and risk

Existing roadmap D41 is P1 after D40 acceptance; one checkpoint/rollback milestone plus native fault, restart, real HTTP/CLI and related regression/audit work. It depends on D33 scope capabilities, D39 fresh explicit approvals and D40 exact single-file/version/commit semantics. Estimated effort is one milestone with separate storage and approval integration gates, not a promised calendar duration. Risks include untrusted project Git execution, source leakage in backups/logs, unbounded private objects, false durability claims, lost post-commit journal acknowledgements, restoring stale/wrong-owner bytes and confusing checkpoint inspection with permission to roll back. No model/dependency/migration/Docker/Vault/database change is proposed.

## Proposed decision

Store scoped single-file checkpoints in a dedicated explicitly configured application-owned private directory, outside registered workspace roots. Use a new private Git object repository controlled by the application, with original exact raw source bytes plus canonical owner/workspace/proposal/path/root/version/hash metadata. A private Git commit is a checkpoint of the admitted file, not a claim to snapshot the entire user repository. Do not change the user's branch/index/working tree for checkpoint creation and do not run Git in an existing user-controlled `.git` directory.

Use the already accepted native bubblewrap mechanism with a writable mount of only the pinned private Git directory, read-only trusted system runtime/empty template, fresh process/network/user namespaces, cleared environment, no host home/workspace/Vault mounts and no capabilities. Preserve the actual unprivileged application UID/GID inside the namespace (native owned-write probe confirmed UID/GID1000 maps to owner1000 on the host). No Docker or new dependency is needed; isolation failure has no unsandboxed fallback. Apply trusted prlimit before fixed Git:256MiB address space, CPU2s soft/3s hard,256KiB per-file size,32 FDs,16 processes and core0, plus bounded pipes/five-second parent wall deadline and joined process-group cleanup. These are enforced policy limits, not measured RSS/throughput claims.

Use only fixed trusted system Git plumbing commands, cleared environment/global/system configuration, empty template, disabled hooks/signing/attributes/filters/pager/editor/network and no model-selected executable, command, ref, object name or storage path. Internal Git object IDs are not the approval authority: independently verify SHA256 of canonical metadata and exact raw content. Checkpoint roots/entries must remain owned private nonsymlink native identities. Hardlink/unsafe-metadata/changed-root cases fail closed. Never log source/diff/replacement/private root or credentials.

Implementation bounds after D40 acceptance:

| Resource | Proposed bound |
|---|---|
| Storage | Explicit dedicated root outside all registered workspaces;0700 directories/private0600 content |
| Count |128 global checkpoints,32 per owner; incomplete reservations count |
| Bytes |256KiB reserved per checkpoint,16MiB global reservation ceiling; independently reject oversized actual storage |
| Original source | Existing D40 limit8192 raw bytes; no broader file read |
| Canonical metadata |8192 UTF-8 bytes; typed IDs, relative path, native identity/version and source/review SHA256 only |
| Git | Fixed private source/metadata blobs and commit;5s per fixed command,20s checkpoint stage; stdin16384/stdout65536/stderr4096 bytes, killed process group and joined exit |
| Concurrency | Single process/root writer lock, nonqueued service admission; no cross-worker replication |

No silent checkpoint retirement or Git garbage collection is proposed. Capacity exhaustion stops new proposals without workspace writes; historical/incomplete records remain accounted for until a separately designed explicit retention operation. Native process deadlines require cancellation/join and do not promise preemption of blocked kernel I/O.

Capture a checkpoint from D40's immutable admitted original bytes before publishing the linked pending review; private backup writes are distinct from workspace writes. Bind canonical checkpoint metadata to the unchanged complete D40 review SHA256, owner/workspace/proposal/path/source version and original/replacement hashes. Expose checkpoint identity separately without rewriting an already registered approval artifact. A source change while backing up still fails D40's fresh pre-apply source fences.

Create and verify the original checkpoint durably before any D40 workspace temporary write or approval consumption. Persist an intent/receipt journal with explicit original/replacement hashes and known source identity; fsync acknowledged storage and directory changes rather than inferring durability from Git exit0. If checkpoint/journal persistence fails before mutation, stop with source unchanged. The successful D40 rename remains the source commit point. A later journal persistence error cannot turn an applied edit into an unapplied failure; retain/report applied-but-journal-uncertain state and prohibit automatic retry. Attempt terminal journal recording after joined cancellation too, using the actual native receipt; never persist a fabricated unapplied result because the client lost its acknowledgement.

New checkpoint integration must preserve the accepted default-off local D40 scope and read-only tools. General coding-agent release must require durable checkpoint capability before exposing project mutation; do not silently claim durability for the standalone earlier ephemeral fixture mode. Specify the exact opt-in/dependency behavior before implementation and retain previously accepted tests unless a necessary reviewed integration change applies.

## Rollback authority

Checkpoint read/list endpoints authorize exact typed owner/workspace before content access or side effects. A checkpoint contains historical bytes, not a reusable grant. Rollback creates a new complete D40 proposal from verified checkpoint bytes against the current explicitly admitted file's exact source version/hash. The owner must review the full resulting diff and approve its new D39 scope/nonce; apply uses the same native D40 final fences and one-shot consumption. Foreign/changed checkpoint, current source/root/parent/path change, stale/replayed approval and unsupported metadata fail closed.

The bounded first scope restores one existing file's bytes while preserving the current eligible native metadata under the reviewed D40 contract. It does not reset a branch, delete new files, restore a whole repository or silently change permissions. State explicitly whether checkpoint and current modes differ; do not call bytes-only restoration a metadata rollback. Automated drill uses synthetic owners/files and actual private Git commits, separate explicit fixture approvals, changed intermediate source and exact restored-byte/hash assertions. It is not a real production rollback approval.

## Restart and uncertain outcomes

Restart invalidates all old ephemeral proposals/grants and never resumes an edit. Durable checkpoint/journal inspection is recovery evidence only. Validate private record integrity and current admitted source through fresh owner/workspace capabilities; report original/replacement/other/missing/uncertain observations without overwriting source. Equal bytes alone do not prove which process caused them. Require a new proposal/review for any restoration.

Persist temporary inode identity before claiming recovery ownership. An abrupt process loss between creating a temporary inode and durably acknowledging its identity remains an orphan-uncertainty window; do not infer ownership from a filename or unlink guessed entries. Any cleanup must use verified retained record/native inode identity and preserve unrelated entries. No power-loss, hostile same-UID CAS or multi-file transaction guarantee is implied. Distinguish controlled process termination/fault injection from an actual machine crash.

## Acceptance before D41 PASS

Freeze the final limits/storage schema and architecture, then test actual Git commit/raw readback/hash, exact owner/path binding, private permissions, quota/capacity, hooks/config/filter/network isolation and bounded Git failure/cancellation. Prove checkpoint failure prevents all workspace writes and consumed grants; prove post-rename journal failure preserves applied/uncertain status. Verify restart invalidates grants and reports all recovery classifications without edits or guessed cleanup. Run actual local proposal→CLI review→apply→new rollback proposal→new CLI review→restore on disposable fixtures, plus foreign/stale/version/replay/metadata cases. Re-run affected D33–D40 gates and required full regression/audit before advancing D42. Preserve D38 first model failures and all selected models/configurations/data/migrations. No implementation or PASS claim while D40 remains open.


## Native FD authority correction before acceptance

Independent canary validation found inherited private mount directories could traverse their host parent, so the initial full run was intentionally stopped at419 confirmed pass markers/exit2; it is not a full PASS. [ADR-061](061-consumed-directory-fds-and-readonly-worker-stdin.md) records consuming native --bind-fd/--ro-bind-fd mounts and the necessary shared document-stdin repair after related-system review. The original first full/freeze/log/712-related artifacts and original source archive remain private evidence. A new actual completed fixed-source full/audit is required. No D42 implementation or D41 PASS occurred.

Final evidence: [D41 acceptance](../evidence/d41-checkpoint-acceptance.json), [full regression](../evidence/d41-full-regression.json), [post-audit](../evidence/d41-final-post-audit.json). All earlier pending acceptance statements are historical; corrected-source final gate PASS. No broad parser/model/data/config replacement.
