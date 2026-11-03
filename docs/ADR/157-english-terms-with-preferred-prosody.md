# ADR 157 — English terms with the owner-preferred prosody path

**Purpose:** Correct the experimental Vietnamese pronunciation substitution while preserving the date/prosody behavior the owner just preferred.

**Status:** ACCEPTED FOR CONTINUING THE OWNER-REQUESTED QUALITY FIX; NOT PRODUCT ACTIVATION OR ADR-155 WORKFLOW RECOVERY. The earlier “Làm đi” requested fixes and new comparison clips; the latest [feedback](../evidence/d74-reading-quality-owner-followup.json) narrows that ongoing work: English pronunciation for Python and API, with API buzz/tremble unresolved in both voices. No new model is proposed or downloaded. [Execution authorization interpretation](../evidence/d74-english-reading-authorization.json) records the limited engineering scope, not an invented owner-specified call count.

## Context and accepted behavior

The owner confirms date/time reading is correct on the reviewed panel and prefers `clauses` as best/most natural. Preserve all ten ADR-156 files, its48 clips and source/SDK weights. The former lexicon “pai thờn”/“ây pi ai” was explicitly experimental; it does not meet the now clarified English-pronunciation requirement. Do not alter the old evidence to hide this unsuccessful choice.

Clip-level numeric inspection of existing target cases shows no samples outside±1 or at digital full scale. That does not rule out perceptual buzz/tremble, localize the fault to API, or certify acceptable audio. Do not suppress the reported defect with gain changes, denoising, sample replacement or trimming.

## Decision

Add a new input-only research renderer that reuses the existing `clauses` rendering trace and removes only edits of kind `lexicon`. Preserve the original English tokens, date/time edits, sentence boundaries, question punctuation, original displayed text and protected-code rules. Feed the resulting text into the exact original owner-preferred worker/ProsodyAdapter without modifying their files, sampling, frame caps, voice, precision or codec.

Before neural execution, use the existing SDK in a sealed model-free namespace to inspect normalized text, English reference phonemes and token coverage. The namespace exposes only the approved text tokenizer JSON, not neural weights. Require both English references in the requested contexts and zero unknown tokens; this is a frontend check, not acoustic quality acceptance.

Generate one small new candidate panel: four fixed sentences ×two existing voices =eight TTS requests, maximum eight original inner chunks per request, zero retries/ASR/CORE/downloads/packages. Two sentences repeat the old targeted input for a new-policy comparison; two are new diagnostic/control cases, including the accepted date/time behavior. Borrow the old best four target audio outputs as the unchanged listening baseline; do not regenerate them or average away prior failures.

Retain existing CPU affinity0,1/two threads; AS8GiB/TTS sampled RSS2GiB/aggregate8GiB/MemAvailable≥14GiB, worker/panel≤600seconds and the same parent-root≤8GiB. Freeze new code/tests, owner requirement, software results, frontend proof, corpus/render traces and unchanged preferred-operator hashes before native calls. Stop/join on first failure, retain all unattempted slots. No extra retry or model/backend fallback is implied.

## Acceptance, priority and rollback

P1 VOICE-ENGLISH-READING-001 and VOICE-API-ARTIFACT-001 before quality acceptance. Dependencies: owner English requirement, preserved accepted date/prosody behavior, exact SDK/preset/tokenizer provenance, tested frontend/runner and resource headroom. Effort: one bounded correction/investigation and eight-clip review milestone. Risks: the existing acoustic model may still mispronounce English despite correct phonemes; phoneme correctness and absence of clipping do not prove absence of API buzz; a new policy may match old raw audio rather than improve it. Record those outcomes honestly.

Owner listening must confirm English pronunciation and whether API buzz/tremble is gone. Keep the previously accepted date/time/preferred-prosody findings separate from remaining English defects. No new voice/model selection, product activation, guaranteed four-second timing, waveform repair, workflow recovery or shared-service change is authorized. Rollback disables only this new input policy, retaining the exact old preferred path and every output. D74 broader quality/rights/no-speech/physical timing and D90 release remain open; D60 stays owner-deferred.
