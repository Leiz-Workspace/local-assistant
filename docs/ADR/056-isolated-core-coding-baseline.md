# ADR-056: Isolated existing-CORE deterministic coding baseline

**Purpose:** Define D38 case-wise coding evidence without granting production patch/command authority or adopting a specialist model.

**Date:** 2026-10-20 (Asia/Ho_Chi_Minh)

**Status:** Implemented evaluation gate after D37 `3786f06`:589 related PASS/16.84s plus separate1 actual CORE evaluation PASS/9.08s,0 SKIP,exit0, clean audit. All6 tasks measured; **4 repairs PASS,2 FAIL** retained. [Acceptance](../evidence/d38-baseline-acceptance.json). Not agent MVP/general coding-quality acceptance; no new full2028 claim.

## Priority, dependencies and risks

P1 D38 baseline after D33–D37; one evaluation harness milestone plus native isolation/model/regression evidence. Existing D11 coding benchmark already uses a pinned Python Docker sandbox, and accepted document processors use bubblewrap. The pinned Docker image is present; no pull/download is required or authorized. Prefer the existing bubblewrap mechanism with only trusted runtime/worker mounts to avoid Docker daemon/container cleanup races. A native probe confirms explicit sandbox UID65534 works. Risks: executing generated code on host, unsafe git configuration/hooks, false PASS markers, unbounded subprocess output, timeout/cancellation leaving descendants, leakage of credentials/host sources and overstating tiny synthetic results.

## Decision

Build an evaluation-only harness, not an application tool endpoint. Freeze six small source-repair tasks, concrete hidden input/expected-output oracles and quality/cleanup criteria before actual inference. Each task owns a private generated workspace/git fixture. Only trusted fixed git commands initialize/checkpoint/diff it with system/global config, hooks, filters, signing and interactive prompts disabled. Root/paths/commands never come from model output. Actual D35 read/search provide bounded source context; unchanged CORE/fast returns a strict JSON full-file code proposal only. The host may AST-parse bounded text and save it to the exact owned fixture path but must never import/exec/eval it. Preserve real project source, existing repositories, models, data and infrastructure.

Evaluate original and proposed functions only in a credential-free bubblewrap mount/user/PID/network namespace: UID/GID65534, no capabilities, readonly trusted runtime and worker, no host workspace/home/config/Vault/socket mounts, no network and no writable filesystem. Pass candidate source and JSON inputs over stdin only. Apply hard CPU/memory/file-size/open-FD/core/process limits before compiling candidate code. Bound aggregate stdout/stderr, wall time and request bytes in the host supervisor, and join timeout/cancel/descendant teardown before return. No weaker fallback. This is a fixed function evaluator, not general D42 application command execution.

Expected outputs remain in the trusted host parent and are not included in the worker request. Parse exact bounded worker JSON and compare each returned value against its authored expected JSON; printed TESTS_PASSED/exit0 alone cannot pass a case. Candidate code could introspect its isolated worker or hardcode finite inputs, so this is finite functional evidence, not a proof of honest arbitrary-code testing or host security beyond tested isolation. Reject malformed/oversized code/output; require module/function/class descriptions. Report actual before/after per-case outcomes, model completion/latency and resource policy separately from unmeasured throughput/RAM/VRAM/generalization. Preserve all failures; do not edit goldens to inflate scores.

Acceptance of an evaluation means all frozen cases were actually attempted and measured with valid isolation/cleanup and retained outcomes, including model task failures. It does not require inventing perfect model accuracy or selecting a replacement. Any specialist proposal remains conditional MODEL-EVAL-007 and needs benchmark/resources/migration/rollback plus explicit owner approval. No model download/switch is implied. Production approval/events, general patch editing/git rollback, command execution and issue-to-fix integration remain D39–D46.

## Verification and rollback

Test strict code envelope/AST contracts, actual D35 source/owner scope, fixed isolated git fixture diff/checkpoint and unchanged project bytes. Native sandbox cases must verify UID/env/host-path/network/write fences, bounded output, CPU/memory/time failures, printed-marker rejection, cancellation/join and no surviving worker/namespace. Run original CORE on every frozen task and retain successful and failed repairs. Re-run relevant D35–D37/parser/namespace guards and readonly data/config audit. Removing the unused evaluation modules/artifacts rolls back without source/model/data migration. D38 stays IN PROGRESS until actual evaluation and cleanup evidence exist.
