# D74 — Multimodal/voice engineering review and open acceptance gates

**Purpose:** Combine existing accepted image/video scopes with actual new voice examples, resource observations and current regression while keeping manual/production acceptance honest.

**Status:** Engineering review COMPLETE; final voice/product phase acceptance PENDING. D70offline evaluation now includes owner complete/repeated listening24/24on speakers with quality limitations; this is not an all-candidate quality/model/license PASS. [Owner findings](D70_OWNER_LISTENING_20261103.md). [D74decision brief](D74_VOICE_DECISION_BRIEF.md) is prepared2026-11-03: existing candidate quality/CPU latency/RAM/rights/rollback/options, [Owner requirements](VOICE_PRODUCT_REQUIREMENTS.md) now specify VI first/female Northern voice, EN retained, custom languages later pending; model/protocol/latency decisions remain pending. [Physical microphone check](D74_PHYSICAL_MIC_CHECK.md) now has owner-reported basic PASS on Brave/PC microphone: clear complete playback, Stop/Cancel/Escape/tab switch stop capture. Initial load, permission denial and30-secondlimit now also owner-reported PASS: requested capture/playback smoke complete. Unreported preview/delete/TTL and other lifecycle details/product acceptance remain separate. Independent later implementation can be prepared without declaring this gate closed.

## Verified engineering evidence

- Original D61–D67 CORE vision/OCR/image/video/timeline/resource scopes remain retained and unchanged: see [D67 resource/context report](D67_EXISTING_MULTIMODAL_BENCHMARK.md). Those image/video model-quality observations are historical accepted examples, not new predictions in this review.
- D68/D69 original ASR/VAD evaluations retained. New [D72 held-out comparison](D72_VAD_ASR_COMPARISON.md) covers40independent new speech sources/5negatives/2padded repeats,89requests per ASR and94VADcalls; preserve all lexical failures and keep concatenating VAD disabled.
- [D71 recording](D71_EXPLICIT_RECORDING.md), [D72 six actual complete voice paths](D72_BUFFERED_VOICE_COMPOSITION.md), [D73 retention/delete/security](D73_AUDIO_RETENTION_SECURITY.md) have their own verified local scope and native fake-device tests.
- Original phase verification recorded **1043media/voice-related tests PASS74.39s/0FAIL/0SKIP**; no rerun in this documentation task. One known warning is the deliberately duplicate Piper archive fixture. This is not the whole-project regression. Established read-only service/model/data/security baseline audit PASS; all inference workers/browser/UI processes retired.

## Actual voice resource matrix

| ASR | TTS | Language | Buffered latency | ASR worker peak RSS RAM | TTS worker peak RSS RAM |
|---|---|---|---:|---:|---:|
| qwen3-asr-0.6b | qwen3-tts-0.6b | en | 45.937s | 5.6359GiB | 5.5269GiB |
| qwen3-asr-0.6b | piper-en | en | 11.359s | 5.6359GiB | 0.2187GiB |
| qwen3-asr-0.6b | piper-vi | vi | 13.980s | 5.6361GiB | 0.2224GiB |
| whisper-small-ct2 | qwen3-tts-0.6b | en | 49.315s | 0.8563GiB | 5.5278GiB |
| whisper-small-ct2 | piper-en | en | 7.775s | 0.8563GiB | 0.2544GiB |
| whisper-small-ct2 | piper-vi | vi | 7.849s | 0.8564GiB | 0.2178GiB |

CORE stays loaded at32K and its recorded NVIDIA process allocation remains9386MiB. Worker RSS is lifetime process RAM, not model-only/private/minimum RAM or VRAM. ASR and TTS workers run sequentially; do not sum RSS as a simultaneously measured peak. Latency includes worker load/conversion and may use warm files/caches; no streaming TTFA, cold-load/SLO or concurrency guarantee. D67 historical sampled CORE/media figures remain separately labelled in that report.

## Listening completed; remaining manual and production gates

1. D70listening dependency COMPLETE for offline evaluation: owner24/24complete/repeated listening on speakers recorded in [new evidence](D70_OWNER_LISTENING_20261103.md); original blank worksheet preserved. Resolve observed VIvoice dissatisfaction/quality failures in the separate approved product decision; do not call all candidates PASS.
2. Explicit approved ASR/TTS/voice choices and complete engine/voice/license/deployment review. [Evidence-bound proposal](D74_VOICE_DECISION_BRIEF.md) now prepared; ENcandidate has latency/intonation limitations, VIvoice not accepted. No product model default or recording-to-model endpoint has been activated.
3. Production no-speech and short/quiet-word policy. Current ASR can hallucinate on authored negatives; naive VAD concatenation degrades speech WER. The present comparison does not certify word boundaries or universal gating.
4. Requested physical microphone capture/playback smoke is now owner-reported PASS on Brave/PC microphone, including all three follow-up scenarios in the [current checklist](D74_PHYSICAL_MIC_CHECK.md). Preview/delete/TTL and unreported lifecycle details remain outside that accepted smoke scope. Final production E2E/load/restore/security/release gates stay open. Neither this owner report nor native fake-device checks certify the whole product flow.

The roadmap keeps D74 product acceptance open. Preparing independent harness/skills/security code does not mark voice accepted, lower these gates, select models or approve release. [Exact engineering evidence](evidence/d74-local-engineering-review.json).
