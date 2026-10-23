# ADR 112 — Bounded voice composition with explicit dependencies

**Purpose:** Define D72's application orchestration and validation boundaries without activating a model, unapproved voice or autonomous recording.

**Date:** 2026-10-23. **Status:** Accepted for implementation and tests under the owner's instruction to continue after D71. Production model selection and real model activation are not granted by this ADR.

## Decision

Add a model-independent application service accepting complete explicitly submitted normalized PCM, authenticated owner identity and trusted injected ASR, text-only CORE and TTS dependencies. Bind each result to owner/source/PCM/text hashes and exact expected model identities. Do not derive authority, tools, profile or endpoints from transcript/model output. Capture and submission are distinct user actions; D71 remains local-only until a reviewed authenticated product route and selected models are configured.

Admit one operation without queuing, enforce30second source/16k mono PCM bounds and finite transcripts/text/output samples, fully buffer each output before publishing, and expose only a complete result. Report per-stage and end-to-end host monotonic times; do not label buffered latency TTFA/streaming. Stop/cancel/timeout/shutdown must join owned work before releasing admission. A dependency that suppresses cancellation or returns late must not publish a successful turn. Do not use a thread cancellation as proof of native-process retirement.

Keep a separate pure VAD span mapping utility: integer half-open spans refer to the original audio clock; gaps are represented explicitly, never converted into invented continuous source timestamps. There is no enabled VAD default. The existing AUDIO-VAD-ASR-001 held-out comparison remains a prerequisite to enabling gating; application tests and existing separate D68/D69 results do not complete that benchmark.

## Priority, dependencies and acceptance

Existing D72/P1; effort one composition/control milestone plus native integration and VAD/ASR evaluation. Depends on validated explicit audio, selected/approved production adapters for actual deployment, cancellation-aware dependencies and the retained native model artifacts for any separately recorded offline evaluation. Risks: cross-owner result substitution, hallucinated no-speech ASR, tool injection via transcript, stale source clock, long buffered inference, retries, resource overlap and unlicensed voices. All remain visible rather than being hidden behind synthetic success.

Implement and test the orchestration now. Keep D72 **IN PROGRESS** until its remaining native/evaluation/model-choice gates are resolved. Deferred D70 listening remains governed by ADR111; this decision does not claim that hearing has occurred or waive unrelated acceptance criteria.

## Existing-candidate offline VAD/ASR comparison

Evaluate both original D68 ASR candidates and original D69 Silero5, without adoption or replacement. Reuse only their retained pinned artifacts/SDKs/unchanged worker source; download nothing. Freeze twenty additional eligible FLEURS utterances per language, excluding every old utterance filename and sentence identity; five authored no-speech signals and two explicitly padded composites complete47inputs for the unchanged VAD worker's forward/reverse protocol. Gold transcripts remain outside every worker mount. The corpus is locally held out, not guaranteed absent from pretraining and not independently word-aligned.

Run the existing VAD worker once, preserving94first observations. Verify forward/reverse spans/probability hashes and original source bindings. Produce two ASR variants: complete original audio and exact concatenated VAD spans. For nonempty gated inputs shorter than one second, record exact trailing zeros required by the unchanged ASR worker minimum; no full-audio gain repair or resynthesis. Empty gating explicitly skips ASR and produces an empty downstream transcript. Retain original spans/gaps separately; do not claim concatenated timestamps are original source timestamps or that coarse references prove word-boundary preservation.

Run both original ASR workers sequentially, one first prediction per admitted variant, no retry/tuning. Existing caps stay3GiB/180s for VAD and8GiB/900s wall/1200CPU seconds for ASR; all remain below the owner's12GiB ceiling, with14GiB sampled host preflight before each worker and original CORE loaded. Report per-language raw WER/CER, no-speech outputs, retained samples/padding, latency, worker RSS and ordinary CORE recovery. Strict coverage/source checks do not imply that gating improves accuracy or passes production acceptance. Record negative results and keep gating disabled unless its separate selection gates are satisfied.

## Compatibility and rollback

New source/tests only; existing production/API/D71 behavior and all models/configurations/databases unchanged. No fallback, model factory, new weight download, resource increase or persistent audio store. Retire the new service and join its active operation on rollback; retain first tests/benchmark failures. Deployment stays off.
