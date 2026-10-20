# ADR-052: Bounded authenticated workspace source snapshots

**Purpose:** Compose accepted D33 capabilities into D34 local authenticated inventory, literal search, source lines and lexical Python definition hints.

**Date:** 2026-10-20 (Asia/Ho_Chi_Minh)

**Status:** Accepted and implemented within the defined local read-only scope:1785 full PASS/1509.95s,0 SKIP,exit0 on2026-10-20; exact301-file freeze and clean final readonly audit. [Acceptance](../evidence/d34-workspace-acceptance.json). Earlier malformed-JSON failures and interrupted attempts remain separate evidence.

## Priority, dependencies and effects

D34 is P1 after D33 `3a3489e`; estimated one implementation milestone plus regression. Reuse existing owner authentication/local-client/Origin policy and read-only openat2 root capabilities. Risks: unbounded directories/files/lines/results, stale/replaced sources, cancellation leaving descriptors or threads active, config/OS error leakage and confusing textual hints with semantic symbols. No model, shell, git/config/hooks, write operation, database, infrastructure or dependency change is proposed.

## Decision

Expose default-off `/api/v1/workspaces/{workspace_id}` discovery and POST inventory/read/search/symbols under existing local bearer authentication. Client cannot select principal, absolute root, model, shell/regex or budgets above server caps. Workspace POST bodies are limited to16KiB while streaming before JSON parsing; Content-Length is not trusted. Parse strict object JSON before framework validation: reject duplicate keys, nonfinite values (including exponent overflow), invalid Unicode and nesting over16 to prevent error-serialization crashes. Operator-only private no-symlink/single-link/owner0600 bounded JSON config supplies at most8 existing explicit owner/root specifications. Load once at startup, drain on shutdown; config changes require restart. No actual host workspace is automatically registered.

All scanning/opening uses D33 directory FDs and kernel scope. Hidden entries are omitted before open. Symlink/hard-link/nonregular/mount entries are omitted with disclosed counters in scans, while direct read rejects them. A missing/replaced source during a snapshot fails closed. No parent traversal, zip/Office parsing, repository instructions or subprocess executes.

Inventory/search/hints visit at most1000 entries/256 files/16 directory levels. Read at most256KiB/file and4MiB total; responses at most512KiB. Literal query at most256 UTF-8 bytes; at most100 matches/hints; read at most200 lines; native lines at most8192 UTF-8 bytes. Any exceeded resource cap rejects the complete request without silently truncating matches/source. Binary/invalid-UTF8 files are counted as omitted in text scans, and rejected on direct read. Filenames remain exact relative paths. Hints are explicitly lexical `def`/`class` line matches, not AST resolution or language-server semantics.

A single nonqueued service admission owns each snapshot and retained root FD through response delivery. Work runs off-loop with an owned cancellation event, checked monotonic5-second cooperative deadline and joined thread completion before descriptor release. This is bounded cooperative local I/O, not a promise to preempt an uninterruptible kernel/filesystem call. No execution sandbox is implied. D35 will separately govern tool dispatch budgets/timeouts.

Every returned file/line carries actual raw-file SHA256 and exact LF-based1-indexed line text; CRLF terminators are excluded only from displayed line text. Match columns are Unicode code points. All source text is untrusted. Inventory retains inode/stat fingerprints; text results additionally retain full-byte hashes. Immediately before response headers, re-open admitted paths under the retained root and compare inode/stat/hash, recheck root and deadline. Close snapshots after joined delivery/error/cancellation. This authorizes a pre-header snapshot; mutation ordered afterward is not an atomic multi-file/filesystem transaction, and an absent-search result is not guaranteed forever.

Return private/no-store/nosniff on successful responses and stable sanitized errors without source/config/OS messages. No source text/path/query appears in audit events; only operation, counts, stable codes and workspace UUID. Authorization always precedes any workspace root read, including discovery.

## Rollback and subsequent work

Disable/drain the workspace feature to restore existing app behavior; no source/database/vector changes or reindex. Preserve D33 classes and all agreed model choices. Related startup/auth/source tests must pass before D34 acceptance. D36 architecture explanations must reference verified snapshots rather than invent source lines; D39–D45 approval/edit/rollback/sandbox/injection gates are still required for writes/execution.
