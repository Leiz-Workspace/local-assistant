# ADR 158 — Paired API phoneme and reference-conditioning diagnostic

**Purpose:** Isolate why the current model realizes English A incorrectly without changing the accepted Vietnamese date/prosody path or claiming a text rewrite fixed acoustic pronunciation.

**Status:** ACCEPTED FOR ONE OWNER-REQUESTED DIAGNOSTIC; NOT PRODUCT OR MODEL SELECTION. The owner explicitly said “Làm đi” after the retained API failure. [Authorization](../evidence/d74-api-reference-authorization.json) records this research scope; sixteen is the engineering ceiling, not an owner-specified count. ADR-155 workflow recovery remains unapproved.

## Evidence and hypothesis

Actual earlier traces contain correct English `ˈeɪ pˈiː ˈaɪ`, but the owner hears A-Pi-Ai. Model-free investigation confirms tokenizer encode/decode roundtrips exactly with zero unknown tokens. No phoneme character loss is demonstrated. A first probe rejected standalone API because its expected canonical string did not match the SDK's compact secondary-stress form `ˌeɪpˌiːˈaɪ`; the rejection and investigative output are retained. This was an over-specific diagnostic expectation, not proof of a broken dictionary or tokenizer.

The pinned SDK accepts `use_ref_codes=False`; source shows the projected speaker embedding is added to every prompt/generated embedding even without reference-code rows. Dropping the accompanying audio-code prompt therefore preserves the exact speaker anchor at the input level. Its effect on perceived timbre, language, naturalness or English pronunciation remains unknown. We do not assume the preset reference codes' spoken language from their label or assert they caused the failure.

## Fixed comparison

Generate four controlled inputs for both retained Trúc Ly/Ngọc Huyền presets, under `with_reference` and `without_reference`: **16 top-level requests, one original engine generation each**.

1. English letter A alone, explicit `ˈeɪ.`: does the model realize “Ei” without acronym/context?
2. API alone with spaced letter phones and primary stresses: `ˈeɪ pˈiː ˈaɪ.`.
3. API alone using the SDK's compact dictionary form with secondary stresses: `ˌeɪpˌiːˈaɪ.`.
4. API inside one fixed Vietnamese sentence, using the original G2P English phones.

Within every ref-on/ref-off pair, require identical actual phonemes/token IDs/text prompt IDs, speaker embedding and projected-anchor hashes. Audit the actual engine prompt rows before dispatch; the only permitted conditioning difference is presence/absence of the original reference-code rows. Keep seed7, sampling0.8/top-k25/top-p0.95, repetition penalty/window, original frame caps, style/codec/watermark behavior and FP32CPU weights unchanged. No hidden warmup generation or retry. The two API phone forms are separate declared controls; do not tune one after listening or claim a univariate phoneme effect from changing multiple conditions.

Retain original native float/WAV, EOS, timings and input/conditioning hashes. Different waveforms, EOS or exact tokens do not establish correct English pronunciation. Owner listening must determine A versus Ei, API buzz/tremble, retained voice character and contextual behavior. No denoising, gain, trimming, replacement samples, external audio or new model asset.

## Isolation, guards and stopping

New worker/controller/tests only in `benchmarks/`; preserve all nineteen prior research files, accepted date/prosody behavior and all earlier audio/feedback. The accepted API is not switched to ref-off. No product routes, SDK/model files, model/default/voice choices, ASR/CORE, recorder, Vault/database/Docker/search or ADR-155 calls change.

Use the same CPU affinity0,1/two threads, AS8GiB, sampled TTS RSS2GiB/aggregate8GiB, MemAvailable≥14GiB before load, each worker and complete diagnostic≤600seconds, existing total parent-root≤8GiB. Maximum16TTS/0ASR/0CORE/0retries; at most8requests per condition worker. Stop on any first software/resource/provenance/native-completeness/pair/cleanup failure and retain every unattempted row. Freeze software/authorization/frontend/input/source/preset evidence before model execution.

## Priority, effort, risks and rollback

P1 under VOICE-ENGLISH-READING-001 and VOICE-API-ARTIFACT-001. Dependencies: explicit latest instruction, pinned model/SDK/presets, model-free roundtrip controls, tested paired invariants/lifecycle and headroom. Effort: one bounded investigation/16-clip listening milestone. Risks: correct phonemes may still sound wrong, dropping references may alter perceived voice despite the same embedding, short-letter frame caps may refuse complete audio, and a few controls cannot establish general code-switch quality. No frame/resource cap is loosened to obtain a result.

Rollback stops/joins only owned workers and verifies the native/container baseline, retaining failed diagnostics and restoring no product state because no integration occurs. Any later promotion needs explicit quality, resource/latency, migration/rollback and owner decisions. Date/prosody acceptance remains scoped and intact; English/API acoustic gates, rights/no-speech/physical first-audible4seconds, model selection/D74 product/D90 release stay open. D60 remains owner-deferred.
