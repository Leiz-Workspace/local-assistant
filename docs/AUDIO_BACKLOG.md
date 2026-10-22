# Audio and supplied-transcript dependencies

**Purpose:** Assess audio integration and model-evaluation dependencies before their implementation or production activation.

## AUDIO-JOIN-001 Explicit provided-transcript timeline

P1 existing D66, scheduled now after D65 acceptance. Depends on D64/D65 decoded clocks/source ownership, bounded native audio and a source-bound supplied transcript. Effort one native normalization/clock validation/pure timeline join/actual authored composite milestone. Risks: unsupported ASR claims, wrong owner/source/audio, sample-clock offsets/priming/gaps, unverified text injection and treating a muxed test composite as an original captured event. ADR-092 defines source hashes, exact clocks, explicit unverified transcript origin, tests and rollback. No model provision or choice. D66 local scope now PASS73 new/368 related/185 private audit controls and first actual2.994s exact source/PCM/sample/frame join with text recovery. Readonly596-source audit/all580 prior bytes unchanged. Automatic ASR/recording/product delivery remain separate gates; no model provision or benchmark claim.

## AUDIO-ASR-001 Registry ASR comparison and approved integration

P2 existing MODEL-EVAL-003/D68, no download/runtime/selection authorized by this backlog entry. Compare original Qwen3-ASR-0.6B versus Whisper/faster-whisper on the same independently labelled Vietnamese/English speech and silence/noise corpus, preserving first errors and rejected cases. Effort1–2 evaluation milestones plus separately approved deployment. Verify primary model/runtime/license/revision, language/segmentation/token budgets, WER/CER and silence hallucinations, timestamp support limits, cold/warm latency and RAM/VRAM/CPU/storage/CORE impact before recommending a choice. Risks: a tiny English provided-reference fixture masquerading as a bilingual ASR benchmark, unequal precision/threads/hardware, new timestamp model assumed selected, recording without consent and replacing registry roles without approval. D66 supplied transcript success does not satisfy any ASR benchmark. State NOT EVALUATED; model/config cutover needs owner's explicit approval after benchmark, migration and rollback review.

## AUDIO-PROD-001 Authenticated media/consent/delivery lifecycle

P1 before public/runtime voice/video API/UI. Depends on VISION-PROD-001, explicit recording consent/stop, owned ready-file capabilities and D71–D74 retention/delete/error/resource gates. Effort one route/delivery/consent integration milestone plus end-to-end validation. Risks: arbitrary paths/URLs/principal fields, automatic recording, audio/text persistence, cross-owner leakage, locks released before decoder/model/client delivery cancellation acknowledgment and unreviewed model selection. Preserve default-off local boundaries until those gates pass; no microphone/server/model activation from D66.
