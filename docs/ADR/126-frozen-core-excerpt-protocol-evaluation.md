# ADR 126 — Frozen existing-CORE excerpt protocol evaluation

**Purpose:** Measure D81 format adherence on fresh authored cases before proposing any production prompt integration or model change.

**Date:** 2026-10-24 (Asia/Ho_Chi_Minh). **Status:** EXECUTED / CLOSED; six-case quality FAIL1/6. The owner's continuation instruction authorized this bounded evaluation; its first observations are retained and the protocol is not adopted.

## Decision and assessed scope

Schedule D81-FMT-002, P2 following the verified ADR 125 admission component. Dependency: unchanged established CORE already loaded, existing profile prompt/gateway/budgets and frozen exact-value/excerpt oracles. Effort: one bounded six-case evaluation and evidence review. Risks: Atlas overfitting, leaking expected answers, reporting source grounding as format compliance, discarding raw gateway failures and selecting only successful retries. No model replacement is proposed; inference uses only the existing CORE instance and configuration.

Before inference, freeze six new authored cases (three EN/three VI, each with file/code/web text) and all current application source hashes. The host-only oracles pin requested string values and fact-only quote spans. Only source text, requested fact keys and one fixed per-request format instruction/example enter inference. The existing D80 v1 system template remains byte-identical. Authored sources are not live web fetches or independent human relevance labels.

Exactly one first request per case, sequentially, Fast512/temperature0,20seconds per case,180seconds inference-phase timeout. No auto routing, model load, context/resource-cap changes, repair or retry. A gateway/completion failure stops remaining cases; a completed format failure is retained and the other frozen cases still run. Verify original PID37256/start63900/command before any request and again afterwards. One ordinary literal CORE recovery request follows, with its existing30second timeout. No other model or evaluator runs.

## Retention and acceptance

Fresh exclusive private output directory; durable attempt record before inference. A zero-retry recording transport saves bounded first native request and decoded native-response payload bytes **before** the unchanged gateway validates completion. Retain HTTP status, complete/truncated-body flag and hashes, including non-JSON/error/length outputs. Maximum decoded body64KiB; even publication/read failures must close the response. Keep raw profile/gateway output and separate scores when available. Never overwrite an old attempt or turn missing/incomplete coverage into PASS.

Scores distinguish exact values, unique literal quotes, exact minimal excerpts and guard admission. Acceptance requires all six cases/18excerpts, correct values, guard admission, same original CORE and exact frozen source bytes. Completion of observations alone is not quality PASS; CLI exits2 for complete but failed quality and1 for incomplete coverage. Original D81 score1/3format and3/3grounding, first response and old prompt remain unchanged regardless of this result. This one small authored protocol does not establish general reasoning/injection resistance, real web currentness, semantic correctness on arbitrary sources or product acceptance.

## Validation, effect and rollback

Prepared33new controls within129related PASS/0FAIL/0SKIP/0.55s; Ruff PASS. Tests cover host-oracle separation, six-case composition, first-failure accounting, no retry/overwrite, bounded raw capture, gzip replay, stream/disk cleanup, actual unchanged gateway length rejection and final source-drift refusal. Tests use fixture inference only.

First startup failed before any native request because the new artifact writer incorrectly reused the16KiB MCP canonicalizer for the full712-file manifest. Keep that log/directory unchanged. Correct only the new artifact serializer: strict finite JSON with2MiB artifact cap; request/MCP limits unchanged. Add actual full-manifest and invalid/oversized-artifact regressions. Corrected preflight36new/132related PASS/0FAIL/0SKIP/0.66s/Ruff PASS. The next fresh directory contains the first actual model attempts; this is not a retry of a model response.

No source changes to existing API/gateway/templates, no new dependency/model/provider, no Docker/Vault/database/collection change, no route activation. Rollback stops using the new offline evaluation runner and retains all first artifacts. Actual D70listening0/24 and model/license/device/product/release gates remain open. Any later product prompt integration needs its own scoped evidence review; this ADR cannot approve a model replacement or rewrite original acceptance.

## Actual execution and scope closure

Corrected snapshot440ae44 executed exactly one first attempt for each of the six cases plus one ordinary CORE recovery request. Quality1/6full contracts,18/18literal quotes/16/18minimal excerpts; source712unchanged, same original CORE, all responses retained, zero neural retries. [First report](../progress/D81_FROZEN_EXCERPT_PROTOCOL_EVALUATION.md), [digests](../evidence/d81-fmt002-first-verification.json). The earlier manifest startup failure made zero model requests. This campaign is consumed/closed; no rerun of its failed cases or model replacement is scheduled by this ADR. Further remediation needs its own declared protocol/fresh cases; old failures remain immutable.
