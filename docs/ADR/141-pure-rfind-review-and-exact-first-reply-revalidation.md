# ADR 141 - Pure rfind review and exact first-reply revalidation

Purpose: correct a concrete fixture-review false negative without generating another model answer, rewriting candidate code or erasing a failed first score.

Date: 2026-11-02. Status: Accepted for the owner's D46 remediation; no new model/default permissions.

## Evidence and assessment

CE005 completed twelve first generations with11functional passes. Its remaining candidate uses `str.rfind` to locate the final separator, but the existing pure review allows `find` and `rsplit` while excluding `rfind`. The reviewer rejected it before native checks. The original11/12 FAIL, raw replies, original review source and exact application snapshot remain pinned. Semantic correctness of the rejected candidate has not yet been established.

P1, dependency retained first observations and joined intermediate workers. Effort one fixture-vocabulary correction, denial regression controls, exact-input native revalidation and final full/audit. Risks are broadening a method allowance, confusing replay with inference, altered prompts or rewriting a historical score.

## Decision and acceptance

Add only `rfind` to the fixture's pure string-method vocabulary. Preserve complete module/import/logger/API/audit/unknown-name/dynamic-call guards, execution capsules, hidden suites and all typed approvals. No imports, tools, shell, model parameters or production service change. Test that this pure method is admitted while forged imports, dynamic calls, private attributes, API/default/audit changes and trusted-name rebinding remain rejected.

Before review maintenance, pin all72first request/reply/native-wire/measurement files and the original review source in a separate immutable record. Revalidate all twelve exact first replies against the exact same original requests and unchanged cases/oracles through new typed approvals and actual visible/held-out native checks. No network/model call, candidate rewrite, feedback or additional generation is allowed. Reject changed first bytes, altered request messages/options, a second response delivery or incomplete input binding. Capture consumption of an old reply separately from new inference; legacy harness counters must not be presented as fresh model requests.

Require12/12functional native passes under this explicit corrected review policy, no cleanup uncertainty and complete retained request/candidate provenance. Any failure remains a failure. The original11/12study is never relabeled; the correction's result is an exact-first-output revalidation, not a new independent model benchmark. Run the complete final source suite with original resource guards and descendant-only scheduling under ADR140, then read-only preservation checks. D60's successful earlier frozen component/native/visual observation is retained without another provider or model call.

## Rollback

Remove the single vocabulary entry and omit the revalidation runner. Original results and first source snapshots remain auditable; defaults, agreed models, source permissions, data, services and release status stay unchanged.
