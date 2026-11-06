# ADR-041 — Isolated HTTP reranker trial before adoption

**Purpose:** Define a test-only composition for measuring real source/query/ranking/delivery and bounded concurrent CORE costs without adopting or changing runtime routing.

**Date:** 2026-10-19
**Status:** Evaluation implementation authorized by the owner's instruction to continue all independent work; production integration/adoption and independent human quality remain pending.

## Context and scope

D27-T02 and request-probe measurements do not cover a complete authenticated HTTP retrieval request or service contention. The owner volunteered for relevance review, but no completed labels were supplied. Repeated continuation authorizes independent measurement and a reviewable implementation; it does not supply human judgments or approve model replacement. Keep D27 open and do not advance D28.

P1; dependencies accepted D26 source/HTTP path, existing approved Qwen embedding and original pinned Qwen reranker artifacts/runtime, owned disposable acceptance fixtures. Effort one evaluation milestone. Risks: source/generation changes during ranking, foreign candidate delivery, CPU/model overlap, joined cancellation, pair overflow, misleading small-sample latency and load interpretation.

## Decision

Add evaluation-only code under scripts and tests. A trial service wraps an existing D26 RetrievalService for explicitly constructed test instances only. Existing application source, startup, routes, flags, configuration and deployments remain byte-identical. Existing authenticated route/response is exercised by test-only app-state injection and immediately restored. No runtime entrypoint imports this trial and no adoption/enablement setting is added.

Request up to ten current, owner-scoped, source-rehydrated dense candidates; rank only those source bytes using the exact accepted CPU BF16 batch4 model/runtime/prompt and complete512-token cap. Preserve original dense scores and identity/provenance; candidate scores are untrusted ranking signals and never calibrated confidence. Return only requested top-k after ranking. Keep all candidate readers and existing response-lifetime admission until actual response delivery; validate source/SQL generation immediately before ranking and again after model delay and before headers. Every candidate must appear exactly once; refuse malformed/nonfinite/foreign/missing scores and overflow, with no silent dense fallback.

Use the existing actual ingestion encoder admission lock during ranking so query encoding/indexing cannot overlap the ranking child within this test service. Require nonqueued admission, bounded child CPU/RAM/wall and secret-free offline environment. Reuse exact parent supervision; shield process creation and kill/join the owned process group before releasing model admission, including launch-gap cancellation. No model download, persistent worker, database grant/schema or vector-space/index change.

Measure the existing route with real approved query encoding, SQL/Qdrant/source rehydration, actual candidate inference, final response fence and serialization. In-process ASGI HTTP is distinguished explicitly from TCP/network/production latency. Retain actual first/repeated request samples and child RAM/CPU measurements; do not sum old timings into an E2E claim. A bounded local CORE traffic drill has a separately frozen maximum duration/request/token budget before execution. It is not sustained production-load certification or proof of persistent encoder/reranker co-resident memory. Relevance on new human-review data is not inferred.

## Migration, rollback and remaining decisions

There is no production migration or enablement: test-only app-state composition is restored, owned temporary source/vector fixtures are cleaned and model workers joined. Existing embedding fingerprint, point/source/generation/owner identity and selected models remain unchanged. Optional future production integration still requires owner adoption, complete quality/resource review and a separate implementation ADR. Its disable/drain rollback must retain dense ordering without deleting sources/models/collections or reindexing.

Record actual failures, immutable execution input/code identities, focused/full tests and post-audit before accepting the trial. A successful trial closes only its explicitly measured local gates; human quality, owner adoption, TCP/load or any unmeasured deployment requirement remains open.
