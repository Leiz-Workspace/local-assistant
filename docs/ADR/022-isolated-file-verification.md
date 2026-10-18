# ADR-022 — Bounded format verification in a private Linux process

**Purpose:** Define the parser trust boundary and version 1 verification limits before HTTP admission.

**Date:** 2026-10-18 (Asia/Ho_Chi_Minh)
**Status:** Accepted for verifier scope: 62 verifier cases; full 389 passed in 17.53s, zero skipped. HTTP/paired restore remain unaccepted.
**Dependencies:** D16 policy, D17-T01 sealed FD, D17-T02 journal; no extraction/model invocation.

## Decision and dependency review

Run every untrusted format parser in a fresh Bubblewrap namespace, using the existing `/usr/bin/bwrap` (observed version 0.11.1; actual unprivileged namespaces verified). Mount only read-only public system runtime, the trusted Python venv and application source. Clear environment, drop capabilities, isolate network/PID/user/IPC namespaces, make temporary mount read-only, detach session and die with the parent. No host home/data/auth/backups/Vault files are mounted. The sealed payload enters as stdin FD; only trusted suffix/policy parameters enter argv. The worker receives no DB/Vault/API credential or original filename.

Set hard limits before loading parsers: 512 MiB address space, 5 seconds CPU (6 second hard stop), 32 descriptors, zero core dump and 4096-byte file output. Parent wall deadline is 10 seconds. Verdict stdout goes to an anonymous regular file with a 4096-byte worker file-size ceiling; parent reads at most 4097 bytes, avoiding an unbounded captured pipe. Stderr is discarded; parent returns only allowlisted codes/canonical media and logs no parser text. Timeout/crash/missing sandbox/malformed verdict fails closed, with no in-process fallback. Actual timeout tests verify no worker/supervisor remains to hold payload FDs.

P0 priority: hostile format parsing is already a D17 requirement, dependent on sealed bounded bytes and typed ownership. Effort includes parsers, namespace/resource tests and adversarial fixtures. `pypdf>=6,<7` (uv locks 6.21.1) validates PDFs; `defusedxml>=0.7,<1` (0.7.1) rejects DTD/entities; Pillow 12.3.0 was already present. Added only these two Python dependencies via uv; no services or privileged mounts. Bubblewrap is a required host capability, not a new service. Kernel/parser/runtime vulnerabilities remain operational patching risks; this is not a malware or semantic-trust certificate.

## Verification version 1

- UTF-8 TXT/MD/CSV: incremental decoding, no NUL/invalid controls, reject leading active markup/shebang/PDF disguises including split prefixes and long leading whitespace. Text/plain is valid for MD/CSV. Content remains untrusted data.
- PNG/JPEG/WebP: Pillow container verify plus decode, exact format family, one frame, at most 20 million pixels. Animated/multiframe containers are deferred; they are not silently parsed as one image.
- PDF: strict parser, no encryption, 1–1000 pages, bounded indirect traversal (depth 64, 100,000 visited values), decoded streams total at most policy archive bytes, and rejection of JavaScript/automatic actions/embedded rich content. All work additionally has process CPU/RAM/wall bounds; parsing can reject a file before a declared expansion total is fully measured.
- DOCX/XLSX: ordinary single-disk non-ZIP64 EOCD preflight; policy entry/ratio/expanded-byte limits checked against headers and actual bounded decompression/CRC. Reject traversal, ambiguous duplicate/case-fold names, symlinks, encryption, unsupported compression, nested ZIP/OLE containers and macro/ActiveX/embedded-object parts. XML parts are capped at 2 MiB each and parsed with DTD/entity/external access disabled. Required content types, root office relationship and main namespace must match; every relationship remains local and resolves to an existing member. XLSX requires sheet relationships and worksheet/sheetData parts. No archive extraction to disk occurs.

These are conservative V1 parser subsets: ZIP64, encrypted/active PDFs, animated images, oversized XML parts and externally linked Office documents are rejected. Expanding support needs a versioned policy/verifier review and fixtures. Metadata declares verification version 1 only after internal verifier success and durable publication; neither filename/header nor a ZIP signature is evidence by itself.

## Integration and rollback

Call verifier only from a worker thread using the sealed borrowed FD, outside SQL transactions and while the writer/guard remain held. Close borrowed verifier FDs before writer cleanup; do not cancel a thread and concurrently close/reuse its FDs. T04 must join bounded in-flight work on cancellation, maintain DB heartbeat/deadlines, and fence ready after publication. A parser failure moves the journal to purging and retains quota until physical cleanup. Runtime HTTP remains disabled until integration gates pass.

Rollback disables admission and preserves journal/bytes; no new migration is required for these parser modules. Retain existing policy/verification version on historical records. T03 tests do not prove HTTP cancellation, DB/FS recovery or paired restore; D17 remains open.
