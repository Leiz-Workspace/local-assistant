# ADR 097 — Proposed separation of TTS measurement and auditory acceptance

**Purpose:** Make the exact proposed scheduling change reviewable when D70's original auditory criterion cannot be executed by the available tool, without claiming naturalness, selecting a model or silently advancing the roadmap.

**Date:** 2026-10-22. **Status: REJECTED by owner on 2026-10-22 — NOT APPLIED.** D70 currently remains IN PROGRESS and D71 has not started.

**Later owner decision2026-10-23:** [ADR-111](111-owner-deferred-tts-listening-and-explicit-recording.md) records explicit permission to defer listening to a later owner test and begin D71. It supersedes this ADR's scheduling prohibition. The rejection and observations below remain historical; this proposal is not retroactively relabelled accepted. D70 naturalness is still unaccepted.

## Owner decision — 2026-10-22

The owner chose: **“Giữ nguyên AC, chờ khả năng nghe”** (retain the existing Acceptance Criteria and wait for audio inspection capability). The proposed milestone split and permission to begin D71 are rejected. D70 remains IN PROGRESS with actual auditory review required at D70; D71 remains unstarted. Preserve all24first native waveforms, listening copies and null review labels. Do not replace hearing with ASR/acoustic metrics, rerun synthesis to select better outputs, alter any model or reopen the rejected proposal without new owner direction.

The proposal below is retained as decision history, not an active approval request. Resume the unmet auditory criterion when genuine inspection capability becomes available; no continuous monitoring or background work is claimed.

## Observed constraint

D70 source `7ff5438` completed30first attempts,24native waveforms,24reference-blind ASR roundtrips, measured CPU latency/RSS and readonly624-source/original-model/data/runtime integrity.118new/436related and34auditor controls PASS. Qwen explicit Vietnamese is unsupported; VI-text/Auto is a separate diagnostic, not a supported-language claim. No model selected or deployed.

ADR-096 and the current D70 gate require actual emitted-audio inspection for naturalness. The tool returned `audio content omitted because you do not support audio input` for an actual qualified smoke listening copy. The available tools cannot perform that inspection; ASR/acoustic proxies do not replace it. The owner instructed that the next milestone must not begin while current Acceptance Criteria are unmet. Continuing generic project work is not interpreted as permission to remove this criterion.

The current [report](../D70_OFFLINE_TTS_COMPARISON.md), [measurement status](../evidence/d70-tts-measurement-status.json), [readonly audit](../evidence/d70-tts-readonly-measurement-audit.json), [complete playable packet](../../data/backups/d70-tts-listening-review/index.html) and pending JSON make the result and missing criterion concrete. Every listening judgement is still null; nobody is represented as having listened.

## Exact proposed change, only if approved

1. Close D70 **only as the completed offline machine-measurement/capability/license-assessment scope** with all first observations and licensing limitations retained. Never relabel it as naturalness PASS, supported Vietnamese Qwen, model selection or production acceptance.
2. Carry the unchanged actual-audio criterion into `AUDIO-TTS-NATURALNESS-001`, a mandatory gate **before D72 voice integration, model/voice selection or deployment**. The existing native/preview hashes, first results and protocol remain authoritative. Reuse the retained24outputs once an audio-capable tool or reviewer is available; do not rerun synthesis to pick better audio.
3. Allow D71's independent explicit recording/stop/cancel foundation and tests to proceed without a TTS default, TTS deployment or background recording. Actual recording remains subject to the product's explicit user recording controls.
4. Keep Piper VI upstream licensing verification, owner-approved model choice and `AUDIO-VAD-ASR-001` as separate prerequisites before D72/deployment. Do not replace any registry nomination, source, service, data or earlier acceptance.

The owner rejected all four proposed scheduling/acceptance changes. Existing D70/D71 statuses and AC remain in force: keep D70 open until actual audio inspection becomes possible and do not begin D71.

## Priority, dependencies, effort and risk

`AUDIO-TTS-NATURALNESS-001` is P1 before product voice integration; about half to one review milestone for24complete waveforms, provenance checks, per-output pronunciation/prosody/artifact notes and a comparison with uncertainty. Dependencies are genuine audio inspection capability, the frozen first native/preview packet and accurate reviewer provenance. Same-agent listening must be labelled; it is not independent human MOS. Licensing work is tracked separately and cannot be waived by a good listening result.

Risk: deferred quality work is forgotten, proxy scores get called naturalness, a nonstandard-language diagnostic becomes a default, or model/engine/voice licenses are conflated. The proposed hard D72/selection/deployment gate prevents those shortcuts; no model is chosen by this ADR. This is a schedule/acceptance-boundary proposal, not an implementation or production architecture change.

## Compatibility, migration and rollback

No runtime/data/config/model migration accompanies either option. Existing services, CORE/model roles, candidate SDKs/artifacts and first evidence stay unchanged. If the proposal is rejected, keep D70 open and D71 unstarted; no technical rollback is needed. If approved, preserve the explicit approval and previous status, record the split honestly in roadmap/backlog/dev_log, and retain the unresolved auditory/license/model gates before D72. Reverting the schedule returns the milestone to the current open state; it never deletes evidence or changes a model.
