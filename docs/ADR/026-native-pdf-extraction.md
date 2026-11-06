# ADR-026 — Bounded on-demand native PDF extraction

**Purpose:** Specify D18 source authorization, page provenance and parser resource ownership.

**Date:** 2026-10-18
**Status:** Accepted for localhost/one worker: 25 parser/protocol/resource and 8 DB/HTTP/lifecycle cases; full 476 passed in 34.23s, zero skipped. No new dependency or migration.

P1 work depends on D17 owned, namespace-bound ready files and its sandbox. Effort is one extraction milestone with golden text/page fixtures, HTTP/DB/race tests and full regression. Risks are hostile streams, text ordering/font mappings, resource exhaustion and deletion during parsing.

Add authenticated `POST /api/v1/files/{id}/extract` for native PDF text only. Return file UUID, SHA-256, versioned extractor identifier, untrusted-content label and all one-based page records, including blank pages, each with a file/page locator. No client paths, owner override, OCR, model call, indexing or implicit context. Empty native text means `no_native_text`; it is not evidence that the visual page is blank. Reading order follows pypdf plain mode; layout/tables/visual fidelity are not certified.

Compute on demand without persisted extraction/cache or migration. Existing file bytes remain the source of truth; downstream persistence needs its own lifecycle decision. A service admits at most two concurrent extractions without a waiting queue; excess receives 429. This limit is for the existing one-worker scope, not a multiworker deployment guarantee.

Reuse owned download admission (namespace/ready/size/hash), borrow a read-only duplicate of its locked FD and join worker threads before releasing locks on cancellation/shutdown. Recheck integrity and owned ready state after parsing so a concurrent delete cannot return stale extracted data. Delete may hide immediately and waits for the shared reader before physical purge. Do not modify upload state/quota.

Reuse Bubblewrap's credential-free, network-isolated read-only mounts. A separate worker applies 512 MiB RAM, 5/6s CPU, 10s parent wall time, 32 FDs, zero core and 8 MiB regular-file stdout ceiling before importing parsers. Revalidate PDF structures using D17 rules. Native text is limited to 128 KiB UTF-8 per page and 1 MiB per document, with 1000 pages; reject rather than truncate. Parent bounds output reads and validates exact schema, numbering, UTF-8 sizes and installed parser version. Worker exceptions/text never enter responses or audit logs. Audit UUID/count/status only.

Rollback removes the extraction route and drains requests; no schema, file or authentication rollback is needed. D17/D15 contracts remain intact. PASS requires actual golden multi-page, Unicode, blank, invalid/active/encrypted/limit tests, sandbox failure tests, HTTP owner/hash/state/delete/cancellation checks and full Vault-backed regression.
