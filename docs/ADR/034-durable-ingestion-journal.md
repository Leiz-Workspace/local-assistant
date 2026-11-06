# ADR-034 — Additive durable ingestion journal and generation fencing

**Purpose:** Define D25-T02 PostgreSQL schema, concurrency, rollout and rollback before persistence changes.

**Date:** 2026-10-18
**Status:** Accepted for D25-T02 local repository/schema/startup compatibility after914 PASS/0 SKIP on2026-10-19. D25 remains IN PROGRESS; T03 NEXT.

P1; depends on ADR-033/T01 and approved Qwen selection. Effort one or more repository milestones, then separate T03 embedding/vector worker. Risks are replay resurrection, stale worker publication, cross-owner/root access, generation races, terminal partial-vector leaks and unsafe schema rollback. Preserve existing source/LLM/auth/model/data and use existing PostgreSQL/migrator/Vault identities; no new service or credential.

## Schema and contract

Add V003 with `assistant.ingestion_jobs` and `assistant.ingestion_heads`; do not modify V001/V002 or existing tables. A job stores immutable source owner/namespace/file/hash, model/collection/generation, exact canonical manifest, deterministic UUID point IDs, complete tokenizer counts and replay fingerprint. Store no text/vectors/private parser payload. Head key is owner/namespace/file/model, with desired job, active job and monotonic admission revision. Composite foreign keys bind pointers to the same source/access/model scope. Source FK prevents accidental deletion of a referenced file journal. Runtime gets explicit DML and mutable-column UPDATE only, no TRUNCATE/DDL or immutable plan edits.

Admission takes a bounded global transaction advisory lock, then source row lock, then job/head locks. Ready/owner/root/hash fences run under that lock. Identical replay returns its existing row before capacity checks, without changing the desired head or resurrecting terminal work. New input increments head revision, fences older pending/running jobs as stale and retains the current active generation until replacement passes publication. Bound outstanding pending/running jobs to128 globally and32 per owner/namespace; no disk/CPU work inside transactions. Metadata tombstones are retained; no automatic retention deletion.

Job states: pending/running/ready/failed/stale/tombstone. Claim validates source, desired head, deadline and due time under locks. Five attempts maximum,120-second renewable lease capped by a one-hour absolute deadline, exponential retry2–30 seconds. DB time governs all comparisons. Every lease transition checks fresh token, running state, expiry and absolute deadline; expired/stolen/replayed workers cannot revive or publish. Publication requires exact complete acknowledged point IDs, final source fence and latest desired admission revision, then updates job/head atomically. It is repository bookkeeping, not proof of Qdrant write; T03 must supply actual acknowledged verification.

Replacing a published generation marks the prior job tombstone for durable vector cleanup. Explicit source tombstoning fences all jobs and clears pointers; bounded paginated reconciliation detects source changes/deletion without modifying accepted file code. `active` joins current source ready/hash/root state so deleted sources are hidden even before reconciliation. D26 still needs final source revalidation around delivery. Terminal jobs remain cleanup candidates; an idempotent cleanup acknowledgement is valid only for terminal jobs after a trusted worker's exact-generation deletion acknowledgement. No live vector operations exist in T02.

## Rollout and rollback

Before migration: render/review offline SQL; verify a fresh private backup/restore with the existing operator drill without shared restart; compare existing table row and owner/ACL fingerprints. Require quiet consumers/current V002. Apply only via existing Vault migrator, then verify old table rows/security unchanged except Alembic revision and new objects/grants. Test app-role transactions/races and full regression, without skipping unavailable credentials. New tests clean only their owned heads/jobs/files/counters. Related legacy fixtures must recognize the additive current migration head rather than hardcode V002.

Rollback code leaves additive schema/journal/data in place. Disable admission, drain/fence workers, retain source/generations/leases for forward repair. A downgrade refuses any job/head row, including terminal tombstones. Never drop populated state or remove source/vector data to roll back. The existing E5 selection backup and Qwen selection remain unchanged. T03 worker/upsert/delete/crash acceptance and D25 overall remain open even when repository tests pass.

## Observed rollout correction — before V004

**Purpose:** Record a real privilege-test failure and the forward correction before applying more DDL.

V003 applied after verified backup/restore; original seven-table rows/security were preserved. Actual app-role tests revealed existing migrator default privileges automatically grant table-level UPDATE to the app. Column grants alone therefore do not make immutable fields immutable. Add V004 to explicitly revoke table-level UPDATE on only the two new ingestion tables, then restate mutable-column grants; leave the existing default-privilege policy and old tables unchanged. Preserve applied V003 and its evidence. V004 downgrade refuses privilege broadening; use reviewed forward repair.

Real psycopg tests also found untyped NULL cursors ambiguous; cast the cursor to UUID in both NULL and comparison branches. These failures are not acceptance. Re-run scoped actual PostgreSQL tests and full regression after fixes.

## Startup compatibility correction

**Purpose:** Record the necessary change to an accepted component exposed by full regression.

Initial full regression after V004 produced831 PASS,71 setup errors and4 failures: file-enabled startup still required exactly revision0002. This compatibility guard had been missed during the initial related-file inspection. Extend only the file initializer's allowed revisions to reviewed0002/0003/0004, retain refusal of unknown/missing/older schemas and leave upload/delete/root/quota/service logic unchanged. Add eight startup-boundary tests proving accepted revisions reach root initialization, unreviewed revisions fail before filesystem I/O and disabled files remain inactive. Related journal/HTTP/recovery plus new ingestion tests now111 PASS in16.85s,0 SKIP; a final full rerun is still required before acceptance.

## Observed acceptance — 2026-10-19

**Purpose:** Accept repository/schema scope from actual results while leaving vector-worker acceptance open.

Final full Vault-backed regression **914 PASS in120.13s,0 SKIP**, exit0, actual PostgreSQL/CORE/Qdrant and explicit actual Qwen/tokenizer flags.44 new cases:14 journal unit,22 real PostgreSQL and8 file-startup compatibility. Focused journal36 PASS/2.56s; related111 PASS/16.85s. Post-test audit: revision0004, jobs/heads/files0, global quota `(0,0,0)`, restore probes0, Qdrant collections0, immutable manifest UPDATE denied, mutable state UPDATE allowed, TRUNCATE denied and old schema/table owner/ACL fingerprint unchanged. Protected backup checksums/permissions and pre/post restore verification remain valid.

The transient prior full run was not recoverable after the environment transition. The fresh2026-10-19 run first encountered sealed Vault and unavailable CORE (collection error, not test acceptance); unsealed the already initialized Vault with existing bootstrap and resumed the configured CORE vision profile. No model/configuration/key/policy change or new model download. Final complete run then passed. Sanitized log is private under `data/backups/d25-t02-final-regression.log`.

Ruff checks/format on nine Python files,104 descriptions, protected original migrations/source service/journal/dependencies/D24 evidence, selected Qwen hash, exact E5 rollback, T01 source/lock hashes and unchanged registry verified. [Retained acceptance](../evidence/d25-t02-journal-acceptance.json) binds observed results to source hashes. **T02 PASS local repository/schema; D25 IN PROGRESS; T03 NEXT.** Actual Qwen embedding/upsert/delete/recovery, admission integration and whole-Day acceptance remain open. T03 must validate supported ingestion schema/grants before enabling a worker.
