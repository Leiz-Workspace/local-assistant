# D87 — Current-source full regression protocol

**Purpose:** Define one reproducible complete software run while preserving original evidence and open product gates.

**Status:** Actual complete software suite **5405PASS/0FAIL/0ERROR/0SKIP**, exit0,1821.99seconds. All707frozen source/config/test files unchanged. Product/manual/release gates remain open. [Exact terminal/source/log evidence](evidence/d87-current-full-acceptance.json).

Run `uv run --no-sync python -m scripts.full_regression data/backups/d87-full-first` only after all native benchmark/browser/restore/fault jobs have joined. The new runner records complete current tracked/additive source/config/test hashes, uses fresh private exclusive logs/status, reads the existing app/migrator/Qdrant Vault secrets only into memory, removes inherited Vault/operator feature overrides and enables existing live integration probes. It redacts credential strings/full DB URLs before writing diagnostics. No source changes during the frozen run; documentation outside source roots may be updated.

The command executes all tests, retains first failures/skips and actual terminal counts/duration/exit status, then requires identical complete source inventory/bytes. A missing summary, nonzero exit, failure/error/skip or changed source prevents software acceptance. Previous D67full4495results and all failed D70reviewers stay historical/immutable; this is a new current-source run, not a replacement benchmark, model choice or reviewer retry.

Eight runner controls verify environment cleanup/live flags/redaction/private metadata/source-change refusal and complete count parsing including singular pytest errors. D87preflight also fixed a numerical telemetry-clock edge: finite extreme/huge integer values could overflow latency bookkeeping. The optional D83wrapper now treats that timing as unavailable while preserving the valid original completion; two regression controls added. Original D83measurements/source hashes remain historical receipts, not rewritten.

Even an all-PASS software run does not close actual D70listening/D74product/model/license/no-speech/D14scorecard/D81quote-format/manual/release gates. D88clean-install and D89manual-review preparation may proceed independently without editing frozen source. Do not tag or deploy v1.0 merely because pytest completes.

## Qualified post-suite audit

Initial strict all-table fingerprint check FAILED; preserve that log. A new uniquely owned restore probe compared the retained D84pre-suite dump to current original data, then was removed. Only assistant.file_global_usage.updated_at differed; its singleton row count/usage remained1row/0bytes/0files/0activeuploads. All11other tables and normalized owners/ACLs matched exactly. Upload/delete tests legitimately update that operational timestamp. It was neither restored nor hidden; final audit explicitly reports strict_all_row_fingerprints_equal=False and accepts only the independently verified timestamp-only delta. Nine separate auditor controls reject changed usage/owner/extra tables/row counts/security/unknown fields/coerced boolean counters; these are not added to5405.

Final original services/provider limits/ports/health, database0006/security/privileges/quota, empty Qdrant inventory and zero restore targets verified. Original CORE PID37256/start63900/samecommand/context retained and literal text recovery PASS; current RAM/VRAM point samples remain separately labeled. Original660other source files/917protected files/176inputs/originalD70pending labels unchanged; the sole old-source exception is ADR121stateless chat. No reviewer model trial/replacement/default/provider/release or actual auditory judgment is inferred. [Qualified audit](evidence/d87-post-full-readonly-audit.json).
