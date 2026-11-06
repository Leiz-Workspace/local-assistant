# ADR 165 — Reading-aware native voice workflow validation

**Purpose:** Execute the owner-requested real-model confirmation of the ADR164 reading bridge with existing pinned assets and an auditable48-slot matrix.

**Status:** Authorized by “Chay để xác nhận đi” after the explicit report that48real-model cases and4second timing were still unverified. This is a new reading-aware workflow scope; the old ADR155raw entrypoint/approval/first outcomes remain immutable and are not invoked or relabeled.

## Fixed scope

Use the original2ASR lanes (Qwen3-ASR-0.6B CPU float32, Whisper-small CT2 CPU int8),2TTS lanes (fixed existing Turbo Trúc Ly CPU FP32 with the verified reading bridge; original Piper VI control),2states (fresh/resident),6unchanged D72sources (4speech,2negative)=48slots. Retain source/PCM hashes and original labels. No new microphone/audio collection, qualification, standalone listening clips, model/reference downloads, voice selection or pronunciation tuning. The accepted Trúc Ly/API-spaced/date/clause/US-term path is fixed; the unaccepted compact Ngọc Huyền policy is excluded.

Preregister the new cohort order before any observation: Whisper first, then Qwen; within each ASR, reading-aware Trúc Ly first, then Piper; fresh before resident; original six-source order. This puts the existing lower-RAM lane first so a later co-residency refusal cannot prevent every reading-path observation. It does not choose a product ASR, change any model or discard slower/higher-RAM rows. Assign new reading-turn IDs and retain all48slots even if stopping early; do not reorder after results.

Reuse original VoicePipeline/ResearchASR/ResearchCORE/owned CORE32K Fast512, native waveform conversion and worker lifecycle. Add a separate operator and tests rather than editing52previous research files. Turbo workers load only with a scope-bound read-only manifest, correct policy/voice/model, max1request in a fresh slot or6in a resident group; verify exact manifest SHA/readiness. The bridge checks actual native plans/reference hashes and source/rendered-answer binding. Piper stays original. No outcome-driven ASR/TTS/preset/backend switch or transcript/output repair.

At most48ASR,48workflow CORE and48TTS first attempts; the unchanged owned CORE lifecycle retains at most2optional recovery checks, accounted separately in its receipt. Negatives with empty actual ASR refuse before CORE/TTS. Nonempty negative transcripts are observed as negative failures, not replaced with gold text or hidden. Count before dispatch;0automatic retries. Never merge the original6software-invalid/42unattempted workflow rows into this cohort.

## Resources, stopping and rollback

Original CPU0,1/two threads; AS8GiB per ASR/TTS; sampled TTS RSS2GiB and sampled aggregate resident-worker/core RSS8GiB; MemAvailable≥14GiB before each load; ASR worker900s/TTS600s/turn180s/campaign3600s; parent asset root≤8GiB. CORE uses its unchanged owned lifecycle/resource guard, not a shared-service restart. No GPU TTS, reduced CORE context, changed caps, streaming, caching, response truncation, VAD policy/default activation or service/Vault/database/Docker mutation.

Freeze owner instruction/scope/packet/source/tests/software/dependent ADR164 hashes and baseline before any model start. Resource, provenance, worker/metadata/software or cleanup failure stops later admission and preserves all unattempted rows. Functional unsupported-response or ASR/CORE quality failures remain visible; no retry. Always shutdown/join the exact owned pipeline/workers/CORE, verify native/container baseline and original bytes, retain first failures and original waveforms. No production migration occurs.

## Measurement and interpretation

Record every slot, stage timings, fresh/startup versus resident costs, ASR/no-speech outcomes, complete native/playback PCM, resource/cleanup observations and render traces. Submission→completePCM is a buffered software proxy, not the instant a speaker starts playing. A proxy over4seconds cannot support a4second claim for this buffered route; a proxy under4seconds still does not certify real-device first-audible. Physical endpoint/auth/retention/playback and owner acceptance remain separate. Report incomplete48coverage honestly if stopped; no score selection or model adoption follows.

P1 VOICE-LATENCY-AC-001 / D74. Dependencies: verified386-test reading bridge/model-free parity, unchanged sources/assets/config, tested new operator and authorized finite scope. Effort one bounded native/audit milestone (up to60minutes). Risks are ASR hallucination/latency, co-residency resource limits, arbitrary CORE text hitting declared guards, native completeness and confusing software with product acceptance. D60 remains owner-deferred; pronunciation refinement remains stopped; D74rights/model/default/no-speech/device/product/D90release remain open.
