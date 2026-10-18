# ADR-023 — Authenticated raw file HTTP and cancellation-safe FD lifetimes

**Purpose:** Define how D17 HTTP composes the accepted journal, filesystem and isolated verifier.

**Date:** 2026-10-18 (Asia/Ho_Chi_Minh)
**Status:** Accepted for T04 local scope: full 428 passed in 24.12s, zero skipped; T05 remains open.

## Decision

Reuse the Day 15 UUID bearer principal and direct-loopback dependency on all file routes. Keep file feature default disabled: only `ASSISTANT_FILES_ENABLED=1` initializes resources after checking V002. The dedicated root is `ASSISTANT_FILES_ROOT` or `ai/data/files`; never reuse auth/backups/models. Share the existing process pool, without new credentials, services or public proxy exposure. Day 15 source changes are limited to necessary router registration and optional lifespan initialization/shutdown.

POST `/api/v1/files` accepts only filename/size/SHA/request key. Cap raw metadata at 8 KiB before JSON parsing, including chunked bodies; reject duplicate/unknown keys and malformed lengths. Commit owner quota admission before PUT consumes bytes. PUT `/{id}/content` is a raw stream, rejects multipart, checks actual bytes plus optional length hint, and splits received transport chunks into policy-bounded writes. A ready file is immutable; a second PUT conflicts. Same-key POST replay returns the existing reservation/ready file without charging again; failed/tombstoned keys conflict.

Public metadata is an explicit projection: ID, display filename, size/hash, detected media, state and creation/verification timestamps. No owner override, filesystem key, lease, purge token or fingerprint is exposed. List/detail/download/delete always use authenticated owner scope; foreign/missing/terminal reads are indistinguishable 404s. Transport/DB/parser errors return stable codes, never driver or document-controlled exception text.

Use ADR-020 guard -> short post-lock DB claim -> exclusive writer. Every blocking filesystem/hash/verifier operation runs in a worker thread, outside SQL transactions. `file_io` shields owned work from request cancellation and **joins it before propagating cancellation**. If a cancelled acquisition returns a guard/handle that the caller never received, close that result after joining. Never close/reuse an FD while a thread still uses it. This joining can extend cancellation latency to the verifier's bounded remaining work; kernel-level stuck filesystem I/O remains an operational host failure, not a guarantee from asyncio timeouts.

Maintain periodic DB heartbeat, serialized with manual progress sampling so an older heartbeat cannot regress byte progress. Enforce per-read idle timeout and absolute whole-upload deadline; continuing bytes or heartbeat cannot extend the DB wall deadline. Verification/publish are followed by fresh fencing before ready. Cancellation/disconnection/timeout closes borrowed/writer FDs, then marks interrupted and attempts purge; validation/I/O failures mark rejected. Busy/unsafe/failed cleanup retains quota and is pending for retry. The journal's authoritative deletion target wins over concurrent upload failure cleanup.

The writer uses its reservation's immutable policy snapshot even if the process's new-admission limits change. This requires a per-writer policy override in the existing adapter; root/device safety remains shared. Download reads remain conservatively bounded to 64 KiB chunks.

For download, read owned ready metadata, acquire a SH payload FD, verify actual size/hash through that FD, then recheck ready/owner before headers. Return attachment + nosniff/private no-store, never a static path. The response object owns final close even when cancellation precedes async-generator entry. Delete hides/fences immediately; 204 means physical cleanup complete, while 202/purging honestly reports a held reader/writer or unresolved FS fault. An already admitted download may finish while deletion waits for its shared lock; new reads are hidden.

Lifespan shutdown stops admission, cancels/joins resource-owning requests while the DB pool is still alive, then closes the root and disposes the pool. No automatic deletion on shutdown or lease expiry alone.

## Assessment, rollout and rollback

P0 within planned D17, dependent on T01/T02/T03. Effort is HTTP/service/lifespan and real DB/FS/ASGI fault/race tests. Risks are cancellation use-after-close, counter drift and sending corrupt ready bytes; tests target these directly. No new dependency or schema is required in T04. Default disabled admission preserves existing deployments; T05 still must demonstrate restart recovery, paired metadata/blob restore and an actual process acceptance run before D17 is closed.

Rollback turns off file admission, drains/fences active operations and retains journal/blobs. Existing conversation code can ignore V002. Never drop tables or payloads as a code rollback. Missing/corrupt ready blobs fail closed before headers and retain quota; owner deletion or operator reconciliation is needed, not silent adoption or fabricated bytes.

## Evidence boundary

Real PostgreSQL/private-root HTTP tests cover roundtrip/provenance/replay, owner/auth/proxy negatives, malformed/chunked metadata, observed size/hash/MIME errors, reader/delete pending behavior, missing/corrupt ready blobs, pool/write/publish failures, cancellation while a verifier holds a borrowed FD, cancelled unreturned guards, idle/absolute deadlines, response cancellation before generator entry and joined shutdown. This is local one-worker acceptance, not production multiworker/load or power-loss certification. Exact counts and remaining T05 gates are recorded in the roadmap/dev log.
