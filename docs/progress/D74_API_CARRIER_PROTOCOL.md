# D74 — Carrier-context follow-up after the stopped short-letter diagnostic

**Purpose:** Continue the requested API investigation with a separately declared complete-sentence cohort while preserving the failed isolated-letter result, original caps and total actual-request ceiling.

## First cohort disposition

The ADR-158 cohort remains STOPPED_NO_RETRY:5attempts of16declared slots,4complete Trúc Ly outputs,1Ngọc Huyền isolated-A output without EOS,11unattempted. The failed generation used13frames, exactly the existing short-utterance cap, with no EOS; it is not published as complete speech. Reference-off was not reached, so the first cohort does not test the reference hypothesis or prove it false.

This short-control failure is separate from the earlier owner-reported API pronunciation defect: the earlier eight contextual clips ended with EOS. Do not infer that the earlier A-versus-Ei complaint was caused by this later short-control cap.

## New declared cohort and authority

The owner's latest “Làm đi” requests finding a way to address the API defect. This continuation uses **eight new requests**, within the unused actual16-request investigation ceiling; it does not retry standalone A, raise caps, resume/relabel the stopped cohort or replace its11unattempted rows. [Authority receipt](../evidence/d74-api-context-authorization.json). Two new carrier sentences ×two retained voices ×reference on/off =8separate slots. With the initial5attempts, maximum actual total is13of16. No further automatic native study is scheduled.

The Vietnamese carrier is a full natural diagnostic sentence; the English carrier explicitly asks for the letter sequence. Their phonemes are frozen before generation. The English carrier uses G2P for “please say” followed by the known English letter phones; it is a declared new stimulus, not padding or repairing the failed A output, and cannot establish that standalone A now passes.

A model-free probe requires exact token roundtrip,0unknown tokens, the English API reference, more than4syllables and the original computed frame cap greater than13. Actual probe values: Vietnamese13syllables/cap156frames; English5syllables/cap74frames. The same original `max_expected_frames` function and absolute300frame limit apply, unchanged. These larger per-sentence values come from natural utterance length, not a raised parameter or loosened guard.

## Controls, limits and reporting

Reuse the exact frozen ADR-158 worker: same weights, precision, speaker embedding/projected anchor, text token IDs, seed7/sampling/frame caps/style/codec. Only reference-code admission differs within each pair. Keep source/preset hashes and actual prompt audits. Human-perceived timbre can still differ and must be reviewed.

Retain CPU0,1/two threads/AS8GiB/TTS sampled RSS2GiB/aggregate8GiB/headroom14GiB/parent-root8GiB; the new cohort has a stricter120second native wall deadline. Both cohorts' actual worker times remain reported separately and below the original600second allowance. Stop again at the first failure and preserve new unattempted rows. No retry, ASR/CORE, new model/package, model/default change, shared-service action, audio repair or ADR-155 workflow is included.

Keep the cohorts separate in artifacts, counts and conclusions. New generated speech needs owner listening for Ei versus A, API buzz/run and voice quality. Different hashes or exact speaker inputs do not establish acoustic success. Accepted date/prosody and all prior model choices/audio remain unchanged; no promotion or release.

P1 dependency of the existing English/API quality tasks. Effort: one bounded8-clip follow-up and paired audit/listening milestone. Risks: carrier effects do not generalize to an isolated letter; dropping references changes perceived voice; correct phonemes still sound wrong; adaptive technical follow-up is not an independent unseen quality benchmark. Rollback retires only owned workers, restores native/container baseline and retains all first failures. Further scope requires a new reviewed plan, not consuming spare slots implicitly.
