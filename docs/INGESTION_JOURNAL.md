# D25-T02 — Durable source-bound ingestion journal

**Purpose:** Document the accepted repository boundary, immutable generation identity, actual migration/restore procedure and remaining vector-worker gates.

## Scope

[ADR-034](ADR/034-durable-ingestion-journal.md) precedes implementation. V003 adds `assistant.ingestion_jobs` and `assistant.ingestion_heads`; V004 explicitly overrides inherited table UPDATE grants on those new relations. Existing migrator default privileges, source tables, model selection, E5 rollback, file root/auth/namespace and services remain unchanged. There is no ingestion route, background worker or vector-service call in this milestone.

Jobs persist canonical source/access/model manifest, expected deterministic UUID points, complete token counts, admission revision, lease/retry/deadline and terminal cleanup state. They persist no document text, vectors or parser payload. Heads bind desired/active job IDs to the same owner/namespace/file/model through composite foreign keys. Runtime app has DML plus UPDATE on mutable columns only; manifest/source/model/point/count identity cannot be updated. There is no new PostgreSQL RLS claim: trusted runtime code and source fences remain part of authorization.

## Repository protocol

`PostgresIngestionJournal(sessions, namespace_id)` binds the repository to a trusted existing storage namespace. `admit(plan, counts)` requires T01 trusted extraction/source-reader integrity and actual tokenizer preflight before it is called. It validates immutable snapshot identity, then locks global admission with a transaction advisory lock, the owner/root-scoped source and journal/head rows. The canonical source/ready/hash fence is rechecked inside the transaction. DB transactions have5-second lock and15-second statement/idle bounds, not disk/model/network work.

Identical replay returns its original job before queue-capacity checks and never changes the requested head. Conflicting counts/manifest/point identity produce409. New input increments the desired admission revision, fences older pending/running work and retains any still-valid active generation until replacement commits. At most128 pending/running jobs globally and32 per owner/namespace; same-file superseded jobs remain durable terminal records. Tombstone retention is not automatic deletion.

`candidates` pages due pending/expired work. `claim` generates a fresh server-side lease UUID, validates source/head/due/deadline, increments attempt and caps its120-second expiry by a one-hour absolute deadline. Five attempts maximum. `heartbeat` renews only a live matching token. `retry` fences that token and persists exponential2–30-second backoff; failed/stale/tombstone/ready work never silently returns to pending. DB time is authoritative. Reclaimed work has a different token, so an old process cannot publish or renew.

`publish` accepts only the complete ordered expected point IDs after trusted T03 acknowledgements. It verifies live lease, latest desired revision and current source, then atomically marks job ready and changes the active pointer; replacement tombstones the previous generation. These acknowledgements are currently a repository input, not proof of actual Qdrant writes. T03 must execute wait-for-acknowledgement vector operations and validate source/point/count/hash identity before calling it. Transaction-fault tests prove job/pointer updates roll back together. If the publication acknowledgement is lost after commit, read the durable job/head to confirm ready identity; an old cleared lease is not revived by reissuing publish.

`active` joins the current source owner/root/ready/hash state, hiding deleted/stale sources immediately even before async reconciliation. This helper is not the D26 retrieval adapter or a final delivery authorization check. `reconciliation_candidates` discovers invalid sources, including already-published jobs; `reconcile_file` pages and tombstones invalid work, clearing affected desired/active pointers. Keyset cursors explicitly cast NULL UUID values for real psycopg/PostgreSQL type inference. `cleanup_candidates` pages retained terminal generations; `acknowledge_cleanup` records a trusted exact-generation deletion acknowledgement idempotently. Neither method deletes vectors or source rows.

Existing source deletion code is unchanged. A future T03 loop must run the durable reconciler and cleanup path; no event hook or worker is secretly enabled by applying a schema. File journal FK references preserve source metadata until reviewed ingestion retention/cleanup has completed.

## Actual rollout and safeguards

1. Rendered/reviewed `0002:0003` offline SQL; no old-table DDL or new role/service. Existing PostgreSQL17.10 had revision0002 and quiet consumers.
2. Ran fresh private backup/restore in `data/backups/d25-t02-pre-v003-20261018`, all seven application tables verified; no shared restart. Archive checksums/owner-only permissions validated.
3. Existing Vault migrator applied V003. Existing seven-table rows and normalized owner/ACL fingerprints stayed unchanged except migration version/new objects. [Rollout evidence](evidence/d25-t02-v003-rollout.json).
4. Actual app-role tests exposed inherited default table UPDATE grants. Preserved applied V003, recorded correction in ADR-034, reviewed/applied forward V004 to revoke UPDATE on only ingestion tables then restate mutable-column grants. Existing default policy/old-table grants were untouched. [V004 evidence](evidence/d25-t02-v004-grants.json).
5. Repeated protected restore after V004 in `data/backups/d25-t02-post-v004-20261018`: all nine tables, schema/table owners/ACLs **and normalized column ACLs** verified, no shared restart. [Restore evidence](evidence/d25-t02-post-schema-restore.json). Secrets/backups remain ignored, not in source archives.

The file initializer now explicitly accepts reviewed0002/0003/0004; unknown schemas still fail before opening the root and default file enablement remains off. Full regression exposed this necessary compatibility change; upload/delete/root/quota/service logic is unchanged. Eight startup-boundary tests cover both forward compatibility and refusal. Legacy file-journal tests now compare the database revision to the actual migration head; paired schema-clone fixtures copy the source schema's real revision instead of stamping0002. Their source/file assertions are retained; only the additive schema dependency changed.

## Rollback and remaining work

Keep the additive schema when rolling back repository code. Disable admission and drain/fence workers; retain all jobs/tombstones/source/generations for forward repair. V003 refuses downgrade while any job/head exists. V004 refuses silently restoring broad UPDATE privileges. Never drop populated records or delete source/vector data to roll back. Current Qwen selection and exact E5 rollback remain unchanged.

D25-T02 is repository/schema acceptance only. T03 must add actual bounded Qwen embedding and Qdrant generation ownership/upsert/delete/retry/crash/shutdown behavior, explicit admission integration and source revalidation. D25 stays IN PROGRESS until real incremental-index lifecycle acceptance; D26 retrieval remains later work. Test outcomes and source hashes are recorded in dev_log and the retained acceptance report after verification.

## Observed acceptance — 2026-10-19

**Purpose:** Link measured repository acceptance to retained evidence and remaining implementation gates.

[Acceptance report](evidence/d25-t02-journal-acceptance.json):44 new cases (14 unit,22 real PostgreSQL,8 startup compatibility), focused36 PASS/2.56s, related111 PASS/16.85s and final full **914 PASS/120.13s,0 SKIP**. [Post-audit](evidence/d25-t02-post-audit.json): schema0004, no retained test jobs/heads/files/probes, quota `(0,0,0)`, Qdrant collection count0, immutable column restrictions effective and old owners/ACLs unchanged. No D25 vector operation was performed. T02 PASS for this local scope; T03 actual worker/vector lifecycle is NEXT, D25 remains IN PROGRESS.

## D25 final local lifecycle — 2026-10-19

**Purpose:** Record the accepted T03 integration and supersede earlier open-worker status without rewriting historical results.

T03 now drives the repository through the default-disabled source-held worker and authenticated admission/status. Existing T02 methods are AST-identical to the accepted checkpoint; only `reject`, `terminal_candidates` and `defer` were appended. Repeat terminal scans include cleanup-acknowledged rows, repairing late writes; busy source admission defers without charging a model attempt or extending the deadline. Schema remains0004, immutable manifest grants unchanged. Final979 PASS/0 SKIP; see [operating guide](INCREMENTAL_INGESTION.md) and [ADR-036](ADR/036-ingestion-worker-and-terminal-sweeps.md). Earlier future-tense T03 statements describe the historical T02 boundary.
