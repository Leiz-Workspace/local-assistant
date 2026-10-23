# ADR 113 — Native offline voice wiring matrix

**Purpose:** Validate the new application composition with actual retained original ASR/CORE/TTS workers while keeping all production model choices unchanged.

**Date:** 2026-10-23. **Status:** Accepted for bounded existing-candidate offline evaluation as part of D72; no production activation/model-selection approval.

## Decision

Evaluate six predeclared compatible paths, sequentially: each of the two original ASR candidates with Qwen TTS English, Piper English and Piper Vietnamese. Existing Qwen explicit-Vietnamese refusal remains unsupported; do not relabel Auto support or introduce a replacement model. Use the first retained new held-out speech source in each language, with explicit recorded PCM16 conversion before the existing native normalizer. This is a wiring sample, not a new representative quality benchmark or user recording.

Every path invokes a real reference-free ASR worker, existing text-only CORE via its existing Fast preset, and one first native TTS synthesis of the actual CORE answer. Use unchanged worker settings/artifact pins and validate complete native audio/hash/EOS. The original TTS worker's160UTF8-byte text limit stays enforced; an answer that exceeds it fails honestly rather than being truncated or retried. Produce a separate explicitly quantized/resampled16k playback PCM; retain native float waveform and all first failures. A failed path does not prevent evaluating other distinct predeclared paths, and is never rerun for a better result.

No model provisioning, new package, automatic selection, production endpoint or microphone acquisition. SDK/artifact checks precede execution. Keep original CORE loaded,14GiB sampled host preflight before each model worker, existing8GiB ASR/12GiB TTS virtual caps, CPU2 and offline namespaces. Single-ASR wall120seconds, TTS wall180seconds and application deadline180seconds. Cancellation joins bounded native work before admission retires; a thread cancellation is not proof that its process exited. Retain stdout/stderr/process receipts and literal CORE recovery.

## Acceptance, risk and rollback

D72/P1 depends on tested source/owner binding and successful complete application turns, the VAD/ASR comparison and explicit selection gates before production. This matrix provides actual stage/resource/buffer evidence only; unsupported language, answer size, EOS, latency or worker failure remain failed observations. It cannot close deferred D70 listening, establish naturalness or approve voices/licenses.

Risk: model errors cascade; a long answer exceeds native synthesis limits; CPU load raises buffered latency; playback conversion differs from the preserved native source. No retries, trimming, gain repair, semantic transcript correction or score-based selection. Models remain evaluation candidates; registry/configuration/data unchanged. Rollback joins owned workers, keeps all artifacts and leaves production integration disabled.

## First integration failure and caller compatibility correction

The first six paths retained six successful real ASR results, but all stopped before CORE generation/TTS: new caller requested128tokens while the unchanged existing Fast context contract requires at least512. [First failure and complete executed-source/raw hashes](../evidence/d72-native-voice-first-failure.json). A separate bounded retained-text diagnostic and a red regression reproduce `invalid_token_budget` before inference. Preserve all first outputs and failure/source receipts.

Correct only the new caller to the existing512token minimum; retain CORE32K, presets, model/worker/SDK/limits and the same predeclared source/matrix. A separate compatibility regression directory runs the corrected integration and retains its results separately. This is a software-contract correction, not repetition to select favourable model responses; initial ASR outputs remain recorded and the repeated inputs/results are explicitly identified. No original reviewer qualification is rerun and no quality threshold is softened. All first TTS/native waveform and generation limits remain binding.
