# ADR-054: Source-cited workspace explanations with existing CORE

**Purpose:** Define D36 source selection, model composition, exact line citations and post-generation source authorization.

**Date:** 2026-10-20 (Asia/Ho_Chi_Minh)

**Status:** Accepted/implemented after D35 `8ce51d3`:423 related PASS/3.95s,0 SKIP,exit0,74 new cases and clean final audit. Actual original CORE2/2 answerable citations and1/1 absent refusal; [acceptance](../evidence/d36-explanation-acceptance.json). No fresh1923 full claim.

## Priority, dependencies and effects

P1 after D33–D35; one explanation milestone plus actual CORE/native/auth/cancellation evidence. Main risks are fabricated line citations, source instructions, sources changing while CORE runs, deadline/descriptor lifetime confusion, and accidentally permitting model-chosen roots/tools. Preserve all agreed models, existing APIs, source data, migrations and infrastructure. No downloads, model replacement, write/command execution or new database records.

## Decision

Add a default-off authenticated local explanation endpoint under an exact workspace UUID. The user explicitly selects1–3 distinct relative source files and bounded line ranges; all source inputs reuse D35 shared read validation. The fixed application supplies owner/workspace, creates and closes a D35 tool run, and executes only the requested read envelopes. D36 is source-bounded explanation, not autonomous repository exploration; the later coding baseline owns autonomous tool-loop evaluation. Expose no tool/run/budget/profile override. Question4096 UTF-8 bytes, prompt32768 bytes, model reply16384 bytes, answer4096 bytes and at most3 exact citations. Reject excess rather than truncate.

Use the existing CORE/fast, temperature0 and at most768 output tokens with a60-second model deadline and joined cancellation. Source text and question are untrusted JSON data, not instructions. Each nonblank original line receives a server-derived evidence ID. Generated output must be strict object JSON with status/answer/citations only. Resolve each supplied evidence ID and exact unique nonempty quote to the authorized original line, relative path, raw hash and Unicode offsets. Reject invented IDs, line/path/hash overrides, malformed/incomplete output and unsupported citation shapes. Mechanical quote validation is not a proof that every generated claim is semantically supported; actual frozen-case correctness is a separate gate.

Do not extend/reset D34 snapshot deadlines across model latency. During each actual D35 source validation, capture private immutable stat/hash receipts and duplicate the admitted root FD with joined ownership transfer. Release the D34 service admission before model generation; retain only these bounded private root pins and source receipts. They are not model-visible authority. After generation and immediately before response headers, rebuild fresh short-lived D34 reads and compare source fingerprints/hashes and pinned root identity before final source validation. Root pins prevent inode reuse from masquerading as the original root. Source/root mutation fails closed. Each read/final-fence deadline remains D34 cooperative5 seconds; model timeout is separate. Sequential multi-file fences are not an atomic filesystem transaction, and hostile same-UID process limits remain unchanged.

Own at most3 root pins per explanation, close/join on every error/cancel/send/shutdown path, and drain explanation service before workspace shutdown. Reuse D34 private response and pre-header fence ownership. Startup is explicit default-off and requires the workspace service; no DB/model process initialization or host registration. Audit only stable IDs/counts/status, never question/source/root/answer text. No model can promote source instructions into tools, commands or another profile.

## Acceptance and rollback

Test actual native line/hash/quote oracles, root/source mutations during model delay and before headers, malformed/invented output, scope/auth/Origin/default-off/limits, independent clock/model injections, cancellation/shutdown/send cleanup and FD ownership races. Run actual original CORE on frozen explanatory/absent cases; retain failures and distinguish controlled model output from real inference. Re-run affected D34/D35/auth/startup tests. Disable/drain the new endpoint to roll back; no source/model/data migration. D37 remains diagnosis without modifications.
