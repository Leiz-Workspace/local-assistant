# File metadata and bounded local storage — D16 specification

**Purpose:** Define the owner-scoped schema, storage contract, limits, consistency and rollout gates for D17 implementation.

**Date:** 2026-10-18 (Asia/Ho_Chi_Minh)
**Status:** D16 design/policy PASS after review on 2026-10-18. No file migration, filesystem adapter or upload/download HTTP implementation is applied by this document.
**Baseline:** Day 15 commit `60c431b`; authenticated localhost, one API worker; shared PostgreSQL V001; UUID principals from ADR-018.

## 1. Scope and dependency review

| Work | Priority | Dependency | Effort estimate | Risk and decision |
|---|---|---|---|---|
| Metadata, ownership, quota and disk contract | P0 | Day 15 owner identity and transaction rules | D16 design milestone | Wrong owner/quota accounting exposes data or exhausts storage; define before upload |
| Migration/repositories/local blob adapter/HTTP streaming | P0 | This design, fresh backup, D17 integration/FS tests | At least one D17 implementation milestone; extend if gates fail | Cross-resource atomicity and symlinks require real failure/race tests |
| MIME/container validation | P0 | D17 bounded stream and quarantine state | Part of D17; do not schedule extraction until accepted | Extension and declared MIME are hints; generic ZIP is not proof of OOXML |
| PDF/DOCX/XLSX extraction and downstream provenance | P1 | Verified ready files, owner checks and bounded parsers | D18–D23 baseline | Content remains untrusted; no parser/model runs merely because upload completed |
| MinIO blob backend | P2 / deferred | Concrete portability/scale need, scoped app bucket policy and adapter parity tests | Re-estimate before scheduling | Existing shared MinIO is available; introducing its credential/consistency dependency is unnecessary for local V1 |
| Cross-owner deduplication, remote URLs, archives, macro files | Deferred | Separate product/security assessment and ADR | Not scheduled | No global content-addressed sharing, SSRF surface or implicit executable content |

The 90-day roadmap is a planning baseline. D17 may span several implementation milestones; a filename policy test does not complete its FS/DB/HTTP acceptance.

## 2. Storage choice and trust boundaries

PostgreSQL remains the source of truth for metadata, ownership, state, idempotency, leases and allocated usage. Binary payloads use a private Linux filesystem root, initially `ai/data/files`, on the existing local ext4 volume. The observed filesystem had approximately 617 GiB available at inspection; this is a measurement, not a reservation or performance guarantee. The policy's logical global allocation is 10 GiB and the free-space floor is 2 GiB.

The root is process-UID owned, mode 0700; payloads are 0600. Root/staging/object directories must share a filesystem. No uploads, storage directories or new credentials are created by D16 helpers. Existing `ai/data/auth` and `ai/data/backups` are outside the future blob root and must never be traversed by blob cleanup.

Derive keys solely from server UUIDs:

```text
objects/<owner-uuid>/<first-two-file-hex>/<file-uuid>.blob
staging/<owner-uuid>/<file-uuid>/<upload-lease-uuid>.part
```

Original filenames are display labels, never joined to the root. API consumers receive file UUIDs and metadata; internal paths/keys, owner override fields and lease details are not public inputs. The root is trusted operator configuration, not a request parameter. No arbitrary local-file import, remote fetch or object key is accepted.

Reuse the existing bearer principal and direct-localhost dependency. Every list/read/download/replace/delete/replay/cleanup query scopes `owner_id` before exposing data or reserving work. Missing, deleted, wrong-owner and unowned files produce the same 404 shape. The new table has a typed UUID owner (unlike the legacy conversation JSONB owner); both refer to the same authenticated principal namespace. There is no automatic adoption/backfill of legacy conversation ownership and no new user table or Keycloak realm change.

## 3. Version 1 policy

The executable source of policy defaults and pure validation is `src/application/services/file_storage_policy.py`.

| Limit | Default | Enforcement point planned for D17 |
|---|---:|---|
| Reservation JSON envelope | 8 KiB | Bound raw request before JSON parsing, including chunked requests |
| Per-file declared and actual bytes | 25 MiB; empty files rejected | Before reservation and on every received chunk |
| Per-owner allocated bytes/files | 1 GiB / 1,000 | Atomic usage-row reservation, including pending/purging files |
| Global allocated bytes/files | 10 GiB / 10,000 | Atomic singleton usage row; not a quota over unrelated server apps |
| Active upload reservations/owner | 2 | Reserved through ready/cleanup; abandoned reservations expire |
| Active upload reservations/global | 4 | Same transaction as metadata insertion |
| Physical free-space floor | 2 GiB | Check before accepting reservation and during write; handle ENOSPC/fsync failure |
| Streaming chunk | 64 KiB | Bounded reads; never buffer a declared file in memory |
| Reservation TTL | 300 s | DB-clock lease for metadata awaiting a body |
| Stream wall deadline / idle deadline | 300 s / 30 s | Explicit request deadline and last successful byte progress |
| Upload lease / heartbeat | 60 s / 15 s | DB-clock owner lease, capped by stream wall deadline |
| OOXML expanded bytes / entries / ratio | 100 MiB / 1,000 / 100:1 | Header preflight plus actual bounded decompression/CRC validation |

Supported suffix/media families: PDF; DOCX/XLSX with verified OOXML content types/relationships; TXT/MD/CSV as verified text; PNG/JPEG/WebP as verified image containers. `.jpg` and `.jpeg` share image/jpeg. Text detection may report text/plain for Markdown/CSV, but downstream parsing still has its own acceptance. Generic ZIP, executable/script/HTML/SVG, macro-enabled Office and future audio/video types are excluded.

Normalize display labels to NFC; cap at 255 UTF-8 bytes. Reject empty/hidden/path-like labels, leading/trailing whitespace, trailing dot, controls/format characters, Windows reserved names and separators/ADS/percent/path punctuation. This deliberately conservative V1 label policy is independent of path safety; opaque UUID keys and descriptor-safe I/O are still mandatory. Changes to accepted formats/limits require a versioned policy review, boundary tests and update of the HTTP/design contract.

A canonical internal verifier media type must agree with the suffix. A declared type may be absent or application/octet-stream, otherwise it must agree with that family. A generic application/zip result never proves DOCX/XLSX. Bounds helpers check reported totals; they do not sniff bytes, decompress archives or make an uploaded payload safe. Verification must inspect required OOXML package parts, reject macros/encryption/nested archives/path traversal/symlink entries, bound XML parsing and avoid external entities/network relationships. Read/check entries without extracting them into arbitrary paths. Parsers must check observed expansion, not only attacker-supplied ZIP totals.

## 4. Proposed V002 metadata (not migrated)

Create only additive tables in schema `assistant`, using the existing migrator identity from Vault. `assistant.files` is the resource journal:

| Field | Proposed type / invariant |
|---|---|
| id | UUID PK, generated by server; UNIQUE(id, owner_id) for future owner-aware references |
| owner_id | UUID NOT NULL from authenticated principal; indexed with state/created_at/id |
| display_name | TEXT NOT NULL, 1–255 UTF-8 bytes; application applies the NFC/label policy |
| declared_size_bytes | BIGINT NOT NULL, >0; policy cap checked at reservation |
| expected_sha256 | CHAR(64), lowercase hex; required before body admission |
| actual_size_bytes / actual_sha256 | Nullable until verification; when ready equal declarations |
| detected_media_type | Nullable until internal container/text verification completes |
| state | reserved, receiving, verifying, ready, purging, deleted, rejected, interrupted |
| request_key | Nullable VARCHAR(128); UNIQUE(owner_id, request_key), including tombstones |
| request_fingerprint | CHAR(64), canonical semantic metadata fingerprint version 1 |
| storage_backend / storage_key | `local_fs` V1; unique key derived from owner/file UUIDs, never arbitrary path |
| policy_version / verification_version | Immutable reservation policy version; verifier version set on verification |
| source_kind / uploaded_by | local_upload / authenticated principal; no remote URL fetch |
| created_at / updated_at / verified_at | TIMESTAMPTZ using DB time; verified_at required for ready |
| lease_owner / lease_expires_at / claimed_at | Nullable worker UUID and DB timestamps, with absolute stream deadline |
| bytes_received | BIGINT, 0 <= value <= declared_size; sampled at bounded intervals, not per-byte SQL |
| upload_slot_released_at / quota_released_at | Nullable timestamps fencing exactly-once counter release |
| purge_target / error_code | Terminal target deleted/rejected/interrupted; stable safe code, no driver/content text |
| deleted_at | Set at logical deletion request; owner APIs immediately stop exposing file/content |

Ready CHECK: actual size/hash match expected; media/verifier/verified_at present; no quota release; upload slot released. Terminal CHECK: quota and upload slot released and payload absent by application cleanup verification. `purging` still owns quota. Keep tombstones/request fingerprints to make replay deterministic; do not hard-delete metadata in ordinary HTTP delete. Later retention/privacy cleanup needs an explicit policy, including the idempotency window.

Use structural SQL CHECKs for nonnegative counters, valid states, hash syntax, release markers and owner-derived key equality. For the key check, the expected expression is `objects/` + owner UUID + `/` + first two file UUID hex characters + `/` + file UUID + `.blob`. No client-supplied key reaches INSERT. File caps belong to versioned policy under locked reservation; a runtime config edit does not rewrite existing reservation semantics.

Add `assistant.file_owner_usage` keyed by owner UUID and `assistant.file_global_usage` with singleton key CHECK(key=1). Each holds `allocated_bytes`, `allocated_files`, `active_uploads`, `updated_at`; counters are nonnegative integers, active uploads <= allocated files, bytes >= allocated files and zero files implies zero bytes. Global counters cover every owner's allocations. File data is charged for the entire declared size from reservation until physical purge and close, including staging, ready, rejected-pending-cleanup and failed deletions. Mark/release flags and counter changes commit together; repeated cleanup never decrements twice.

No file data or usage counters are backfilled from conversation text/model weights/backups. Initial global row is zero and owner rows are created atomically on first reservation. A future conversation attachment relation is a separate migration with both resource ownership checks; D17 standalone files do not implicitly become model context.

## 5. Reservation, replay and locking

Use canonical fingerprint version 1 over principal UUID, NFC display label, declared byte size and lowercase expected SHA-256. Exclude generated file UUID and request key so a same-key retry can locate the original resource. Changed filename/size/hash under the same key returns 409; owner scopes never share replay. A null key creates a separate charged resource, even for identical bytes. No global or cross-owner deduplication.

Proposed future HTTP shape (not registered in D16):

| Operation | Proposed route / response |
|---|---|
| Reserve | POST `/api/v1/files`, bounded JSON filename/size/sha256/request_key; authenticated owner assigned internally; 201 |
| Stream reserved body | PUT `/api/v1/files/{id}/content`, raw bounded byte stream; application/octet-stream; verified ready result |
| Metadata/list | GET `/api/v1/files/{id}` and GET `/api/v1/files` with bounded owner-scoped pagination |
| Download | GET `/api/v1/files/{id}/content`, only own ready file; attachment/nosniff headers and bounded stream |
| Delete | DELETE `/api/v1/files/{id}`, immediately hide, queue/perform bounded purge; report pending cleanup accurately |

Exact HTTP schemas/status codes are finalized and tested in D17. Reservation JSON is capped at 8 KiB before parsing and rejects unknown fields; do not rely solely on field validation or Content-Length. File body bytes are streamed only after successful metadata/quota admission; multipart parsing/spooling before quota reservation is not the V1 contract. Content-Length is an optional transport check, never proof of actual file length; terminate at the first extra byte beyond declaration/cap. A short body or SHA mismatch is rejected and purged.

Transaction A locks **global usage -> owner usage -> file resource** in this order for admission and any counter mutation. Lookup a same-owner request key under these locks before allocating counters; exact reserved/ready replay returns the existing resource, while receiving/verifying/purging/terminal repeats return a deterministic conflict/state response. Only one PUT owner lease may transition reserved to receiving. Slot/capacity checks and metadata insertion commit atomically. A free-space snapshot is advisory because other server applications can write the same disk; handle actual ENOSPC and preserve cleanup accounting.

Do not hold a SQL transaction/session during streaming, hashing, verification, file-lock waiting or fsync. Heartbeat uses short transactions. At finalization/recovery, lock global -> owner -> file and fence state/worker/live lease before publishing a DB-visible ready result. File ownership and all quota release operations are mandatory even if an internal caller bypasses the HTTP adapter.

## 6. Blob durability, locks and crash journal

D17 implements a local adapter behind a blob-storage port; the D16 helper produces keys but performs no I/O. Anchor all path traversal to an operator-opened private root descriptor. Walk/create server-derived directories with dir_fd, O_DIRECTORY/O_NOFOLLOW and fixed permissions. Open staging with O_CREAT|O_EXCL|O_NOFOLLOW; verify regular-file fstat/ownership, no arbitrary root/symlink substitution and no cross-device staging/final paths.

Use cooperative Linux file locks on payload descriptors: writers hold exclusive lock until all writes/verification/finalization finish; download readers hold shared locks; purge must obtain a nonblocking exclusive lock. A dead process releases the lock; a paused/unresponsive process does not. Expiry alone therefore never proves its FD is closed. Skip/retry purge while an old writer/reader still holds a lock, retaining quota. This avoids releasing quota for unlinked bytes still held open by a stale writer or download. Acquire/wait for no FS lock while holding DB locks.

Write chunks to the staged FD while hashing and enforcing observed byte/deadline/free-space limits. Verify from the same controlled FD/duplicate, without parser-driven path reopening or arbitrary extraction. fsync the file. Publish without replacement on the same filesystem (e.g. descriptor-anchored exclusive link plus inode/regular-file verification); never use overwrite-capable rename blindly. fsync parent directories and remove the staging name after durable publication. EEXIST requires verifying the expected owned publication/state or failing safely; do not overwrite a supposedly colliding object.

State sequence:

```text
reserved -> receiving -> verifying -> ready
reserved/receiving/verifying -> purging -> rejected or interrupted
reserved/receiving/verifying/ready -> purging -> deleted (explicit owner deletion)
```

`ready` means verified format/hash/size and durable publication, not semantic trust, malware immunity or permission to execute/extract. Source instructions remain untrusted. Download always authorizes metadata, opens/locks a regular controlled blob, rechecks ready/owner after lock acquisition and streams from the FD. A deletion race either proceeds before download admission or waits for readers; no path is reopened after authorization. Owner deletion during upload first hides/fences the row and requests cancellation, then waits outside SQL transactions for the exclusive payload lock. Return an honest pending-cleanup result until old FDs close and purge/release completes; do not claim physical deletion from a tombstone alone.

DB and filesystem cannot commit atomically. The journal deliberately hides every non-ready object:

| Failure boundary | Required recovery |
|---|---|
| Reservation committed, no body | Expired owned reservation -> purging, release only after proving no payload/held lock |
| Partial stream/crash/cancellation | Fence old lease, acquire exclusive payload lock, remove only its UUID keys, fsync, close, then release counters |
| Verified payload published, DB not ready | Remains hidden/charged; prove worker dead/expired and use owned journal state to finalize only if every invariant is verified, otherwise purge conservatively |
| DB ready, staging link remains | Keep original ready blob; remove only redundant staging link after lock/inode verification; do not release ready quota |
| Delete requested, unlink/fsync failed | Keep hidden purging state and quota; retry cleanup, never report physical deletion complete |
| Purge complete, DB release failed | Retry DB transaction using release markers; never decrement twice or make counters negative |

Recovery/reconciliation is owner/resource scoped and lease/file-lock fenced, never a glob-delete of arbitrary paths. Unknown files or legacy unowned journal entries are reported/quarantined for operator review, not deleted or adopted. A bounded startup/periodic report can reconcile counters/known stage names, but does not bulk-expire live workers. No second service/queue is required for V1's single worker; restart recovery uses the persisted journal.

## 7. Provenance, privacy and backup

Retain file UUID, uploader/owner UUID, original display label, expected/observed hash/size, detected media, source kind, policy/verifier version and creation/verification timestamps. Future extraction artifacts refer to file UUID + immutable content hash + page/sheet/span locators and recheck source owner/ready state. Filename/file content is data, never a system instruction. No reasoning trace, credential, raw payload or untrusted label is written to audit logs; log stable IDs, sizes, state transitions, quota counts and safe error codes.

After D17 starts storing blobs, a DB-only backup is insufficient. Drain file mutations/processing, snapshot metadata and inventory/hash of all referenced ready/staged objects with release states, copy opaque blobs preserving permissions, verify every referenced payload SHA-256, and restore DB+objects together into isolated targets. Keep encryption/access/retention review for private data. Restore the same principal UUID binding through the existing app Vault/auth configuration; token rotation preserves that UUID. Credential recovery must never silently assign stored resources to a newly generated identity. Day 15's DB backup does not prove future blob recoverability. App files are private, not static web assets, and ignored by Git.

## 8. Rollout and rollback (future D17)

1. Keep upload feature disabled and leave Day 15 endpoints unchanged. Inspect current V001, principal config and free capacity; create/verify a fresh protected DB backup using the existing operator procedure.
2. Implement additive V002 migration and explicit app grants with the dedicated migrator secret retrieved from the existing app Vault path. No root/app-superuser credential enters API. Review offline DDL, FK/check/index/locking/grant/downgrade plan and integration results before applying to the shared app DB. No migration is generated/applied by D16.
3. Create a new dedicated private root (do not repurpose auth/backups/models), validate device/permissions/symlinks, then implement/test adapter, journal and owner/quota repositories with upload disabled.
4. Complete the acceptance matrix below with real PostgreSQL and disposable directories/FDs. Confirm no old stateless/conversation behavior regression; only then enable authenticated loopback file routes. Review bounded parser dependencies via uv; existing MinIO/Vault policies stay unchanged.
5. Rollback disables new admission first, drains/cancels writers while fencing leases, preserves journal/usage rows and private blobs. Existing Day 15 code can ignore additive tables. Never drop tables or delete blobs merely to roll code back. Downgrade is allowed only for a proven empty new schema under reviewed maintenance; otherwise use forward fixes or an explicitly reviewed paired DB/blob restore.

## 9. Design review and D17 acceptance matrix

D16 review confirms ownership matches ADR-018; default bounds fit observed capacity; same-key semantics exclude generated IDs; quota counts staging/purge; lock order is consistent; expiry cannot release a held inode; publish-before-DB crash stays hidden; backup/rollback preserve the journal and bytes. Pure policy tests verify labels/keys/hashes/fingerprints/media/size/quota/archive bounds and log privacy. They do **not** prove atomic SQL reservation, MIME sniffing, descriptor I/O or durability.

D17 must supply observed results for:

- Two principals cannot list/read/download/send/delete/replay each other's files or claim an owner/key.
- Simultaneous quota reservation at byte/count/upload limits, unique replay and counter consistency across independent connections.
- Raw stream overflow/short body, hash mismatch, interrupted body, idle/wall timeouts, disk-full/fsync failure and bounded memory/FD usage.
- Header/extension spoofing, macro/encrypted/bomb/traversal/symlink ZIP entries, XML/entity/network references and actual expansion limits.
- Symlink/hardlink/root traversal, final collision, inode substitution, EXDEV and permissions using real disposable directories, including no overwrite of another object.
- Crash at every tabled DB/FS boundary; expired paused worker/reader holds lock -> quota retained; kill closes lock -> safe cleanup; no double release.
- Delete/download/cleanup races, absent/corrupt ready blob, restart recovery and bounded worker shutdown.
- Paired metadata/blob backup and isolated restore; no D17 completion from DB-only backup or plan text.
- Existing Day 15 complete regression plus new real integration/HTTP tests; exact passed/skipped counts and ADR/dev-log update.

## 10. Actual D16 acceptance — 2026-10-18

- Design review completed against Day 15 principals/repositories, V001/Alembic layout, current dependencies, shared-service restrictions and measured disk capacity. Reservation/quota, journal states, FD-lock release, owner-deletion races, identity restoration and rollback were checked for consistency.
- `uv run python -m pytest tests/test_file_storage_policy.py -q --tb=short`: **86 passed in 0.06s**.
- Complete Vault-backed PostgreSQL/CORE regression: **237 passed in 9.48s**, zero skipped and no exclusions (151 prior cases plus 86 policy cases).
- Read-only app-credential schema verification: `0001`, exactly four existing assistant tables; no file schema/migration applied.
- Existing API/runtime/owner/lease/recovery source files and dependencies remained unchanged. D16 adds only this specification, ADR-019, the isolated policy module/tests and progress records.

D16 is accepted as a design/policy milestone. D17 is NEXT; all actual upload/DB/FS/container/HTTP/paired-backup behaviors in section 9 remain implementation acceptance, not inferred PASS from this review.


## 11. D17-T01 implementation checkpoint — 2026-10-18

`src/infrastructure/local_blob_storage.py` now implements the standalone Linux filesystem foundation. `tests/test_local_blob_storage.py` has **66 passing cases**; the final complete Vault-backed PostgreSQL/CORE regression has **303 passed in 10.38s**, zero skipped/no exclusions. This supersedes the earlier no-adapter current-state statement for D17 only; section 10 remains the historical D16 acceptance.

The adapter anchors a 0700 root and generated directories with no-follow directory FDs, writes exclusive 0600 staging files in bounded chunks, checks observed size/hash and actual disk floor, lends a sealed verifier FD, rechecks bytes after verification, fsyncs and publishes using no-replace hard links. It holds exclusive writer/shared reader locks and purges only after all exact payload inodes can be exclusively locked. Link/permission/inode errors, collisions and unknown staging entries fail closed. Purge closes payload FDs and syncs directories before returning true; a failed unlink/sync remains pending and retry resyncs absent names.

[ADR-020](ADR/020-resource-directory-locks.md) adds a persistent resource-directory lock to close the absent-name/create-before-inode-lock gap. **Required integration:** acquire its guard outside SQL transactions, recheck/claim the DB lease under the guard, then pass the guard to `create_writer`. The writer retains its duplicate until close. Deletion must fence the journal before purge and release counters once in a final fenced transaction. Guard directories are intentionally retained. Standalone adapter calls without a journal do not provide authorization, DB fencing, quota reservation or exactly-once release.

Actual filesystem process tests kill an uploader at creation, write, seal, link, object-directory sync, staging unlink, staging-directory sync and completed publication. Separate writer/reader processes retain their locks while SIGSTOPped and release them after SIGKILL. ENOSPC/short-write/EXDEV/fsync errors are injected against disposable real files; they do not prove physical power-loss durability or a real full-disk event. Inventory/FD-count/log-privacy tests run without production data.

No production blob root, V002 migration, parser dependency, runtime route or new infrastructure service was introduced. Read-only app-credential inspection still shows `0001` and four existing assistant tables. Day 15 runtime source/config is unchanged.

**Remaining D17 gates:** V002 and atomic owner/global quota/idempotency journal; live lease/recovery integration; every allowed format's bounded MIME/container verification; HTTP owner ACL/deadlines/cancellation/download/delete races; paired metadata/blob backup and isolated restore. T01's FS evidence does not complete those gates. D17 remains IN PROGRESS and D18 is not started.


## 12. D17-T02 journal checkpoint — 2026-10-18

Additive V002 is now applied by the existing Vault migrator after fresh protected backup plus isolated app row/owner/ACL restore verification (`data/backups/d17-v002-preflight-20261018`, no shared restart). Existing conversation/message/run row and owner/ACL fingerprints match before/after migration. Three new tables contain the file journal and global/owner usage; no production blob root or HTTP route is enabled.

`PostgresFileJournal` implements serialized admission/replay, immutable policy snapshots, owner-scoped reads/locks, monotonic DB-clock upload leases, verification/ready transitions, deletion/expiry fencing and exactly-once counter release. [ADR-021](ADR/021-file-journal-and-quota-transactions.md) records schema, rollout/rollback and caller obligations. Empty-only downgrade refuses populated journals, including tombstones.

All **24 real journal cases** passed in the full **327 passed in 11.41s** regression, zero skipped/no exclusions. Tests include independent-connection quota/replay races, typed-owner isolation, stale lease/progress, structural checks/grants, populated downgrade rejection and actual guard/FD/DB cleanup interactions. These tests do not bypass the need for a real HTTP service, bounded MIME verifier or paired metadata/blob restore. D17 remains IN PROGRESS; T03 is next.


## 13. D17-T03 verifier checkpoint — 2026-10-18

The isolated verifier now handles every allowed format from a sealed FD. [ADR-022](ADR/022-isolated-file-verification.md) defines read-only runtime/code mounts, cleared environment, separate Linux namespaces/network, no host data mounts, CPU/RAM/FD/file-output/wall limits, exact format subsets and fail-closed behavior. Existing Bubblewrap 0.11.1 was reused; uv added only pypdf 6.21.1 and defusedxml 0.7.1. No routes or live payload root enabled.

**62 tests passed in 6.05s** for valid formats/hostile containers, real host-file/environment/network isolation and kernel resource limits, real timeout with no leftover process, malformed worker verdicts and log privacy. Complete regression: **389 passed in 17.53s**, zero skipped/no exclusions with existing PostgreSQL/CORE. T04 HTTP integration and T05 paired restore/reconciliation remain open; D17 is not complete.
