# ADR 162 — Ngọc Huyền matched-context validation

**Purpose:** Test the existing Ngọc Huyền preset on the exact ten sentences used for Trúc Ly, preserving the accepted Trúc Ly version and all earlier Ngọc Huyền failures.

**Status:** Owner-authorized by “Làm đi” after the separate pending Ngọc Huyền evaluation was explained. This authorizes one bounded TTS-only validation, not another pronunciation-tuning loop or product adoption.

## Decision

Reuse ADR161's frozen no-weights frontend observations, source/rendered text, ordered twelve chunks, question/gap/number/date/Roman semantics, API stress and three US-term edits. Recheck its SHA, original source renderer and semantic checks before execution. These frontend operations are voice-independent; reuse is explicit, not a claim of a new probe. Actual Ngọc Huyền plans must match every frozen chunk before generation. Only the existing preset changes; no model, reference asset, dictionary, sampling, seed, frame allowance, audio repair, download or training changes.

Add a separate Ngọc Huyền-only adapter/runner and tests. Leave the forty previous research source/test files unchanged, including the Trúc Ly-only guard. Reuse original chunk planning, generation/joining, native verification, namespace and owned-worker resource lifecycle. Bind the new read-only packet by SHA and voice at readiness; reject wrong voice, ID, text, repeat or unapproved input. Require measured speaker/reference-code hashes to match the prior Ngọc Huyền US panel, not Trúc Ly. Matching input hashes do not certify perceived identity or correct English.

## Bounds and gates

One worker, at most ten top-level TTS requests and sixteen inner chunks (twelve planned), 120 seconds wall, zero retries. Preserve CPU0,1/two threads/AS8 GiB/TTS sampledRSS2 GiB/aggregate8 GiB/headroom14 GiB/root8 GiB and original min(baseline cap,US cap,300) budgets. No ASR/CORE/Brave, shared-service/config changes or ADR155 workflow recovery. Freeze passing software/source/authority and the packet before load. Stop on first failure, join the worker, preserve failed/unattempted slots; do not retry or enlarge a cap to fill the page.

Keep original Trúc Ly audio/owner acceptance with known unclear English articulation (this heard as “dít”) intact; its refinement cycle is stopped. Preserve Ngọc Huyền's earlier I→i English rejection. New listening results are unknown until reported. Publish genuine complete WAVs in four EN/three mixed/three VI groups, with all missing outcomes visible and no recording, scripts or network. Provide complete new source/test versions and provenance; keep model/default/product/physical4second/rights/no-speech/D90 gates separate.

P1 VOICE-ENGLISH-READING-001 / VOICE-BILINGUAL-IDENTITY-001: dependencies are unchanged accepted policy, frozen same-corpus evidence, existing preset, tested bounded runner and owner listening. Effort one ten-clip evaluation milestone. Risks include repeated I/accent/articulation failures, different perceived identity, conservative-frame failure and a small non-blind authored corpus. Rollback retires the optional worker and leaves all original bytes/presets/defaults untouched. No automatic tuning or voice/model selection follows from the result.
