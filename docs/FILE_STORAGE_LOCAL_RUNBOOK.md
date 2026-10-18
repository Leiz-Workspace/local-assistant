# File storage — authenticated local operation

**Purpose:** Operate the accepted D17 file feature, preserve ownership/namespace and run its protected paired recovery drill.

## Runtime and access

Use the existing PostgreSQL/Vault and one API worker bound directly to `127.0.0.1`. Follow the credential delivery in [conversation runbook](CONVERSATION_API_LOCAL_RUNBOOK.md): runtime receives app `DATABASE_URL` and protected digest-only `ASSISTANT_AUTH_FILE`, never an operator Vault token. Current app/API credentials already exist in Vault under `secret/server/local-assistant/postgresql` and `secret/server/local-assistant/api`; migration identity is separate. Token rotation must preserve principal UUIDs.

File resources initialize only with `ASSISTANT_FILES_ENABLED=1`, revision V002 and matching principal/root bindings. `ASSISTANT_FILES_ROOT` defaults to `ai/data/files`; keep it dedicated, 0700, with private 0600 payloads/namespace marker. Changing to another empty root while these principals have allocations fails startup. Do not delete/replace `.storage-namespace` or persistent resource-lock directories.

After secure app-credential delivery, from `ai/`:

```sh
ASSISTANT_FILES_ENABLED=1 \
ASSISTANT_AUTH_FILE="$PWD/data/auth/principals.json" \
ASSISTANT_FILES_ROOT="$PWD/data/files" \
uv run uvicorn apps.api.main:app --host 127.0.0.1 --port 8000 --workers 1
```

Default feature flag is off; setting it does not create another infrastructure service. Bubblewrap `/usr/bin/bwrap`, working unprivileged namespaces and the uv-locked runtime are required; missing isolation rejects verification without fallback. Browser Origin/proxy headers are rejected by the existing loopback boundary.

## HTTP contract

| Operation | Request/result |
|---|---|
| Reserve | POST `/api/v1/files`, JSON `filename`, `size_bytes`, `sha256`, optional `request_key`; 201 |
| Upload | PUT `/{id}/content`, raw bytes; use application/octet-stream; 200 only after verification/durable publication |
| List/detail | GET collection or `/{id}`; owner-scoped metadata, bounded pagination |
| Download | GET `/{id}/content`; ready only, attachment/nosniff, full size/hash check before headers |
| Delete | DELETE `/{id}`; 204 after physical purge or 202/purging while cleanup remains pending |

Always send the existing bearer credential. IDs/owner/key/lease/path fields are assigned by the service. Same-key/same-declaration POST replays the existing live reservation/ready record without charging twice; changed declarations and failed/terminal keys return conflict. A ready PUT is immutable/conflicts; use GET to recover an acknowledged/uncertain result. New intentional retries after terminal failure require a new request key.

Limits and supported format subsets are defined in [design](FILE_STORAGE_DESIGN.md) and ADR-022: 25 MiB/file, 1 GiB/owner, 10 GiB/global, bounded counts/upload slots/free space, 8 KiB metadata, UTF-8 text, verified raster/PDF/OOXML. Encrypted/active/macro/ZIP64/external-linked/animated or oversized structures may be rejected by conservative V1 bounds. Verification does not grant semantic trust, execute content, attach to conversations or start extraction automatically.

## Recovery and maintenance

Startup and a five-second loop reconcile bounded known journal batches. Expired lease alone never releases allocation: the old writer/reader must release its inode/resource lock and physical purge must complete. A paused process retains quota; a dead process releases locks. Busy cleanup is retried fairly; redundant known ready staging links are removed only after same-inode/hash proof. Unknown/colliding/corrupt files remain quarantined for operator review; no glob-delete or silent adoption occurs.

Inspect safe stable-code logs such as `file_purge_pending`, `file_ready_reconciliation_pending`, `file_storage_root_namespace_mismatch` and pool metrics. Keep unresolved quota charged. Stop admission and drain before filesystem/database repair; do not reset counters or markers to hide a fault.

## Paired backup/restore drill

Stop API consumers first; resolve active/purging uploads and run a verified nonempty fixture if this is an acceptance drill. Deliver the existing app DB credential securely, then use a **new** backup directory:

```sh
uv run python -m scripts.file_storage_recovery_acceptance \
  --source-root data/files \
  --auth-file data/auth/principals.json \
  --backup-directory data/backups/CHOOSE_A_NEW_PRIVATE_DIRECTORY
```

The operator CLI needs existing local Docker PostgreSQL administrative access for dump/probe restore. It reuses the instance; no shared restart or production restore/overwrite occurs. Artifacts include DB archive/verification, blobs, an independent restored blob root, namespace identity, digest-only principal bindings and a success manifest. All remain protected/ignored; never commit/package them with source. Retention/encryption/off-host procedures require a separate operational plan.

Accepted retained evidence: `data/backups/d17-paired-20261018/manifest.json` has paired/database/security/identity verification true, one 53-byte fixture, seven restored tables, matching hashes/permissions and no remaining DB probe. The actual API process drill stopped both owned workers and removed only its test resource; final allocation is zero and existing conversation rows/ACLs are unchanged.

For real recovery, verify the complete paired set in isolated targets first, preserve namespace/principal UUIDs and current credential-revocation policy, then review activation while the old deployment is drained. Existing DB-only Day 15 backups are insufficient once blobs exist. Rollback disables admission and preserves tables/bytes; never downgrade populated V002 as a code rollback.
