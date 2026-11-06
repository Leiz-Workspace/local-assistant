# ADR 167 — Fixed gain only on the speech-detector view

**Purpose:** Address AUDIO-VAD-ASR-002 after ADR166 rejected two quiet EN controls, without replacing a model, lowering the detector threshold or changing ASR audio.

**Status:** Owner requests continuation “Tiếp tục làm để pass đi”. Authorizes this fixed research comparison; passing means the declared local detector controls, not D74 product acceptance.

## Decision

For the detector only, convert original normalized PCM to float64, compute absolute peak and apply `gain = 1` for zero peak, otherwise `min(32, max(1, 0.5 / peak))`, then round once to float32. No DC removal, compression, filtering, trimming, padding, learned normalization or threshold changes. The original waveform cannot clip under this boost-only rule. ASR receives the identical original NormalizedAudio object/PCM/clock; never the detector copy. Retain source/PCM/view hashes, gain, sample count, model/policy and original rational clock in a required redacted trace. Complete native results must match the view before rebinding to original audio.

Silero v5.0 and all original settings/weights/runtime stay fixed. The earlier raw gate, models, application/defaults and every prior result remain immutable. This preprocessing candidate is not a new model selection or production activation.

## Fixed comparison and acceptance

Before inference freeze 100 labelled rows and two views each: the earlier 47-row D72 regression panel, six known quiet repair controls, and a 47-row validation group. Validation contains the first ten eligible retained D68 speech recordings per language whose sentence identities are absent from D72, twenty full-recording gain0.03 derivatives, five authored three-second negatives (zero, seed20261104 Gaussian sigma0.02, uniform±0.05, DC−0.02, 880Hz sine amplitude0.03), and two one-second-each-side padded repeats. D68 recordings have previous ASR/VAD history; they are disjoint from the D72 examples used for this fix, not a new independent dataset or human quiet-label review. Derivatives/repeats are not independent recordings.

Order: D72 raw47 then boosted47; validation raw47 then boosted47; then each of the six repair controls raw then boosted. Original workers process the four47case batches in forward/reverse order and twelve singleton smoke batches once: **16 loads, 388 actual VAD observations**, zero retries. Keep all raw baselines, rejected speech and admitted negatives visible. PASS requires all100boosted decisions match the frozen coarse expectations, zero false admission/rejection on these controls, complete provenance/replay/cleanup and unchanged old evidence. No altered labels, second gain choice, result-dependent threshold tuning, dropped rows or rerun. A failure remains a failure.

CPU offline original VAD namespace/CPU0,1/thread limits/3GiB virtual cap/14GiB MemAvailable before each load/180second worker deadline; native phase≤900seconds and new root≤128MiB. No ASR/CORE/TTS inference, new weights/packages, shared services, Vault/database/Docker/provider changes. Validate actual cap from the launch command; generic evaluator headroom metadata is not the VAD address-space limit. Preserve all native events and source snapshots. Actual-view results traverse the optional adapter/original pipeline with explicitly synthetic downstream sentinels, never relabelled as native full-workflow acceptance.

The first preparation wrote134.183MiB and was refused before any native load. Keep its files/log/source version as a failed preparation, not a model-quality observation. The corrected preparation uses a distinct exclusive root and omits redundant PCM storage: raw float samples are exact multiples of1/32768, so reconstruct signed16-bit values only if finite/integer/in-range and reverify the original normalized PCM hash. No lossy compression, source change, sample removal or cap increase. Check projected bytes before each input write.

## Consequences, dependencies and rollback

P1, one implementation/control and bounded comparison milestone. Dependencies: retained ADR166 failures/probabilities, pinned existing VAD/runtime, source/clock contracts and fixed validation panel. Risks: amplified noise/DC, short/quiet speech losses, inherited labels, reused-corpus overfit and view/source mismatch. Tests cover numeric boundaries, full PCM preservation, invalid evidence, audit failure, cancellation, finite budgets and first-failure preservation. Rollback omits only the optional detector-view adapter; no migration or product cutover. A later native ASR/CORE/TTS integration remains separate and must preserve the original failed48turn scores. Max4second/device/rights/model/default/product gates remain OPEN; D60 deferred, pronunciation cycles stopped, D90 NOT RELEASED.
