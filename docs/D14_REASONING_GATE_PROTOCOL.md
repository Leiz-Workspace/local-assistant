# D14 — Fresh full bounded-reasoning gate

**Purpose:** Preregister complete local validation of the optional reasoning adapter after the paired text signal and token-validator correction.

Date:2026-10-26. FROZEN BEFORE FIRST FULL-GATE MODEL LOAD. [ADR-136](ADR/136-opt-in-bounded-reasoning-profile-decoding.md). Original D14 and the invalid first diagnostic remain immutable.

## Fresh corpus and policy

42new questions/profile: reasoning8, Python8, source-policy8, Vietnamese6, image5, near32Kretrieval4, stream3. New arithmetic/variables/source labels/text, neutral images, PINEcodes and sequence8through39 differ from previous scored inputs. Three stream cases are planned replicates, not retries. Trusted unit calculations independently verify references; images are visually checked before inference. Avoid ambiguous ellipse/oval labels: the fresh shapes are a blue circle and orange triangle.

Source labels and text are legitimate untrusted evidence, never hidden gold. Explicit atomic-label requirements apply uniformly. The model receives no expected field, expected enum/const/default/description or computed oracle feedback. Schemas contain only trusted structural types/fields/size bounds. Final answers must be complete strict typed JSON with exact expected values, no normalization/extraction/repair or model-generated code execution.

The optional adapter sends unchanged existing profile aliases/system templates, temperature0/cacheFalse and native shape grammar, with max1024including thinking and final answer, reasoning budget512, enable_thinkingTrue and separated reasoning_formatdeepseek. Require observed native reasoning in nonstream and stream. Both final output and request/response bytes stay unchanged. The research validator's512/1024mismatch is fixed and boundary-tested before this load; previous rejected first rows stay rejected in history.

## Gates and runtime

Require42/42schema-valid and42/42whole-answer exact first responses per profile. Missing, unsupported, truncated, malformed, wrong or unmeasured cases remain failures within42. Require source/model/schema/native reasoning identity,30000–32000native prompt tokens for context, and prompt+1024<=32768. Then require actual native cancellation/slot retirement, exit0/reaped/no resource guard, all five distinct provenance checks and exact initial/final baseline. Use the reviewed shared acceptance policy; no new lower threshold. Complete execution alone is not PASS.

Two sequential owned18080GPU workers, original models/projectors/runtime and configured32K/GPU99/thread2/batch512/ubatch128/reasoningoff/offline; request-local override only. Retain14GiBpreflight RAM/GPUfree and sampledRSS12GiB/VRAM14GiB/hostavailable4GiB/freeGPU512MiB;90srequest/2400scampaign,20sTERM/10sKILL. Resource-release wait30sbetween workers is not a load/generation retry. Maximum84scored generations plus2planned nativecancel streams. No old-question reruns, automatic fallback, second model selection, service changes or downloads.

## Freeze and disposition

Freeze source/tests, protocol/ADR, complete cases/PNGhashes, original weights/runtime/provenance, current732-file application manifest and all730prior-file retention before first load. Run once: `uv run --no-sync python -m benchmarks.scripts.d14_reasoning_gate`. An existing execution receipt refuses another run. Store all first artifacts under `data/backups/d14-reasoning-gate-20261026` and publish a separate offline verification, followed by roadmap/devlog/backlog and full-code delivery.

A passing result qualifies only this optional local42-case path. Original full-suite5674/728files stays historical; no full732claim, default/model/production/release adoption or D70hearing completion. If any case fails, retain it and keep the new gate FAIL; diagnose without silently replaying these cases or lowering criteria.
