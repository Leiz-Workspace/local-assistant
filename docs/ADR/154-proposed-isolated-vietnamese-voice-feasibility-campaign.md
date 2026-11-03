# ADR 154 — Proposed isolated Vietnamese voice feasibility campaign

**Purpose:** Propose a bounded comparison for the owner's Vietnamese/female/Northern voice requirement and four-second response target without replacing agreed models or changing passing production components.

**Date:** 2026-11-03. **Status:** OWNER APPROVED / IMPLEMENTED / PARTIALLY EXECUTED / WORKFLOW STOPPED. The owner explicitly approved this bounded campaign with “Duyệt”. Preparation, two qualification calls and24 standalone outputs completed; six workflow slots are software-invalid and42 unattempted. [Approval receipt](../evidence/d74-adr154-owner-approval-20261103.json), [actual result](../D74_VI_VOICE_CAMPAIGN_RESULT.md). Original proposal hashes remain in the approval receipt; model selection/deployment is not approved. [Survey](../D74_VI_VOICE_CANDIDATE_SURVEY.md), [protocol](../D74_VI_VOICE_BENCHMARK_PROTOCOL.md).

## Context

D70 owner listening covers24original outputs; the existing VI configurations do not satisfy the owner's voice preference. The owner requests Vietnamese first, female Northern voice, English retained and customizable languages pending a later version. The maximum wait is4seconds from explicit submission to first audible meaningful answer; it is not a TTS-only budget, p95 target or technical timeout.

Existing D72 prediction records expose a wider bottleneck: Qwen ASR alone exceeds4seconds on17of20VI utterances; Whisper exceeds it on0of20but has worse VI WER. These are recomputed existing observations, not a new comparison. The present VoicePipeline fully buffers complete output and existing evaluation workers load models for a run; first physical speaker audibility has not been measured. Changing TTS alone cannot establish the product target.

## Proposed decision, subject to owner approval

Study exactly one additional TTS candidate: **pnnbao-ump/VieNeu-TTS-v3-Turbo**, CPU/ONNX FP32, model revision `61b85e3d937fbbacb387714180e8182823512523`, original SDK source `pnnbao97/VieNeu-TTS` commit `04044e1b8f822f946bafb2c88b716459f4164152`. Study Trúc Ly and Ngọc Huyền as two metadata-labelled Northern female presets. Fix Trúc Ly as the workflow variant before predictions; do not choose the faster/better voice after observing results.

Compare with the retained original Piper VI voice, not an invented improved baseline. Keep both originally nominated ASR candidates in separate declared lanes; do not switch the product default to Whisper to obtain a faster score. CORE remains the existing model/32K configuration/Fast512token contract. No new ASR, CORE, GPU backend, quantization variant or alternative candidate is included.

The [proposed16-artifact allowlist](../evidence/d74-vi-turbo-proposed-artifacts-20261103.json) totals **608,816,450bytes** before the SDK environment. It includes FP32 ONNX/external data/heads/config/tokenizer, mandatory MOSS ONNX codec revision `ceff0d0749bfb3fa2d61149794ec6feef0d1e1ae`, the denoiser eagerly loaded by the inspected constructor, and the one SDK Turbo preset-vector asset. The encoder is fetched by that original constructor bundle even though no voice cloning is proposed. These assets are additional neural/voice artifacts requiring approval, not harmless configuration-only downloads.

## Conditional campaign scope

One explicit approval may cover all three phases below, with no repeated approval between compliant phases. Approval does not permit automatic retries, model/backend changes, relaxed caps, production selection or release. First implement, test and freeze the operator, exact package lock/hashes, source/assets, corpus and execution inputs; **the present documents are not an executable runner or a test PASS**. If those preconditions cannot be met, stop before model execution.

1. **Preparation:** isolated owned root capped8GiB including SDK/cache/payload/results. Use `uv`, a separately locked environment and only original needed upstream source plus the one approved Turbo voice asset. Audit dependency contents; reject undeclared neural assets. Do not run upstream installers, Docker, demos, remote code or inference endpoints. Validate every file size, LFS SHA256 or Gitblob pin before offline use. Preserve an exclusive download receipt; no implicit “latest” revision or additional model fetch.
2. **Qualification and TTS comparison:** credential-free/offline/no-GPU worker, CPU2threads/affinity0,1, AS8GiB and sampled RSS2GiB ceiling, MemAvailable≥14GiB before each new model load, wall≤600seconds per worker. Two declared qualification calls maximum; only successful import/load/integrity/native-output/cleanup permits24scored TTS calls. Eight fixed new texts × original Piper VI/Trúc Ly/Ngọc Huyền. Retain all failures and outputs; user listening later determines preference, accent and naturalness.
3. **Workflow comparison:** only if software/native integrity/resource checks pass, compare2ASR ×2fixed TTS ×2load states ×6retained sources =48turn slots. Fresh-process and resident-model lanes are explicit, with no cached answer/audio. Existing ASR math/settings/caps stay unchanged. A new research-only lifecycle adapter may retain an ASR/TTS process between warm turns; the passed VoicePipeline/API/recorder must remain untouched. Native-model phase total wall≤3600seconds; per-turn technical deadline remains180seconds. Maximum50CORE calls including2recovery checks,48ASR calls and74TTS calls including qualification/standalone/workflow. No automatic rerun of failed or slow cases.

For overlapping resident research workers, use a conservative sampled sum-RSS8GiB ceiling in addition to per-worker guards, and retain the14GiB preflight floor. These are proposed stop conditions, not predictions of required memory or reserved RAM. Stop and join owned work on breach, timeout, invalid provenance or changed baseline; never relax limits or reclaim shared services automatically.

## Architectural boundaries

The resident-worker lifecycle is an experimental architecture change isolated outside registered application routes. It requires bounded admission, same owner/source/model fences, complete-output publication and joined cancellation/shutdown. Do not modify the passing composition to publish incomplete speech for a favorable first-audio score. No LLM streaming, TTS streaming or GPU variant is implicitly approved here; those remain possible separate proposals if needed.

A future temporary loopback measurement surface may serve only retained synthetic/public benchmark packets and returned audio, with no microphone, upload from the owner, persisted session or deployment. It must be implemented/tested before use, keep authentication/origin/body bounds and close after the campaign. Browser digital-render time is a labelled proxy; it must not be represented as physically audible speaker timing. Actual first-audible acceptance needs validated output-device/acoustic timing or separately reviewed measurement evidence. Approval of this campaign does not waive that requirement.

## Quality, acceptance and licensing

Freeze the [packet](../evidence/d74-vi-voice-proposed-packet-20261103.json) before predictions. Fixed reused D72 sources are timing/compatibility data, not a new independent ASR holdout. Include negatives without forcing ground-truth labels into model inputs; preserve hallucinations and failed refusals. Do not enable VAD concatenation, normalize model transcripts, truncate answers or hide overruns. Wrong/failed/missing/late outcomes remain in their denominators.

Separate gates: software/provenance/isolation, VI intelligibility/pronunciation, owner-approved female/Northern/natural voice, first-audible≤4seconds on the declared workload, no-speech behavior and deployment rights. A successful TTS sample, warm average or digital-render proxy cannot close D74. Cold measurements stay reported; a warm-only product readiness policy would require its own explicit scope decision, not deletion of cold failures.

Publisher cards state Apache-2.0 for Turbo/codec and make explicit preset-asset rights assertions; preserve those statements and component notices, not an independently issued legal clearance. SDK, preset, codec, phonemizer and distribution obligations remain separately reviewed before activation. No owner recording, external voice cloning or audio upload is included.

## Priority, effort, migration and rollback

P1 for VOICE-VI-NORTH-FEMALE-001 and VOICE-LATENCY-AC-001. Dependencies: owner candidate/campaign approval, pinned artifacts and dependency lock, tested/frozen operator, existing protected originals, adequate resources and actual listening/timing evidence. Effort: one preparation/implementation/qualification milestone plus one bounded comparison/audit milestone; engineering time remains unestimated until implementation is reviewed. Risks: wrong voice metadata versus SDK assets, precision/phonemizer differences, hidden downloads/retries, ASR accuracy-speed tradeoff, CPU contention, cached timing and mistaking renderer activity for physical sound.

**No production migration now.** Trial stores results separately, retains original model/config/audio/hash snapshots and admits no product traffic. A future promotion would need explicit model/voice selection, exact performance/quality/resource/rights evidence, an owner-approved integration design and rollback. Rollback here stops admission, joins only owned workers/CORE child/test UI, restores the captured native/container baseline and retains failed results. Never stop a pre-existing shared service or delete original models/data. D60 remains owner-deferred; D74 product and D90 release remain OPEN.

## Execution disposition — 2026-11-03

The approved campaign consumed26 TTS/6 ASR/6 CORE attempts, without retry. The new research caller misread Fast gateway metadata (`preset_selected` versus `preset`); six otherwise complete CORE responses were rejected before TTS. This is a caller failure, not evidence that CORE or the voice candidate failed. The first caller and all outputs/freezes remain preserved. The corrected caller, fatal metadata handling and cancellation cleanup have161 scoped software tests PASS; no corrected native inference has run. The first interrupted cleanup receipt remains unchanged; a separate inspection verifies the exact original native0/container baseline restored. [Result and limitations](../D74_VI_VOICE_CAMPAIGN_RESULT.md).

This approval is not reused for a retry after the software stop. [ADR-155](155-proposed-workflow-recovery-after-caller-metadata-failure.md) proposes one replacement workflow-only campaign with the same assets/caps and a new explicit approval gate. New owner listening/physical timing/product selection remain open.
