# ADR 168 — Conditional native check of the qualified speech gate

**Purpose:** After ADR169 passes all fixed detector controls, verify actual no-speech suppression through the unchanged ASR→CORE→Trúc Ly workflow rather than declaring synthetic sentinels a native success.

**Status:** Within the owner's request to continue fixing and verify PASS. Conditional, finite research scope; not product/default deployment or permission to change models.

## Scope and criterion

ADR167 failed99/100 and never activated this conditional check. Only if ADR169 records all147peak decisions correct,288observations, no runtime/preservation failure and restored baseline, run exactly eight new turns: Whisper-small CT2 then Qwen3-ASR-0.6B, each on the first two original D74 speech sources and its two original no-speech sources. Trúc Ly reading policy, CORE32K/Fast512 and all existing model/reference/resource settings stay fixed. Original48turn ADR165 outcomes stay immutable. Do not claim native quiet-ASR accuracy from these original-volume VI sources.

Each turn first runs one original CPU/offline Silero smoke worker on the exact fixed detector-only view, then joins it. A valid empty decision must stop before actual ASR/CORE/TTS; a speech decision forwards the complete original audio. ASR/TTS load only after the detector exits, fresh per admitted turn. Required success:4positive complete native/playback outputs,4correct no-speech early refusals, exactly4actual ASR/CORE/TTS calls each,8VAD observations, all hashes/model/owner/clock contracts, lifecycle guards and baseline intact. No retries, transcript repair or result selection. Functional failures remain visible; software/resource/provenance faults stop remaining admission.

Native phase≤900seconds, original per-turn180second deadline, original ASR/TTS caps and owned CORE guard; VAD original3GiB address-space cap, CPU0,1,14GiB MemAvailable and180second worker cap. VAD is not co-resident with ASR/TTS; sampled VAD+CORE RSS≤8GiB, original ASR/TTS/CORE aggregate guard retained. Retire exact owned processes on cancellation/fault and preserve first outcomes. Maximum4workflowCOREcalls plus only the unchanged owned CORE lifecycle's separately recorded optional recovery budget; no additional recovery generation planned. No download/model/default/voice/context/shared-service/Vault/database/Docker/provider changes.

## Consequences and limits

P1 AUDIO-VAD-ASR-002 integration check. Dependencies: exact ADR169 qualification/source hashes, new source-bound software controls, prior accepted reading bridge and original six PCM inputs. Effort one bounded native/audit milestone. Risks: stale view binding, worker cancellation, source/voice mismatch, co-residency limits and confusing buffered audio with speaker timing. Rollback omits the optional detector composition and joins owned processes; no production migration or cutover. PASS closes only these local detector/no-speech integration checks. General ASR accuracy, short/quiet word retention, physical4second performance, rights/model/default/product acceptance and D90release remain separate; D60 deferred and pronunciation cycles stopped.
