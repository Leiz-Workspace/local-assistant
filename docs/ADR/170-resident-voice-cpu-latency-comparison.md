# ADR 170 — Resident voice latency with fixed CPU profiles

**Purpose:** Address VOICE-LATENCY-AC-001 under the owner's request “Làm cho nó pass đi”, without replacing models, weakening quality or changing the four-second target.

**Status:** Authorized bounded research implementation/comparison. This does not approve a product model/default, deployment or physical first-audible acceptance.

## Decision

Keep a single owned CORE32K/Fast512 and one resident detector/ASR/Trúc Ly reading worker per group. No user-input processing, warmup inference, cached transcript/answer/audio or source-dependent preload before timed submission. Setup/readiness time is separate and explicit. Reuse the accepted peak-v2 detector, original complete PCM/sample clocks, ASR decoding/precision/settings, text/reading/voice/reference/sampling/seed/frame caps and native-to-playback conversion.

Compare exactly2,4,8CPUthreads for ASR/TTS, on distinct physical cores0..threads−1. The original two-core baseline remains unchanged. The new research profiles allocate more host CPU for measured inference, not more RAM/VRAM/address space or weaker deadlines. Topology observed2026-11-05 has eight physical cores0–7 with SMTsiblings8–15; do not schedule those siblings as extra physical cores. Detector remains original two CPUthreads. No GPU ASR/TTS, new packages, weights or source/SDK mutation. Only new research entrypoints select the SDK's existing thread argument; application/defaults remain unchanged.

## Fixed scope, quality and stopping

One36turn cohort: Whisper-small then Qwen3-ASR, each profile2→4→8, each on the same six original D74 sources (four speech/two negatives) in original order. Exactly36VAD, at most24ASR/24CORE/24TTS first calls, zero retries. Worker scope6VAD or4ASR/TTS calls. Negative turns must stop before all three downstream calls; no transcript repair, truncated response, changed beam, language, voice, sampling or outcome-dependent profile selection. Each group is recreated and joined; no undeclared shared warmup.

Require complete native/playback output and original provenance on every speech case; preserve all latency failures and unattempted rows. Match ASR transcript bytes across profiles for each source/candidate. Report CORE-answer/reading-plan/frame/reference/native waveform parity separately; thread-dependent output changes cannot silently become a quality PASS. Exact native audio parity is strongest; any numeric-only differences must be reported with length/peak error/SNR and cannot replace acoustic/semantic acceptance. The four-second engineering proxy passes for a lane/profile only if **all four** complete-PCM speech latencies are≤4seconds and all quality/no-speech/runtime gates hold. No averaging/p95, negative-refusal times, beep, first token or initial silent PCM can satisfy it.

For same-input numerical equivalence, require exact transcript and CORE-answer bytes, matching reading phones/chunks/frame caps/reference/EOS and native sample count; report whether float bytes are exact. A numeric-only waveform difference qualifies as equivalent within this comparison only if maximum absolute error≤0.0001 and SNR≥80dB (identical zero signals handled separately). This is a strict numerical proxy, not new listening/naturalness acceptance. Changed words, answer, phone plan, EOS/length or errors outside that fixed envelope remain a quality-parity failure even when a time is fast. Verify all14original ASR checkpoint artifacts before loading.

All original memory guards stay: ASR/TTS8GiB virtual, TTS sampled RSS2GiB; VAD3GiB virtual; aggregate sampled resident workers plus owned CORE≤8GiB; MemAvailable≥14GiB before each load. Include VAD in aggregate checks. CPU0..7maximum, no affinity or host-service mutation outside owned children. Per-turn180seconds/global900seconds, existing worker CPU/log caps, private artifact root≤8GiB. Stop admission on first resource/software/provenance/cleanup fault, retain every first failure, close/join exact owned workers/CORE and verify baseline. A missing four-second or quality result remains OPEN/FAIL, not a reason to weaken criteria.

## Dependencies, impact and rollback

P1, one worker/lifecycle/test and bounded native measurement milestone. Depends on ADR169147/147 and ADR1688/8, pinned assets/runtime, existing owner/model/clock contracts and actual stage data. Risks: resident co-memory, CPU contention, changed numeric reductions, stale readiness, cancellation/TTL and conflating buffered PCM with real audio output. Rollback retires the optional workers; original code/config/data/models/defaults and every older score remain unchanged. No migration, Vault/database/Docker/provider action or shared-service restart.

This cohort measures submission→complete PCM after explicit worker readiness, not cold start or physical speaker playback. A compute result over4seconds fails this buffered route; a result under4seconds still requires authenticated endpoint/playback integration and a separate real-device first-audible check. D74whole product/rights/model/default/device and D90release stay OPEN; D60 deferred and pronunciation refinement remains stopped.
