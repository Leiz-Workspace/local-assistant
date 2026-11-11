# D69 original Silero VAD v5 offline evaluation

**Purpose:** Record genuine original-v5 speech-presence/control, sample-clock, repeatability and resource measurements without selecting VAD or claiming combined-ASR/word-boundary accuracy.

**Status: PASS local offline evaluation; NOT SELECTED / NOT DEPLOYED.** Source commit`48f9888`, ADR-095.59 new/526 related tests PASS16.88s;19 private auditor controls PASS0.58s. Final readonly audit verifies612 source files/all608 prior source bytes, original models/configuration/data/security/runtime/CORE unchanged. Historical D67 full4495 is scoped to599 source files; no new full612-source run is claimed.

## Pinned official implementation

Original [snakers4/silero-vad tagv5.0](https://github.com/snakers4/silero-vad/tree/v5.0), annotated tag object`a27ffa1d13db33ee6d9898ee469c6302ccc46912`, target commit`5cd2ba54db059f961e7545d4f211b44f005a6dfb`, MIT. Canonical ONNX2313101bytes, Git blob`d0ccd9d7fc1f98033c04b4a2b03ed0e07e842a13`, SHA256`6b99cbfd39246b6706f98ec13c7c50c6b299181f2474fa05cbc8046acc274396`. Exact unchanged official`utils_vad.py`, README and license accompany it. No v6/JIT/alternate model, no ASR rerun or extra aligner.

Direct local official `OnnxWrapper(force_onnx_cpu=True)` plus `get_speech_timestamps`, no TorchHub/download/read_audio factory. Separate uv environment: CPU Torch/torchaudio2.10.0+cpu, ONNXRuntime1.31.0, NumPy2.5.4. CPUExecutionProvider only; official ONNX intra/inter-op one thread each, Torch two threads, CPU affinity0,1. These are inference settings, not a claim of exactly two kernel threads. Original app/D68 environments and lockfiles remain unchanged.

Fixed original threshold0.5/hysteresis0.35,512sample32ms windows/64sample recurrent context, min speech250ms, min silence100ms, pad30ms, integer sample outputs. Official segmentation resets state per recording and pads only the last model window; complete source float32 buffers are hash-verified unchanged before/after. A transparent observer returns the original tensors and records external resets/probabilities/windows. Probabilities are uncalibrated model outputs, not verified truth confidence.

## Corpus and first observations

47unique inputs:40unchanged D68 FLEURS recordings (20VI/20EN,9/10 distinct sentence IDs),5known-negative signals,2padded first-source composites. Known negatives are5seconds each of exact silence, seed7low-amplitude white noise,50Hz sine,500Hz sine and two authored5ms clicks. Each composite has exact5second zero prefix/suffix around the first selected source recording and an authored2second timeline origin. No microphone/private recording, normalization/resampling or independently labelled word boundaries.

Two passes were specified before predictions: forward then reverse order with a reset per recording.47unique inputs remain47independent input identities, not94independent signals. Each pass processes485.18source seconds;970.36seconds total, excluding final model-window padding.

| Observation | Actual first result |
| --- | ---: |
| Complete calls |94/94 |
| Exact forward/reverse segment/probability replay |47/47 inputs |
| Whole-recording speech presence detected |40/40 public speech recordings |
| Known-negative false speech |0/5 unique inputs |
| Padded composites with source-region detections |2/2 |
| Known-padding false-positive samples beyond62ms window+pad tolerance |0 for both composites |
| Import / load seconds |1.452 /0.038 |
| All94segmentation-call seconds |3.039 |
| Whole worker wall seconds |4.881 |
| Call latency min / median / max seconds |0.01570 /0.02993 /0.07106 |
| Duration-weighted call RTF |0.003132 |
| Lifetime process peak RSS KiB |277724 |
| Lifetime process peak RSS MiB |271.215 |
| Process CPU seconds |4.774 |

Every returned interval is a complete valid nonoverlapping integer interval within the exact source sample count. Host timeline mapping adds32000samples to composite-relative intervals exactly. This proves source/clock arithmetic, not that a detected boundary identifies a word to one-sample precision. No source clipping, dropped final samples, failed calls, outcome-driven retries or threshold changes. Both passes include all controls and all recordings; repeated results are retained unchanged.

RSS is process RAM including imports/SDK/model/mapped/shared pages, not unique RAM, a minimum hardware specification or candidate VRAM. The2.313MB checkpoint is disk storage, not RAM. The imported Torch/torchaudio/ORT stack is part of this actual measurement; an optimized ONNX-only deployment was not measured. Files/cache may already be warm; first inference initialization remains included. No cold-storage, streaming/word-timing/SLO or cross-hardware determinism claim. CORE stayed loaded at its original PID/start/command/model, recorded RAM and NVIDIA allocation separately, and passed literal text recovery before/after. No owned ASR/VAD worker remains.

## Interpretation and remaining gates

The fixed candidate separates these particular public speech-presence and authored negative inputs and reproduces exact outputs under reverse ordering on this host. The corpus does not establish real-room/music/microphone false-positive rates, quiet/short-word retention, sample-level speech recall or human word boundaries. Whole-recording presence can succeed even when a model misses part of a sentence. Five synthetic negatives do not certify production noise robustness.

D68 first ASR hallucinations remain3/4Qwen and4/4Whisper requests. No gated ASR was run here, so do not claim those errors are fixed or that VAD preserves ASR WER. [AUDIO-VAD-ASR-001](VOICE_INTEGRATION_BACKLOG.md) adds the necessary held-out gated/ungated comparison before D72 acceptance, with separate risk/effort/dependency/rollback. This is a deployment dependency, not a retroactive rewrite of D68/D69 evidence.

Keep original SileroVADv5 as an evaluated candidate, not an approved default. Owner-approved selection, explicit recording consent/stop, source/owner-bound API lifecycle, short-speech/error/cancellation/admission behavior and resource/retention tests remain required before runtime activation. Preserve every existing model role, D24 E5 rollback and source/collection/database. Evaluation rollback retires only its owned namespace and retains private artifacts/results pending separately authorized cleanup; no production migration occurred.

Evidence: [first frozen contract](../evidence/d69-vad-first-freeze.json), [auditor/control/result freeze](../evidence/d69-vad-audit-freeze.json), [readonly final audit](../evidence/d69-vad-readonly-audit.json), [acceptance](../evidence/d69-vad-acceptance.json). Original raw window probabilities/segments and SDK/corpus remain under ignored`data/backups/d69-*` paths. The sole inherited D68 audio-backlog progress-document update is checked against exact retained old/current/Git bytes; all other historical guards remain unchanged.
