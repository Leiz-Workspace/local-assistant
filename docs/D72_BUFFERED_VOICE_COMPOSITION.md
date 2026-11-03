# D72 — Bounded buffered voice composition

**Purpose:** Document actual local ASR→CORE→TTS integration and its source, owner, timing, cancellation and activation limits.

**Status:** PASS local offline composition; production activation/model selection gated. D70owner listening24/24is now recorded with quality limitations; [D74decision proposal](D74_VOICE_DECISION_BRIEF.md) keeps model/voice/product choices pending. [Design](ADR/112-bounded-voice-composition-without-model-selection.md), [native protocol](ADR/113-native-voice-evaluation-matrix.md), [acceptance/source/raw hashes](evidence/d72-native-voice-composition-acceptance.json).

## Implemented behavior

`VoicePipeline` admits one explicit submission without queuing, checks owner/source/PCM/language/model/completeness at every stage, sends text-only content to the existing CORE Fast adapter, and publishes only a fully buffered bounded PCM result. Speech cannot choose endpoints, profiles, tools or permissions. Original rational source clocks/spans remain separate from gated concatenation; no continuous source clock is invented across removed gaps.

Cancellation, shutdown and timeout retain admission until owned work exits; suppressed cancellation/late results never become successful turns. Evaluation adapters join their real bounded subprocess/thread. The application does not persist user audio/transcripts; private CLI artifacts contain only retained public evaluation speech. D71 remains a local-only recorder with no upload endpoint.

## Actual complete native paths

| ASR | TTS | Language | Complete buffered latency |
|---|---|---|---:|
| qwen3-asr-0.6b | qwen3-tts-0.6b | en | 45.937s |
| qwen3-asr-0.6b | piper-en | en | 11.359s |
| qwen3-asr-0.6b | piper-vi | vi | 13.980s |
| whisper-small-ct2 | qwen3-tts-0.6b | en | 49.315s |
| whisper-small-ct2 | piper-en | en | 7.775s |
| whisper-small-ct2 | piper-vi | vi | 7.849s |

All6paths execute actual original ASR, existing CORE and one actual native synthesis of the actual answer. Complete native waveform/hash/EOS checks pass. Qwen explicitVI remains unsupported; no Auto relabelling or candidate replacement. Separate playback PCM is explicitly quantized/resampled; native float audio stays intact. These are six wiring examples, not a representative quality benchmark, subjective listening, streaming TTFA, cold-load latency, minimum RAM/VRAM or production SLO. Buffered latency includes per-path worker load and conversion; caches may be warm.

## First failure and verification

The first6paths completed ASR but failed before CORE generation/TTS because the new caller requested128tokens below the unchanged Fast512reserve. [First failure/full executed-source and raw receipts](evidence/d72-native-voice-first-failure.json) remain intact. A red regression reproduced the existing budget contract; only the new caller changed to512. Corrected matrix6/6complete; every ASR source hash and raw transcript matches its original first attempt. No reviewer controls, thresholds, old results or production presets were changed.

Final **267related PASS7.52s/0FAIL/0SKIP**, including51new controls; Ruff/diff PASS. [Actual held-out VAD/ASR comparison](D72_VAD_ASR_COMPARISON.md) has40new independent speech utterances plus5negatives/2padded repeats,89predictions per ASR and94VADcalls/replay. Naive concatenation worsens several WER results; leave gating disabled and do not certify short/quiet-word retention.

Readonly audit preserves661prior sources,917protected files,176original inputs and24pending D70 listening labels. Same CORE PID/start/command/context32K and literal text recovery verified, workers reaped. No new weights/packages, production API/configuration/model/default/database/Vault/collection changes.

## Activation boundary and next work

No product recording-to-model endpoint or new model default is enabled. Product activation still needs explicit approved ASR/TTS/voice choices, licenses, no-speech/short-word policy and physical-device acceptance. Owner listening is recorded for original D70outputs; it does not approve these six D72example outputs or a production voice. This local milestone accepts verified composition and fail-closed nonactivation, not a deployed voice product. D73 owns audio retention/delete/security controls; D74 must report remaining phase/release gates honestly.
