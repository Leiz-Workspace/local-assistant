# ADR-020 — Stable resource locks around local blob creation and purge

**Purpose:** Close the gap between journal fencing, payload creation and physical cleanup without changing the Day 15 runtime.

**Date:** 2026-10-18 (Asia/Ho_Chi_Minh)
**Status:** Accepted for D17-T01 filesystem implementation; PostgreSQL/HTTP integration remains unaccepted.
**Extends:** [ADR-019](019-bounded-local-file-storage.md).

## Context

An inode lock alone cannot protect a payload that does not yet exist. A purger could observe no staging name immediately before an old uploader creates it, or open a new staging inode before its writer has acquired the exclusive inode lock. Releasing quota in either interval would violate the D16 allocation contract. A database lease checked before waiting for a filesystem lock does not eliminate a delayed stale worker.

Unknown staging names are also positive evidence of unresolved bytes. Ignoring a different lease name while returning successful cleanup would allow a journal mismatch to release quota prematurely. Deleting it without its journal is equally incorrect.

## Decision

Use the stable private directory `staging/<owner UUID>/<file UUID>` as an additional cooperative Linux `flock` anchor. It is never removed by ordinary file deletion. Acquire its exclusive lock nonblocking before creating a staged inode or inventorying/unlinking payloads. A writer duplicates the guard descriptor and retains it through publication and close, including after the service admission context exits. Retain the existing payload locks: readers use shared inode locks; purge requires exclusive locks on all known payload inodes before unlinking anything.

The future service must use this order:

1. Authenticate/authorize metadata; reservation already owns quota.
2. Acquire the resource directory guard outside a SQL transaction; busy means retry/conflict.
3. Recheck/claim the live DB lease and state in a short transaction while retaining the guard. Do not hold a DB transaction while acquiring a filesystem lock.
4. Pass that guard into `create_writer`; consume bytes only after the claim commits. Keep the writer open until the fenced DB ready transition or failure handling has finished.
5. Deletion/recovery first hides/fences the DB resource, then calls purge outside SQL transactions. Release counters exactly once in a final DB transaction only after purge returns true and the row is still correctly fenced. A stale uploader acquiring the guard later must fail the post-lock DB recheck before creating a payload.

Guards are bound to UUIDs and the actual directory inode, preventing a guard from another root from being passed accidentally. A replacement guard directory is rejected when it disagrees with the writer's parent inode. Private same-UID processes must cooperate; this does not isolate a malicious process with the same OS identity or root.

Inventory only the known resource staging directory. An entry other than its journal lease name raises `untracked_staging_entry` and leaves all bytes in place. Distinct staging/final inodes raise `object_collision`. Untracked hard links, wrong permissions, symlinks and nonregular inodes fail closed. No glob deletion, cross-lease discovery/adoption, path import or quota release occurs inside the adapter.

Successful purge means exact payload names are absent, parent directories have been fsynced and local FDs have closed. Busy or failed purge means keep quota. On retry after an unlink/fsync failure, fsync the existing parent even if the payload name is already absent. Keep unknown/colliding objects for operator reconciliation.

## Alternatives and impact

| Alternative | Outcome |
|---|---|
| Payload inode locks only | Rejected: cannot lock an absent name or eliminate the create-before-flock gap |
| Hold DB locks over filesystem lock waits | Rejected: pool exhaustion and lock inversion; no atomicity across SQL and FS |
| Removable lock file/directory | Rejected: unlink/recreate can split one resource into multiple independently locked inodes |
| Dedicated lock service or another database instance | Unnecessary for the existing Linux localhost single-worker scope |

This is P0 correctness work within D17, dependent on ADR-019 and required before journal/HTTP integration. Effort is one filesystem subtask plus integration validation. Costs are retained empty control directories, additional directory descriptors/fsync operations and nonblocking busy responses. Cleanup of tombstones/control directories requires a separate retention design; never remove lock anchors opportunistically. Async HTTP code must move blocking file work off the event loop, serialize access to a handle and close borrowed verifier FDs before returning.

No runtime route imports the adapter yet. No database migration, production blob root, infrastructure service, credential, dependency or Day 15 source is changed by this subtask. Rollback removes its unused code or leaves it disabled; never delete runtime data to roll back code.

## Evidence and remaining gates

`tests/test_local_blob_storage.py` exercises actual private files, paths, hard links and Linux locks; independent spawned readers/writers are stopped/killed; an uploader is killed at eight FS publication boundaries. It also injects ENOSPC, short writes, EXDEV and file/directory fsync failures. Tests cover guard transfer, another-root guards, creation/purge interleaving, unknown leases, collisions, idempotent cleanup, descriptor counts and log privacy. Exact final commands/counts are recorded in the D17-T01 dev-log checkpoint.

These tests do not certify PostgreSQL quota/replay races, lease/recovery transactions, HTTP deadlines/ACLs, MIME/container validation, paired metadata/blob restore, power-loss behavior or production multiworker operation. D17 remains IN PROGRESS until its complete acceptance matrix passes.
