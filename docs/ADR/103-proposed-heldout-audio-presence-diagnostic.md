# ADR 103 — Proposed held-out factual audio-presence diagnostic

**Purpose:** Distinguish the failed multi-field reviewer task from a minimal factual audio task without repairing old results, claiming naturalness or replacing agreed models.

**Date:** 2026-10-22. **Status: PROPOSED, EXECUTION NOT APPROVED.** ADR-102 permits load/integrity only. New `prepare-diagnose`/`diagnose` entry points remain blocked until an explicit decision; original `qualify`/`review` remain blocked regardless of this proposal. No new real diagnostic packet or inference is prepared before approval.

## Evidence and hypothesis

The original nine first-turn responses contain Python-style dictionaries and factual speech claims on exact silence/noise. EOS repair preserved all first-turn tokens, so a serialization fix alone cannot qualify this reviewer. Readonly source inspection found no new conditioning bug: the native SDK selects valid audio frames through the supplied mask. Pread memory-only loading now passes within12GiB, but actual audio inference fit is unmeasured.

Hypothesis, not a demonstrated remedy: a short factual question may reveal whether the original3B checkpoint distinguishes speech from no speech when the multi-field JSON/naturalness task is removed. This is one separately preregistered diagnostic candidate, not tuning the old qualification into PASS. Success cannot qualify the reviewer or satisfy the auditory naturalness AC.

## Frozen proposed task

Use the same original model/revision/SDK/CPU-BF16/native processor/EOS/seed7 with the exact existing system instruction. The only diagnostic question is:

> Does this audio contain any intelligible human speech? Answer exactly yes, no, or uncertain.

Maximum16new tokens, greedy, one response per case, no response repair, retries, alternative prompt or label changes. Only surrounding whitespace may be removed for the exact lowercase labels `yes`, `no`, `uncertain`; retain raw text/tokens/features/source and real EOS. Unknown/invalid/capped/wrong responses prevent diagnostic PASS. `uncertain` is retained as uncertainty and does not match either known yes/no expectation.

Four controls, never sent to the previous local reviewer:

| Source | Expected factual answer | Original provenance |
| --- | --- | --- |
| Existing complete16k public FLEURS `en_us-0001`,126720samples | yes | SHA256 `ba28baf3162a91509342ddbd17f5dc906e664c65dfa0693bd55aa4fcd3ad5273` |
| Existing complete16k public FLEURS `vi_vn-0001`,148800samples | yes | SHA256 `8cf49bc6f5f2e54188db71944091fd25ebf09eb1d3aeeadd6ff8412a301d4d15` |
| Authored exact zeros,60000float32samples at16k | no |3.75seconds; no synthesis or download |
| Authored Gaussian noise,60000samples, NumPy default_rng seed102, mean0/std0.05 | no | Separate deterministic float32 signal; reject amplitude overflow rather than normalizing/retrying |

Predeclare opaque shuffled order with NumPy default_rng seed103. Source hashes/counts and expected answers stay parent-only; worker gets opaque IDs/hash/count only. No transcript, language, expected response, filename hint or candidate24output is mounted. Keep full speech sample bits and complete timeline; no resampling, clipping, gain adjustment, new weights or speech synthesis. All originals and every old label/failure stay unchanged. Diagnostic arrays/publication are exclusive/private and must be frozen before inference.

## Bounds and approval

Only after an explicit approval may this add `prepare-diagnose` and `diagnose` to the shared mode policy. Prepare one separate packet, then one owned worker for all four cases. Keep12GiB virtual cap,14GiB sampled host preflight before preparation/launch, CORE loaded/same identity/recovery, CPU2/interop1/affinity0,1,600second wall/1200CPU,128MiB tmpfs and no network/credentials/GPU. Capture failure resources. No cap/headroom change, automatic second candidate, larger model, download, parser coercion or review24outputs. Stop after this fixed packet; any missing/incorrect/uncertain response leaves the diagnostic failed. An allocator/native failure terminates the owned process and preserves partial events.

## Priority, effort, risk and rollback

**AUDIO-EVAL-PRESENCE-DIAG-001, P1 diagnostic dependency research, proposed only.** One preparation/test/first-response milestone; depends on owner approval, held-out provenance, tests, original artifacts/SDK and qualified12GiB inference execution. Risks: prompt sensitivity, hallucinated speech, allocation exceeding12GiB during features/generation, confusing factual competence with quality judgement and outcome-driven retries. Preserve raw first results and all old failures; fail closed rather than substitute a score.

Rollback disables only the two diagnostic modes and joins the owned worker. No production source/model/default/data/database/service/Vault/Docker changes. Even4/4factual answers provide **no naturalness qualification, MOS, model-selection approval, D70 closure or D71 advance**. The next auditory-quality protocol still needs justified controls and retained first failures; this diagnostic is not a replacement AC.
