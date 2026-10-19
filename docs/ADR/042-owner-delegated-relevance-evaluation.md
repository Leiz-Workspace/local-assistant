# ADR-042 — Owner-delegated AI relevance evaluation

**Purpose:** Apply the owner's explicit delegation without inventing human review, rewriting frozen inputs or treating classifier scores as adoption approval.

**Date:** 2026-10-19
**Status:** Evaluation policy amended by explicit owner instruction; paired execution and day acceptance pending actual results.

## Authorization and boundary

The owner first volunteered to review, then explicitly said they were unavailable and instructed the assistant to perform this review and similar tasks autonomously from now on. This supersedes the pending requirement for that owner's manual64-pair review. It does not turn assistant judgments into human-independent evidence and does not authorize replacing an agreed model or changing production routing.

P1; dependencies frozen diagnostic data, existing source-held evaluation trial and exact original models. Effort one evaluation milestone. Risks: same-agent authorship/judgment bias, ambiguous absent-answer semantics, small correlated sample, low statistical power and conflating benchmark acceptance with deployment selection.

## Decision

Retain the human packet, pending template, scorer/plan and assignment as historical artifacts; do not populate a false human attestation or silently modify their schema. Add explicitly assistant-authored/assistant-reviewed artifacts and a separate scoring/execution path that reuses pure metric/source/HTTP helpers while reporting its actual provenance. No independent-human or representative production-quality claim is allowed.

Before inference, review the original8/8 challenge. Query04 asks for an approved quarterly VAT-inclusive total, while doc-d explicitly states the quarterly budget is not approved. Under the existing rule that sources supporting negative answers can be relevant, doc-d supports answering that no approved total is available. Therefore the original challenge has no unambiguous absent-answer case; its predeclared minimum-one-absent coverage gate fails. Retain that pre-execution corpus/coverage finding. Do not mark doc-d irrelevant just to meet the gate.

Create a separately versioned challenge v2 before any new-challenge inference, changing only query04 to ask for the physical backup disk serial number storing generation G-17. No source supplies that identifier or explicitly answers the question. Retain original source bytes, other seven queries and all v1 artifacts. Explicitly freeze v2 input, AI judgments, plan and source/test hashes before actual execution; do not tune them from model scores. Keep original answerable/absent coverage minima and nonregression/group gates. Absent support metrics stay null; ranking alone does not prove calibrated abstention.

Run three actual paired rounds through the isolated owned source/HTTP trial with approved embedding and exact original Qwen reranker runtime. Retain complete raw ranks, source/point/hash/generation bindings and timing. Same-agent judgments remain diagnostic. Review quality and roughly doubled observed request cost honestly; failed gates remain failed. Acceptance may conclude to retain dense ordering and defer integration, because evaluation need not adopt a candidate. Registry nominations remain intact. Any actual model replacement or production routing/adoption still requires the owner's specific approval and reviewed migration/rollback.

## Consequences

No remaining mandatory manual-label action is assigned to the owner. Later roadmaps/dev logs must reflect owner-delegated AI review, not keep requesting unavailable human labels or claim they were supplied. D27 can close only after its amended local evaluation criteria, explicit bounded limitations, tested evidence and a concrete evaluation decision are complete. D28 must wait for that checkpoint. Production/human-independent quality, persistent-model resources and deployment SLOs remain separate unfulfilled claims; no false PASS is created for them.
