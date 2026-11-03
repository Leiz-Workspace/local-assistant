# D74 — Proposed VI voice and four-second feasibility protocol

**Purpose:** Define a bounded, reviewable comparison before any candidate download or model request, preserving original baselines and separating software, voice quality and actual audibility.

**Date:** 2026-11-03. **Status:** PROPOSED / NOT APPROVED / NO RUNNER IMPLEMENTED / NO EXECUTION. [ADR-154](ADR/154-proposed-isolated-vietnamese-voice-feasibility-campaign.md) controls scope/resources/rollback. [Fixed packet](evidence/d74-vi-voice-proposed-packet-20261103.json), [proposed payload pins](evidence/d74-vi-turbo-proposed-artifacts-20261103.json).

## Preconditions and source freeze

Owner explicitly approves the candidate,16payload files, isolated SDK preparation and bounded campaign. First implement and test the research runner/adapters/measurement surface without live models. Freeze code, dependency lock/package hashes, every artifact/voice and corpus hash, exact settings/limits, request counts and interpretation before the first prediction. The documentation packet prepared now is a proposal input, not the final executed-source freeze. No model request occurs if preconditions are absent or modified.

The current snapshot has750application/config/test files with a retained5889PASS suite. Preserve those bytes, passing D71recorder/VoicePipeline, configuration, production endpoints, shared services and old results. Existing Qwen/Whisper/Piper/CORE artifacts are borrowed read-only. CPU FP32 candidate settings and exact preset assets must be validated against the approved manifest and actual SDK before qualification; voice aliases/defaults cannot silently replace the two requested presets.

## Fixed measurements and denominators

| Phase | Inputs and variants | Maximum calls and disposition |
|---|---|---|
| Qualification | One separately declared neutral text per new Turbo/original Piper runtime |2TTS; retain first failures. No retry/silent auxiliary downloads. Stop before scoring if integrity/output/lifecycle/resource guards fail |
| TTS comparison |8new authored VI texts × original Piper VI / Turbo Trúc Ly / Turbo Ngọc Huyền |24first outputs, including every error. Same exact text per variant; upstream normalizer/phonemizer differences disclosed. No cross-engine architecture-only claim |
| Workflow comparison |6retained source clips × Qwen/Whisper ASR × Piper VI/Turbo Trúc Ly × fresh/resident model state |48declared slots; ≤48ASR/48CORE/48TTS calls, plus2CORErecovery calls. Fixed Trúc Ly, no outcome-driven voice or ASR selection |

Across phases:≤74TTS,≤48ASR,≤50CORE; automatic retries0. If an upstream software failure stops execution, keep all declared unattempted rows; do not replace failed slots with later successes. Negatives that correctly refuse need no answer-synthesis call; unexpected speech/answers remain failed negative observations, not successful task completion. Stage request counts are ceilings, not fabricated actual totals.

Eight new texts cover rhythm, question intonation, numbers/currency, date/time, tone contrast, instruction, clauses and borrowed terms. Authored references are not independent human truth/MOS. The workflow uses four VI speech clips chosen solely by existing duration quantiles at indices0/6/12/19 plus existing VI-labelled negatives1/3. Their identities/durations/hashes are in the packet; all were used in priorD72 and are transparently repeated, not a new unseen ASR benchmark. Never pass expected transcript/negative label into inference or repair the ASR text.

Keep the original normalized PCM/source spans and model output limits. No waveform trimming, input shortening, answer truncation, prerecorded response or result cache. A CORE response exceeding a retained native limit fails honestly. Keep existing CORE32K/Fast512contract; request/model text cannot gain tools, profiles or credentials. No VAD concatenation or voice cloning is included.

Retain each engine's original native waveform/sample rate/channels and hashes; Turbo's declared output is48kHz, while the original Piper voice is22050Hz. Qualification must validate the actual returned shape/finite values, not assume the separate codec's channel layout. For the existing16kmono PCM port, use an explicitly recorded conversion with original source clocks and separate native/playback hashes, including conversion time. Do not overwrite native audio, alter gain or trim silence to improve comparison. Owner listening uses the original outputs; a playback conversion is not a repaired native score.

## Fresh versus resident comparison

Fresh-process runs include owned ASR/TTS startup/import/load in the measured turn. Resident runs reuse only already-loaded model processes, with each ASR/CORE/TTS computation performed for the current turn. Measure readiness/load separately and retain the first warm-turn effect. No feature/output/audio cache for known questions.

A resident adapter is research-only and must preserve nonqueued admission, owner/source/model binding, limits, full-output publication and joined cancellation/shutdown. It does not modify the accepted application service. Report every cold and resident result; warm results alone do not certify a general four-second requirement or authorize a new product readiness policy.

## Timing boundaries and four-second acceptance

Record client submission, ASR start/end, CORE start/token/completion, TTS start/complete, transfer, playback scheduling, digital first non-silent answer sample and audio completion with clock provenance. Use one client monotonic timeline for end-to-end observations; never subtract unrelated process clocks without calibration. Store outputs/hashes, errors, stage wall/CPU and sampled RSS/VRAM alongside latency, not just successful-case averages.

**Owner target:** explicit submission→physically audible meaningful answer≤4seconds. First token/PCM, beep, silence or progress announcements do not satisfy it. Record maxima and all misses; p50/p95 may describe results but cannot replace the maximum target. A correctly refusing negative is assessed for no-speech behavior, not a fabricated first-answer time.

The isolated initial implementation may establish submission→complete PCM and browser digital-render timing. Clearly label those as software/proxy observations; playback APIs alone do not prove physical speaker audibility. Physical first-audible acceptance requires a reviewed output-device/acoustic measurement with synthetic input and explicit authorization for any recording. **No automatic microphone capture or owner audio is authorized by this protocol.** If physical timing cannot be measured, leave that gate UNVERIFIED even when generation/rendering is fast.

The four-second goal is not a new process timeout. Retain the180second technical turn limit, worker guards and campaign wall cap from ADR154. Slow/error/incomplete cases are reported; do not cancel at4seconds and count them as omitted observations. Inputs in this packet do not certify all30-second recorder inputs, all text lengths, concurrency or general ASR quality.

## Quality review and separate product gates

Prepare24unaltered native audio outputs with stable IDs and original hashes plus a reviewer sheet. Owner records pronunciation/tones/number-date reading, question rhythm, artifacts, female/Northern perception, naturalness and uncertainty. Preserve the original disliked Piper voice as a comparison and every adverse opinion. A model-family/preset label is not owner approval. Optional anonymized presentation is not an independent multi-rater MOS study.

No new quality/latency score threshold is tuned after predictions. The existing four-second requirement and owner voice requirements remain binding; report failure or uncertainty separately. No-speech hallucinations, word loss, licensing, resource coexistence, real-device/privacy/lifecycle, approved model choice and release remain separate gates. Retain all earlier D70/D72failures and datasets unchanged.

## Completion and reporting

Before execution, the runner needs real software regression/lifecycle/failure/cancel/boundary tests, formatter/lint checks and a final freeze. After any approved execution, report exact commands/settings, counts including failures/unattempted, all timings/resources/voice judgments, source/payload preservation and joined owned-process cleanup. No software PASS is a model-quality or physical4second PASS.

This proposal has no download, live inference, runner tests or trial results. The present verification only checks metadata/hash arithmetic, source/packet provenance, original-file preservation and documentation. Further architecture work, a different voice/model/backend/cap or production migration requires a reviewed amendment/owner decision; there is no automatic fallback to Nano/int8/GPU/cloud.
