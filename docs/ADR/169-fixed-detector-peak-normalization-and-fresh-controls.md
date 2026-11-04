# ADR 169 — Detector peak normalization with fresh controls

**Purpose:** Correct the arbitrary gain32 ceiling that left one quiet EN recording below usable detector amplitude in ADR167. That first99/100outcome remains FAIL; no native ASR/CORE/TTS check ran from it.

**Status:** Owner requests continued work until the issue passes. This is a separately preregistered candidate and comparison, not a retry or rewritten score.

## Fixed rule and provenance

Detector copy only: peak0.5 boost, `gain=1` on zeros and otherwise `max(1,0.5/abs_peak)`, float64 arithmetic then float32 output. With signed16-bit original PCM, the smallest nonzero absolute value is1/32768, so gain is mathematically bounded by16384. This removes a configured ceiling, not a memory/CPU/resource guard. No threshold, model, filter, DC correction, trim, ASR input gain, parameter search or arbitrary volume fallback. High-amplitude input is unchanged and no new clipping occurs. Every source/PCM/view/clock/model/hash check and mandatory trace remains before original-audio forwarding.

## Frozen scope and acceptance

Keep ADR167's100rows (47regression/47validation/6knownquiet) and every first failure. Add a fresh47row group before native observations: the first ten remaining eligible D68 originals per language, excluding D72sentence IDs and every original used by ADR167;20full-recording gain0.03derivatives;5three-second authored negatives (zero/Gaussian sigma0.02/uniform±0.05/DC−0.02/880Hz sine0.03, RNGseed20261105);2padded repeats. These are20new utterances relative to fix selection, not unseen model-pretraining data or new human quiet labels. Do not count derivatives/repeats/duplicate zero/DC/tone sources as independent recordings.

One new VAD-only campaign: three47case groups with forward/reverse passes, followed by six singleton known-quiet smoke cases, **9loads/288observations**. PASS requires all147fixed rows match expectations:132speech-present rows admitted,15authored-negative rows refused, with all provenance/resource/replay/cleanup gates. If a row fails, keep FAIL; no third gain candidate, threshold tuning, row deletion or automatic retry. Historical ADR167 raw87/100 and gain32candidate99/100 remain separate; the new147row score is not an aggregated paired score.

Reuse exact raw PCM from immutable prior float storage; only new47raw copies and147detector views live in this new exclusive root, bounded128MiB. No redundant PCM copies. Original Silero v5.0/settings/CPU/offline namespaces/3GiB virtual cap/14GiB pre-load headroom/180second worker cap, whole native≤900seconds. Zero ASR/CORE/TTS calls in this comparison. No downloads, package/model/provider/default/context/shared-service/Vault/database/Docker changes. Preserve original normalized PCM, first99/100 and failed134MiB preparation completely.

## Priority, risks and next gate

P1 AUDIO-VAD-ASR-002; one fixed implementation/test and native-comparison milestone. Dependencies: retained failure amplitude evidence, integer PCM bounds, separately fixed remaining utterances and source/view binding. Risks: amplifying noise/DC/quantization, inherited coarse labels and reused-control overfit; retain all negative failures and distinct cohort counts. Rollback omits only this research view. Only an actual full PASS can authorize the separately bounded8turn native check in ADR168 under the owner's same instruction; no further question between the two steps. Quiet-ASR semantics, short-word sensitivity, real-device maximum4seconds, rights/model/default/product and D90release remain independent; D60deferred and pronunciation cycles stopped.
