# D84 — Actual isolated local restore drill

**Purpose:** Document verified restore coverage, retained private artifacts and exact original-data protections.

**Status:** Local isolated drill VERIFIED. [ADR123](ADR/123-isolated-local-release-restore-drill.md).

Actual quiet PostgreSQL custom dump60622bytes restored into a newly generated probe database. All12application tables and normalized ownership/ACL fingerprints matched; original row/security/revision fingerprints before/after remained unchanged, schema0006. Only the owned restore database was removed; no original canary inserts, schema/role changes or shared restart. The reviewed existing RecoveryAcceptance.verify_restore was used directly; its old main/restart workflow was not run. Protected dump/manifest remain under data/backups/d84-isolated-restore-first/postgres, never committed.

Actual Qdrant inventory was empty before/after, reported as zero original collections. Two owned canary collections demonstrated logical export/restore of3nonempty8dimensional authored vectors, exact payloads and2keyword indexes; both targets removed. These are storage canaries, not a replacement embedding configuration or proof of restoring a populated original index. A changed/nonempty original inventory fails closed before vector mutation.

Four fixed original non-secret model/embedding/E5rollback/runtime config files copied to separate private backup/restore directories and matched byte-for-byte. One39byte synthetic object was independently copied/restored and matched its metadata hash. Original object/source metadata is preserved in the database dump; no claim of a populated real user blob restore is made. No auth/Vault/signing keys were copied into public artifacts.

**11new/16related controls PASS0.19s/0FAIL/0SKIP/Ruff PASS**, followed by the actual Docker PostgreSQL/local authenticated Qdrant drill. Tests cover namespace/delete guards, original inventory refusal, failure cleanup, private exclusive/no-follow outputs, bounded artifacts, config symlink refusal and exact canary roundtrips. Frozen reviewed execution source matched after completion. [Native/source/log receipts](evidence/d84-isolated-restore-verification.json).

This proves same-cluster local logical restore assuming existing roles and runtime. It does not certify off-host disaster recovery, a new cluster restored from globals/Vault, production failover, RPO/RTO/SLO or broader release readiness. Keep private backups until the owner explicitly authorizes deletion; never run a restore over original stores. D85 bounded failure/load tests are next; manual/product/model/format gates remain open.
