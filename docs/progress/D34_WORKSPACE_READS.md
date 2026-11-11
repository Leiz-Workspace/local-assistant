# D34 bounded authenticated workspace reads

**Purpose:** Document explicit local workspace setup, read-only endpoints, source provenance and tested limitations.

[ADR-052](../ADR/052-bounded-authenticated-workspace-reads.md) composes the D33 Linux scope guard with the existing local bearer/Origin policy. The feature defaults off. No actual host workspace is registered by this change, and no model/git/shell/hooks/config/source instruction runs.

## Operator configuration

Enable only an explicitly reviewed root through `ASSISTANT_WORKSPACE_ENABLED=1` and an absolute `ASSISTANT_WORKSPACE_CONFIG_FILE`. The JSON must be owner0600, single-link, regular, at most32768 bytes, without symlink ancestors or duplicate keys:

```json
{
  "description": "Explicit local source workspaces.",
  "workspaces": [
    {
      "owner_id": "<existing-authenticated-owner-uuid>",
      "workspace_id": "<operator-created-workspace-uuid>",
      "root": "<explicit-absolute-source-root>",
      "name": "Project source"
    }
  ]
}
```

This is a schema illustration; placeholders are not valid runtime UUIDs/roots. At most8 roots, no cwd/home/environment expansion or automatic parent discovery. Startup verifies configured roots and fails safely if invalid. Catalog reload requires restart/drain. An allowlisted root authorizes nonhidden content under that path; hidden exclusion is not a classifier for every possible secret. Choose intended source roots rather than a broad home/server filesystem. No production config, database or Vault mutation is required by these tests.

## Endpoints

All paths are relative to an exact owner-authorized workspace UUID. Workspace POST streams are capped at16KiB before JSON parsing, independently of Content-Length. Strict JSON object parsing also rejects duplicate/nonfinite/deep/invalid-Unicode input before framework error serialization. Client ownership, root, regex, model, command and budget overrides are forbidden.

| Method and suffix under `/api/v1/workspaces/{workspace_id}` | JSON body | Result |
|---|---|---|
| GET root | None | Display metadata and safe git-marker classification |
| POST `/inventory` | `{"directory":null}` | Admitted regular-file paths and sizes |
| POST `/read` | `{"path":"src/main.py","start_line":1,"end_line":100}` | Exact source lines and raw-file hash |
| POST `/search` | `{"query":"literal text","directory":null}` | Exact case-sensitive nonoverlapping literal matches |
| POST `/symbols` | `{"directory":null}` | Lexical Python `def`/`class` hints with original line/hash |

Successful results are private/no-store/nosniff JSON; source text is `untrusted`. Read/search/hints attach relative file path, raw-byte SHA256, LF-based1-indexed line number and exact line text. CR is removed only as part of CRLF; a final literal CR remains. Search columns use Unicode code points, not bytes/UTF-16. Hints are textual candidates and can match a definition-like line inside a string/comment; they are not semantic AST/language-server resolution. Only `.py` files are read for hints.

## Bounds and freshness

Each request admits one nonqueued service operation. Limits:1000 listed names,256 regular files,16 directory levels,256KiB/file,4MiB initial text reads,100 matches/hints,200 read lines,8192 UTF-8 bytes/line and512KiB serialized reply. Final text validation repeats at most the admitted source reads under the same per-file bounds. The5-second cooperative deadline covers source construction and final validation; it does not preempt an uninterruptible filesystem/kernel operation. Cancellation signals the owned worker and joins it before closing source descriptors; repeated cancellation and completed-worker transfer races have explicit tests.

Hidden, unsafe and nontext/non-Python omissions have separate counters. Hidden entries are filtered before open; unsafe links/mounts/nonregular entries never become results. Nontext files are omitted only by text scans and fail direct read. Exceeded count/byte/depth/result/line/deadline bounds reject the complete request; no silent partial matching result is delivered.

Snapshots pin the admitted root through response delivery. Immediately before headers, re-open sources through the kernel guard and compare inode/stat/hash; compare discovery marker and root identity. Changed/replaced/deleted sources or roots fail closed without returning stale source text. Mutations ordered after this final authorization point are not an atomic multi-file transaction or a guarantee that absent matches remain absent forever. The D33 admission-time/host-process limitations remain applicable.

## Verification status

**D34 PASS (defined local read-only scope).** Actual full application regression:1785 PASS/1509.95s,0 SKIP,exit0, including101 new D34 cases;164 workspace-focused PASS/1.10s is a subset checkpoint. All301 evaluated files/protected hashes match. Final readonly V006/data/quota/vector/worker/ACL audit is clean. [Acceptance](../evidence/d34-workspace-acceptance.json), [source freeze](../evidence/d34-full-regression-freeze.json), [post-audit](../evidence/d34-final-post-audit.json). D35 tool dispatch is next. The interruption/recovery notes below describe earlier attempts, not the completed accepted run.


## Pre-full strict JSON correction

An isolated actual HTTP probe found `NaN` produced ValueError and an overlong surrogate input produced UnicodeEncodeError inside framework error serialization. They are real observed failures, not rejected4xx acceptance. The first full run was intentionally interrupted with normal fixture teardown after414.48s/exit2/no completed tests; its log and v1 source freeze remain retained. Add a bounded strict JSON guard to only the new router; original source/auth/scope oracles remain unchanged. Actual malformed-body cases must return sanitized422 without root access. Final full rerun/audit remain pending.


## Interrupted-process recovery

A later corrected full attempt retains159 completed PASS but no final exit, and the host subsequently restarted. The exact loss cause/time is not established; this partial cannot be used as a completed full run. All301 evaluated source files match. Existing Vault/CORE were recovered without rotation/model/config changes; DB inventories are empty and exactly one acknowledged-owned empty vector probe was verified/removed. The next full1785 attempt runs on the same frozen code with durable PID/boot-aware progress and observed final exit metadata. See [partial evidence](../evidence/d34-reboot-interrupted-full.json) and [scoped cleanup](../evidence/d34-reboot-empty-probe-cleanup.json). D34 acceptance/audit are still pending.

## Completed exact-source rerun

The fresh boot-aware full run finished on2026-10-20 at01:37:42 UTC with observed exit0 and1785 PASS. Runner elapsed1510.60s; pytest1509.95s. Final audit then verified all301 frozen files, protected model/config/migration bytes, old owners/ACLs, no live model worker or advisory lock, V006 and empty source/memory/quota/vector/probe inventories. No host workspace or production feature enabled. Earlier interrupted attempts are retained unchanged and are not included in the PASS total.
