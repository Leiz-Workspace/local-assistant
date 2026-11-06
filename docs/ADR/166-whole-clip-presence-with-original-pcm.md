# ADR 166 — Whole-clip speech presence with original PCM

**Purpose:** Address AUDIO-VAD-ASR-001 after ADR165 observed 16/16 false replies on two repeated no-speech sources, without changing the agreed models or activating the rejected concatenating VAD policy.

**Status:** Research implementation and one finite VAD-only measurement authorized by the owner's continuation request after the ADR165 result. No product gate/default or further ASR/CORE/TTS campaign is authorized by this decision.

## Decision and rationale

Retain the existing pinned official Silero v5.0 detector, commit `5cd2ba54db059f961e7545d4f211b44f005a6dfb`, original threshold 0.5, 250 ms minimum speech, 100 ms minimum silence and 30 ms padding. A nonempty, valid segmentation admits the **entire unchanged NormalizedAudio object** to the original ASR. An empty valid segmentation returns the original source-bound empty transcript so the unchanged VoicePipeline raises `no_speech` before CORE/TTS. Never concatenate intervals, trim silence, pad ASR input, adjust gain, rewrite recognition text or substitute a model. Invalid/incomplete detector evidence raises an explicit failure rather than pretending to detect silence or falling back to raw ASR.

The optional research adapter binds evidence to owner, source/PCM hash, count, rational clock, exact detector identity and ordered sample bounds. Admission remains exclusive through joined cancellation, timeout and shutdown. Model workers remain externally owned. Existing application code/configuration and all passing implementations remain byte-identical. This distinguishes whole-clip admission from the old D72 concatenation, which worsened recognition on some VI/EN cohorts.

## Preregistered finite evaluation

Use all 47 retained D72 inputs: 40 unique upstream-labelled speech recordings (20 VI/20 EN), five authored negatives and two padded repeats. Normalize through the original PCM port and verify the six D74 ASR input float hashes exactly. This is a reused diagnostic panel, not a new independent holdout. Add six derived controls: the first eligible speech source per language in retained order, with full-recording PCM gains 0.5, 0.1 and 0.03, round-to-nearest. These are separate authored robustness controls with inherited coarse speech-presence expectations, not independent recordings, human-verified audibility or word-boundary labels. Gain changes apply only when creating these declared new test controls; admitted original audio is never changed by the adapter.

Run the **unchanged** original VAD worker once on the 47 recordings in forward/reverse order (94 observations), then six single-case `smoke` workers for the quiet derivatives: maximum seven loads / 100 VAD observations / zero retries. Worker namespaces are offline, CPU 0/1 with the original thread limits, 3 GiB virtual-address cap, 180-second worker deadline and 14 GiB MemAvailable preflight. The complete native phase is capped at 900 seconds and the new artifact root at 128 MiB. No new downloads or ASR/CORE/TTS inference, context/resource-cap changes, shared-service operations, credentials or database access.

Reconcile source hashes, complete coverage, original model probabilities, exact recurrence replay, native worker retirement and baseline. Feed only the measured detector evidence into the real optional adapter/original pipeline with explicitly synthetic downstream sentinels; verify zero downstream calls on refusals and identical full PCM/clocks on admission. Sentinel tests are not native ASR accuracy, a new 48-turn workflow, latency acceptance or a count of genuinely independent negative examples. Preserve every rejection/failure; do not tune thresholds, select outputs, rerun or label rejected quiet speech as silence.

## Priority, consequences and rollback

P1 before product activation. Dependencies: ADR165 first outcomes, D72 original detector/source artifacts, original voice pipeline contracts, tested adapter and source-bound finite operator. Effort: one design/control and bounded measurement milestone; a later native full-workflow/device milestone remains separate. Risks: rejecting short/quiet speech, inherited labels, reused-panel overfit, VAD startup/CPU latency and stale/mismatched evidence. Full PCM preservation removes concatenation from this candidate but does not prove semantic accuracy or general sensitivity.

Rollback omits the optional research wrapper and retires only its owned calls. No deployment or migration occurs. Keep ADR165 failures, every previous source/artifact, existing models/voices/defaults and both stopped pronunciation cycles. Report no-speech quality and physical maximum-four-second acceptance separately; D74 product/rights/default/model/device gates stay OPEN, D60 owner-deferred and D90 NOT RELEASED.
