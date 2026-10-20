# D40 approved single-file atomic patches

**Purpose:** Document complete proposal review, native source-version fences and honest one-file commit receipts before durable rollback or general coding-agent release.

**Status:** PASS within the local single-existing-file scope. [ADR-058](ADR/058-approved-single-file-atomic-patch.md), [source freeze](evidence/d40-patch-freeze.json), [related regression](evidence/d40-related-regression.json). [Full regression](evidence/d40-full-regression.json)2172 PASS/1543.21s,0 SKIP,exit0; [final audit](evidence/d40-final-post-audit.json) clean. No production edit feature or host workspace is enabled.

## Scope and review

Separately default-off `ASSISTANT_PATCH_ENABLED=1` requires both existing live workspace and `ASSISTANT_APPROVAL_ENABLED=1` services. No database, migration, Vault, model, Docker or dependency configuration change. D35's five readonly model tools stay unchanged; model output alone cannot approve or apply an edit. All recorded writes are on disposable synthetic owner fixtures.

Only replace one existing eligible nonhidden single-link regular UTF-8 file, at most8192 original/replacement raw bytes, without NUL. Empty replacement is permitted; no-op, create/delete/rename/multiple-file proposals fail. Root/parent/source owner/type/mode/group and metadata gates use accepted D33 capabilities. Reject set-ID, group/world writes, unsupported group preservation and nonempty xattrs/ACLs instead of silently losing metadata. Preserve eligible original UID/GID/mode. No source import, hook, Git or shell command executes.

| Method | Scoped route | Meaning |
|---|---|---|
| POST | `/api/v1/workspaces/{workspace}/patches` | Read-only capture with exactly path, expected_sha256 and complete replacement |
| GET | `/api/v1/workspaces/{workspace}/patches/{proposal}` | Owner-only historical full proposal/diff and authoritative receipt |
| POST | `/api/v1/workspaces/{workspace}/patches/{proposal}/apply` | Exactly approval_id; apply only the already-approved unchanged proposal |

Local bearer/Origin authentication, private/no-store/nosniff responses and strict16KiB streamed JSON. Unknown/foreign owner/workspace status gives the same404 before expiry or pin cleanup. No client owner/root/mode/diff/TTL/model/command/scope overrides. Invalid requests cannot cause a pending proposal to write even a temporary file.

The server captures source bytes/stat/hash, retained root and parent identity, derives source_version and renders a full unified diff with explicit missing-final-LF markers. Review bytes bind proposal UUID, scoped relative path, source_version, original/replacement hashes, mode/group, full new text and diff. All review bytes must fit the existing32768-byte D39 limit; no truncation. The owner obtains the linked approval via the existing full-review CLI and explicitly types `APPROVE <complete-request-uuid>`; approval itself changes no file. Applying accepts only that linked exact owner/workspace/kind/artifact grant, never a changed replacement.

At most16 process-local proposal records/pins,120-second monotonic lifetime and nonqueued one-operation admission. Expiry is checked on authorized access/capacity maintenance; bounded expired idle pins may remain until that check/shutdown. Terminal closed records may retire at capacity. Restart loses grants/proposals; no resume/replay or durable recovery is claimed.

## Native commit and status

Before any temporary write, require explicit approved state, unchanged exact review and live proposal. Hold root/parent/source descriptors and a nonblocking cooperating-writer advisory lock. Revalidate source/root/parent identity, bytes/hash and metadata. Prepare one O_EXCL/no-symlink owned hidden inode in the same admitted parent, write exact bytes, preserve mode/group and fsync it. Recheck source version and prepared bytes/identity, consume approval once, check cancellation/deadline again, then FD-relative same-directory rename and directory fsync. Native stages have a cooperative five-second deadline; uninterruptible kernel I/O is not forcibly preempted.

The rename is the one-file commit point. Receipts remain queryable after the native pin closes or HTTP acknowledgement is lost:

| State | applied | Interpretation |
|---|---|---|
| applied | true | Rename committed and acknowledged directory sync completed |
| applied_durability_uncertain | true | Rename committed; parent fsync failed |
| applied_cleanup_uncertain | true | Rename committed; a later cleanup acknowledgement failed; uncertainties retain earlier states |
| outcome_unknown | null | Lost syscall acknowledgement could not establish whether the expected inode committed |
| failed / expired | no receipt | No commit was acknowledged; inspect error and external source changes before a fresh proposal |

A lost rename acknowledgement is reconciled only against the known prepared inode and recorded separately. Cancellation signals and joins the owned worker before closing any root pin; after commit it does not silently revert or erase the receipt. A consumed grant cannot be reused after any failure or lost response. Response-scoped error handling finishes before sending headers, so a send failure cannot be translated into a new503 after an already started successful response. Read status; never infer rollback from client cancellation. Receipts describe historical action, not a guarantee that later independent writers kept those bytes.

Cleanup only unlinks the acknowledged-owned temporary inode. If another process replaces its name, preserve that unrelated entry and report uncertainty. An unacknowledged temporary identity is never guessed. This is atomic visibility for one file under cooperating-writer/final-fence limits, not a hostile same-UID compare-and-swap or multi-file transaction. Uncooperative mutation after final validation remains outside the guarantee. No abrupt-process-loss/orphan-temp recovery claim before D41 durable journal/checkpoints. D41 must precede general release and supply separately approved rollback.

## Observed verification

**621 related PASS/8.32s,0 SKIP,exit0**, including73 new D40 cases and548 prior cases. Real native replacements cover exact Unicode/CRLF/empty/no-final-LF bytes, hashes, preserved mode/UID/GID, pending/no writes, changed root/parent/source/metadata/link denials and cooperating-writer lock. Controlled failures are injected at real filesystem stage boundaries: file/dir fsync, pre-rename cancellation, lost rename acknowledgement, indeterminate target, prepared content/name replacement and cleanup acknowledgement. Controlled clocks prove exact expiry/deadline, not crash recovery.

Actual Uvicorn/TCP proposal→full CLI review→typed approval→native apply→fresh readonly source results pass. Foreign/unknown/auth/Origin/strict-body/extra-authority/replay/default-off gates, proposal capacity/retirement, native-constructor ownership transfer, cancellation before/after commit, nonqueued admission, lost ASGI response and startup/shutdown dependency order pass. Source code is never executed by these patch tests.12 evaluated Python files/94 described functions/classes pass Ruff correctness/import/format.**2172 full PASS/1543.21s,0 SKIP,exit0** on the same355-file source map.621 related are a subset, not additional unique tests.

The immutable original D38 four successful/two failed repairs remain unchanged. Its live integration test now writes subsequent measurements to private `data/backups/d38-latest-core-observations.json`, so full regression can exercise the harness without replacing/selecting the public first baseline. Cases, model, first observations and score semantics are preserved. Later private measurement is additional regression evidence only.

Full regression uses a frozen355-file map plus protected hashes, durable private redacted log, boot/PID supervision and observed exit status. Actual completion and final SQL/Qdrant/model/config/security audit pass: V006, no data/quota/vector/probe/worker/lock residue, old security and selected models/configs/migrations unchanged.343 unchanged baseline/protected files plus12 evaluated files match. Additional private D38 trial again measured4/6 repairs with the same palindrome/clamp failures; the first report remains hash-identical and authoritative. Disable/drain patch service to roll back feature availability; it does not automatically undo source edits.
