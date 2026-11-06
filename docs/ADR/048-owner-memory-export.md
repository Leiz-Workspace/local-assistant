# ADR-048 — Bounded owner memory export

**Purpose:** Close the explicit D29/D30 owner-export obligation discovered before D30 final regression.

**Date:** 2026-10-19
**Status:** Accepted locally after focused147 PASS/0 SKIP, full1570 PASS/1357.69s,0 SKIP and clean post-audit; see [D30 acceptance](../evidence/d30-memory-acceptance.json).

P1, dependency ADR-044/V005/T02 authenticated controls; effort one small D30 task. Risks are cross-owner disclosure, inconsistent multi-query snapshots, unbounded payload and confusion with source/backups erasure. No new model, schema, grant, dependency or source mutation.

Expose authenticated private GET `/api/v1/memory/export`, including own settings, all retained consent receipts and full records, even while disabled/revoked/expired. Use one read-only repeatable-read PostgreSQL snapshot and parameterized principal filters; a missing settings row yields inert revision0 without creating it. Export is explicit data management, never memory-use authorization. Include format/version, DB observation time and untrusted-content marking. Do not include conversation history, files, operator keys, vectors or deleted records.

Enforce existing1000 owner receipt/record caps with limit1001 overflow refusal and a12MiB UTF-8 JSON response ceiling. Refuse rather than truncate. Fixed attachment filename and private/no-store/nosniff headers; no filename/path or owner selector input. Join the existing owned SQL operation before response construction. The snapshot can precede a concurrent deletion; export already delivered to the owner cannot be recalled. Source deletion, export privacy/injection and purge propagation receive separate D31 tests.

Require pure bounds/JSON serialization and actual PostgreSQL/HTTP owner isolation, disabled access, Unicode and no-mutation tests, then full system regression. Disable/drain the existing feature for rollback; keep all data/migrations/model choices unchanged.

## Measured final acceptance

Final full1570 PASS/1357.69s (22:37),0 SKIP, exit0. Python source matches pre-regression freeze; model/config/dependencies/applied V005 unchanged. Actual owner SQL/CORE/HTTP/TCP, export and retention gates accepted within documented local synthetic scope. Final inventories0 and original owners/ACLs/grants preserved. Earlier failed attempts retained; D31 source deletion/injection/export propagation remains separate.
