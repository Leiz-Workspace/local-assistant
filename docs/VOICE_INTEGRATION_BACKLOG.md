# Voice integration dependencies

**Purpose:** Assess additional evidence and lifecycle work required by observed offline voice results before model/default selection or product activation.

## AUDIO-VAD-ASR-001 Held-out gated versus ungated ASR

**Priority P1; scheduled D72 prerequisite.** This follows D68's3/4and4/4known-no-speech ASR outputs and D69's limited clip-presence/negative evaluation. Dependencies: unchanged D68/D69 source/model artifacts, bounded private explicit waveform handling, fixed segmentation clocks/thresholds, a separately frozen independently labelled VI/EN holdout and original CORE/runtime audit. Effort one paired evaluation milestone, separate from model adoption.

Compare the nominated ASR candidates without gating against the exact original-v5 gated composition on common held-out speech/noise/short-speech/known-negative cases. Keep rejected/missing speech, full original source spans and all first errors; no label repair, outcome-driven retries or tuning on D68/D69. Measure original-timeline mappings, coverage, per-language raw WER/CER, no-speech errors, added latency/resource/CORE impact and cancellation cleanup. Compare complete materialized outputs, including short/quiet boundaries and no-speech early exit. Independent fine-grained voice labels are needed for word-level retention claims; do not turn a whole-clip transcript into sample-level ground truth.

Risks: VAD discards quiet/short words or reorders context, gap removal corrupts source clocks, full ASR/candidate models overlap in memory, state survives cancellation, and a successful synthetic silence test masks user-audio failures. A complete comparison may still reject a configuration. Model selection/deployment requires actual performance/resource/compatibility evidence, migration/rollback and the owner's explicit approval. No default/current role or database/index/source migration is authorized by this entry. Rollback disables/drains only the optional proposed gate and retains original source audio and ungated path/evidence. Do not delete recordings or rewrite earlier scores.

## AUDIO-PROD lifecycle

D71–D74 retain explicit recording consent/stop, authenticated source/owner capabilities, nonqueued bounded admission, joined cancellation, model buffering/error handling and retention/delete/security gates. Existing D66 supplied-reference and D68/D69 offline results are foundations; none activates a microphone, background recorder, ASR/VAD/TTS default or server. TTS evidence/voice licensing remains D70; additional gaps must be assessed here before scheduling, not silently replacing registry models.

## AUDIO-TTS-NATURALNESS-001 Actual first-output auditory review

**Priority P1; currently an unmet D70 criterion. Proposed move to a mandatory D72/selection/deployment prerequisite is NOT APPROVED or applied.** [ADR-097](ADR/097-proposed-tts-auditory-review-sequencing.md) makes that exact alternative reviewable; D70 remains IN PROGRESS and D71 unstarted under the current order.

The actual D70 tool cannot accept audio input, so no listening/naturalness/MOS judgement exists. Dependencies: an audio-capable tool or reviewer, all24retained first native waveforms/complete separate Opus listening copies and their hashes, fixed authored texts, accurate reviewer provenance and original model/data/runtime guards. Effort half to one review milestone; no synthesis rerun or model provisioning. Record per-output pronunciation/prosody/artifacts/naturalness with uncertainty after hearing the complete signal. Label same-agent review honestly and do not call it independent human MOS. [Measured report and review packet](D70_OFFLINE_TTS_COMPARISON.md).

Risks include replacing hearing with ASR/acoustic proxies, selecting only good outputs, forgetting deferred quality work, silently using unsupported Qwen Vietnamese/Auto or conflating voice/engine/source-data licenses. Keep all first failures and no outcome-driven tuning. Model selection still needs benchmark/resources/compatibility/migration/rollback and explicit owner approval; Piper VI source-license verification and AUDIO-VAD-ASR-001 remain separate. No model/default/service/data change is authorized. Rollback of the unapproved proposal keeps D70 open/D71 unstarted, retaining every output and current system unchanged.
