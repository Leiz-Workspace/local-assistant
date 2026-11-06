# ADR-024 — Bind file journals and recovery to a durable storage-root identity

**Purpose:** Prevent wrong-root cleanup from releasing quota for bytes that still exist elsewhere.

**Date:** 2026-10-18 (Asia/Ho_Chi_Minh)
**Status:** Accepted with T04: full 428 passed in 24.12s, zero skipped; runtime feature remains default disabled.
**Extends:** ADR-019/020/021/023.

## Context and assessment

An absent pathname proves nothing when the operator accidentally configures another empty root. The same issue appears if integration-test roots share the app database with production metadata: an unscoped recovery worker could infer that a foreign root's payload is absent and release its allocation. UUID-derived object keys and inode locks alone do not identify which storage root the journal describes.

This is P0 correctness within the existing D17 quota/recovery gate, not an added product feature. Dependencies are the private root, immutable reservation metadata and safe startup. Effort is a durable identity marker, scoped repository/recovery operations, startup checks and negative tests. Risks are identity loss during restore or unsafe automatic adoption; the decision explicitly rejects both. No new service, credential, endpoint or schema migration is required.

## Decision

Create/read `.storage-namespace` through the anchored root FD: canonical UUID plus newline, regular owner-owned 0600, single link, O_NOFOLLOW/O_EXCL, file and parent fsync. Reopen preserves identity. Invalid, partial, public, symlinked or hard-linked markers fail closed without overwrite/repair. Runtime purge never removes the marker or stable resource directories. This metadata is not a client input.

Include `_storage_namespace` as a reserved internal context key alongside limits in the immutable JSONB reservation snapshot. The typed `StoragePolicy` constructor receives only actual limit fields after validating/removing this context. This avoids rewriting already-applied V002; its JSONB snapshot already permits immutable contextual metadata. Policy version remains 1 and the semantic replay fingerprint remains owner/normalized filename/size/hash; namespace never changes request semantics or allows cross-owner deduplication.

Runtime FileService creates a namespace-bound journal. Every read/mutation lock/replay/recovery batch enforces this binding; global/owner usage still counts allocations across all namespaces. A same-owner request key belonging to a different namespace conflicts as an unavailable storage configuration, never replays/charges anew. Cleanup checks the snapshot binding *before* touching FS or releasing allocation. Trusted maintenance repositories may remain explicitly unscoped; routes do not use them.

On enabled startup, load the protected current principal bindings and reject a root if any outstanding allocation for these principals belongs to a different or missing namespace. This catches a newly configured empty root before admission. Historical unbound records are not silently adopted. Test roots with distinct test principals remain isolated; their recovery cannot touch another root's rows.

Paired restore must preserve the source namespace explicitly when creating an isolated target, verify every DB-referenced blob/hash/permission and restore the same principal UUID bindings. The adapter's optional trusted `namespace_id` constructor supports that controlled restore, while refusing to replace a different existing identity. A deliberate verified restore may change device/inode/path; the durable namespace is the logical identity. Copying a marker without verified paired bytes is not a restore procedure.

## Consequences and rollback

The marker is a required protected backup artifact. Losing it disables startup rather than reassigning resources. JSONB namespace filtering is adequate for the local bounded workload; indexing/typed migration can be reviewed with future scale needs. No RLS or malicious same-UID isolation is implied by this binding.

Rollback disables admission and retains marker/journal/payloads. Never delete the marker to make startup succeed, rewrite another root's identity, or release quota to hide missing bytes. Restore/adoption of pre-binding records requires separate operator verification and a migration plan, not an automatic startup fix.

Tests cover persisted identity/reopen, explicit isolated restore identity, invalid marker forms and FD cleanup, foreign-root list/read/delete/replay/recovery denial, allocation retention and startup rejection for the same principals. Existing owner/auth and FS acceptance must remain regression PASS.
