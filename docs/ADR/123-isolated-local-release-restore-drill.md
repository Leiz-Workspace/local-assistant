# ADR 123 — Isolated local release restore drill

**Purpose:** Define D84 actual PostgreSQL/logical-vector/blob/config restore evidence without modifying original application data or restarting shared services.

**Date:** 2026-10-23. **Status:** Accepted for bounded owned local drill/tests; not off-host disaster recovery or release approval.

## Decision

Require quiet existing PostgreSQL consumers. Read canonical row and ownership/ACL fingerprints; stream a private custom-format dump of local_assistant with the existing reviewed RecoveryAcceptance helper. Restore only into its newly generated `la_restore_probe_<uuid>` database, compare every table and security fingerprint, then remove only that target. Recheck original rows/security/revision/inventory. Do not execute the older helper's main run, insert canaries into original tables, restart PostgreSQL or change roles/Vault/schema.

Require the currently observed Qdrant baseline to have no collections. Record that emptiness honestly. Use two newly generated guarded probe collections to demonstrate a nonempty logical-vector/payload/index export/restore with three authored8dimensional float canaries. These are storage fixtures, not an embedding model or production schema. Verify exact restored vectors/payloads and keyword index schema, delete only the two owned names and require original empty inventory restored. Do not create snapshots or change an original collection. A populated real collection requires a separately reviewed quiet export plan, not an automatic extension of this drill.

Copy only a fixed allowlist of non-secret existing model/embedding/rollback/runtime config bytes to private backup and separate restore directories, verifying complete hashes. Demonstrate nonempty object bytes/hash/metadata pairing with a synthetic private blob; original file/object tables may be empty and must be reported as such. Never tar arbitrary paths, follow links, copy Vault tokens/auth/signing keys or restore over originals. Retain protected dumps/config/object/vector evidence locally, publishing only digest/count outcomes.

## Impact and rollback

Existing D84/P1; dependencies actual Docker PostgreSQL/local Qdrant, existing private Vault admin credential access, quiet consumers, original configurations and reviewed restore helper. Effort one bounded integration/drill milestone. Risks include accidental deletion/overwrite, leaked backups, concurrent source mutation and partial restore. Fixed sources, exclusive0700/0600outputs, guarded minted target IDs, exact content/security comparisons, cleanup in finally and fail-closed changed inventories constrain them. Do not delete retained failure evidence. No cross-host/roles-from-scratch/production failover/RPO/RTO/SLO or model-selection claim. Actual target cleanup is required before marking this drill complete.
