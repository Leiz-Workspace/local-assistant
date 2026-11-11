# D36 source-selected workspace explanations

**Purpose:** Document explicit source selection, existing CORE composition, native citation/freshness guarantees and measured local acceptance.

**Status:** PASS within the local source-selected explanation scope. [ADR-054](../ADR/054-source-cited-workspace-explanations.md), [acceptance](../evidence/d36-explanation-acceptance.json), [source freeze](../evidence/d36-explanation-freeze.json).

Explicitly enable `ASSISTANT_WORKSPACE_EXPLAIN_ENABLED=1` only after the D34 workspace service/config is enabled. Default is off. No production flag or host workspace is enabled/registered by these changes. There is no database requirement, model download, new model profile or automatic source-root discovery. The endpoint reuses local bearer/Origin authentication:

```text
POST /api/v1/workspaces/{owned-workspace-uuid}/explain
```

```json
{
  "question": "Which Catalog method does route_catalog call?",
  "sources": [
    {"path": "catalog.py", "start_line": 1, "end_line": 20},
    {"path": "transport.py", "start_line": 1, "end_line": 20}
  ]
}
```

The application supplies owner/workspace and makes only selected D35 read calls. Select1–3 distinct nonhidden relative files, at most200 lines each, question4096 UTF-8 bytes, streamed strict body16KiB. Existing native file/line/source guards and D35 budgets apply. Total system/user prompt32768 bytes; reject excess rather than truncate. The existing CORE/fast uses temperature0/max768 output tokens; model-only deadline60 seconds with joined owned client/task cancellation. This does not promise instantaneous backend/kernel preemption. No model-selected tools, root, profile, budget or command is accepted. Autonomous exploration/coding evaluation belongs to later gates.

Each nonblank original line receives a server evidence ID. Generated JSON has only status/answer/citations; answer at most4096 bytes, model JSON at most16384 bytes, at most3 citations. Citation proposals contain only evidence ID and exact unique nonempty quote. The server resolves the original relative path, raw-byte SHA256, LF-based line number and Unicode-codepoint quote offsets. Unknown IDs, repeated/ambiguous quotes, invented metadata, malformed/incomplete output fail closed. Missing evidence can produce `insufficient_evidence`; selected blank text returns `no_sources` without generation. Content and generated answers remain untrusted.

During actual D35 final validation, copy private native stat/hash receipts and duplicate at most3 admitted root FDs. D34 admission is released before CORE runs. Root pins prevent inode reuse; no D34 snapshot deadline is extended. After generation and before response headers, fresh short-lived D34 reads must match pinned root identity and source fingerprints/hashes and pass normal native validation. Replaced/changed/deleted sources or roots produce a sanitized error without stale generated content. These sequential fences are not an atomic filesystem transaction or protection from arbitrary same-UID host processes after the authorization point. Response is private/no-store/nosniff. Pins and model/source tasks are joined/closed on cancellation, timeout, parse/fence/send failure, startup rollback and shutdown. Explainer drains before workspace service.

## Observed acceptance

**423 related PASS/3.95s,0 SKIP,exit0**:74 new D36 cases plus349 accepted D35/workspace/auth/API/startup cases. Ruff correctness/import/format passes11 evaluated Python files/74 described functions/classes. Full application collection1923 is **not a fresh1923 full run**; historical D34 full1785 remains separate.

Actual unchanged `qwen3.5-9b-core` on [frozen synthetic sources/cases](../evidence/d36-core-case-freeze.json):2/2 answerable explanations correct with relevant exact native citations,1/1 absent question refused. [Raw synthetic observations](../evidence/d36-core-observations.json) retained. This is a small authored/same-agent synthetic gate, not independent human review or general architecture/coding quality proof. Foreign/invalid/oversized/blank cases verify zero inference separately with a controlled port. Controlled clocks, shortened timeout, model output and transport failure injections are distinguished from real native/TCP/live CORE cases.

Actual source/root/delete/post-generation/pre-header mutation, UTF-8 prompt overflow, exact quote/hash/Unicode oracles, auth/Origin, pin CLOEXEC, cancellation during pin transfer, repeated cancellation, model timeout, cleanup failures, transport failure and dependency-ordered startup rollback pass. [Final readonly audit](../evidence/d36-final-post-audit.json) verifies V006, empty source/memory/quota/vector/probe/worker/lock inventories, original owners/ACLs/narrow grants and protected model/config/dependency/migration hashes. Only prior main/lifecycle composition changes; D34 source fences and D35 contracts/dispatch remain unchanged.

Disable/drain the optional explainer to roll back; no model/source/data migration. D37 will add a bounded diagnosis/plan without modifications or command execution.
