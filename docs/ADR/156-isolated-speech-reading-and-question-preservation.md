# ADR 156 — Isolated speech rendering and question-preserving comparison

**Purpose:** Address the owner's reported reading/prosody issues through a separate research adapter and paired audio, without changing agreed models, product responses or historical results.

**Status:** ACCEPTED FOR OWNER-REQUESTED RESEARCH IMPLEMENTATION AND ONE NEW PAIRED PANEL; NOT PRODUCT ACTIVATION. The owner said “Làm đi” after the concrete proposal to investigate/fix time/date and Python/API reading, examine prosody on existing voices, then create new comparative clips. [Authorization receipt](../evidence/d74-reading-quality-owner-authorization.json). This authorizes this quality work; it does not authorize the separately deferred ADR-155 workflow recovery.

## Findings before neural execution

The pinned `sea-g2p`/SDK already expands the original date/time case to correct written Vietnamese and supplies English phonemes for Python/API. Therefore there is no evidence that missing normalization alone explains the owner's heard errors. A dictionary rewrite can be redundant or worse and must be compared, not declared a fix.

A model-free diagnostic confirms a specific defect: “Bạn đồng ý chứ?” is normalized into a chunk ending in a period; its final phoneme punctuation also loses the question mark. The high-level Turbo path always enables `punc_norm` for short chunks. The pinned `style` argument is deprecated/ignored; `silence_p` does not control the v3 gap-based path. Do not claim those knobs fix naturalness.

An initial64-character packing diagnostic split a spelled time between “mười lăm” and “phút”; it was rejected before any native call. Preserve the diagnostic. The final variant keeps a complete normalized sentence/clause together, at most256 characters each/eight chunks, refusing longer clauses instead of splitting time/date phrases arbitrarily.

## Decision and architecture

Implement only under `benchmarks/`, with tests. Keep the displayed/original answer immutable. A pure speech renderer produces separate spoken text, original UTF8 hashes, character-offset edit trace and its measured cost. Only explicitly contextual VI times, `ngày DD/MM[/YYYY]` with calendar validation, and exact standalone Python/API tokens are rewritten. Protect code, URLs, paths, emails and compound identifiers; unsupported/ambiguous formats remain unchanged. Day/month order, Northern number conventions and “pai thờn”/“ây pi ai” are experimental conventions, not independently approved phonetic truth.

Compare three preregistered profiles on8 authored diagnostic sentences and both existing Trúc Ly/Ngọc Huyền presets:

1. `raw`: unchanged new text through the original high-level SDK.
2. `reading`: speech-only rendering through the same original SDK/settings.
3. `clauses`: the same reading policy, semicolons as sentence boundaries, one sentence/clause per chunk, and question-preserving normalization/G2P with `punc_norm=False`. Feed these phonemes through the original engine's existing `infer(phonemes=...)` API. Use the same original preset resolver, sampling, frame caps, codec, watermark behavior and join function. Retain native chunk bytes/hashes as well as the complete output.

No SDK file or global SDK function is patched. The third profile is an explicit composite research variant, not evidence that one individual intervention caused a preference. The existing model weights/CPU precision/voices and original seven research files remain unchanged; product VoicePipeline, recorder/API, model/default configuration, Vault/database/Docker and search provider are untouched.

## Execution boundaries and interpretation

One new panel has48 top-level TTS requests, at most8 inner chunk generations each, no retry. No ASR/CORE requests, workflow48-slot recovery, new weights/packages, remote audio, microphone, speed changes, streaming or model selection. Keep all failed/unattempted rows; stop on software/provenance/resource/native-completeness/cleanup failure. Two model-free diagnostic runs and a final sentence-preserving probe are separate observations, not TTS calls or retries.

Reuse the exact existing namespace/resource controls: CPU affinity0,1/two threads; AS8 GiB, sampled TTS RSS2 GiB/aggregate8 GiB, MemAvailable≥14 GiB before load; worker≤600 s, new panel≤1800 s. Existing parent root including all prior SDK/cache/results and new clips stays≤8 GiB. Source, tests, authorization, corpus/rendered inputs, pinned assets and diagnostic hashes are frozen after software tests and before neural execution. The original24 audio, first failed workflow, owner feedback and ADR-155 plan remain immutable.

Software/probe success is not naturalness or pronunciation acceptance. Preserve question marks and written numbers deterministically, but owner listening must determine whether the generated speech improves or still fails. Report identical raw/reading outputs honestly. Rendering cost is measured separately; TTS-only latency does not establish the physical first-audible≤4-second requirement. No independent MOS/holdout generalization, new owner ratings or deployment rights are fabricated.

## Priority, dependencies, effort and rollback

P1 VOICE-TEXT-READING-001 and VOICE-PROSODY-001. Dependencies: exact existing SDK/preset provenance, owner request, tested renderer/adapter/lifecycle, model-free evidence and headroom. Effort: one implementation/investigation milestone plus one bounded panel/review milestone; native wall cap30 minutes. Risks: Vietnamese approximation worsens English accuracy, dates already normalized need acoustic fixes, punctuation/chunk changes affect tone/latency/EOS, protected-token rules have limited scope, and one person's small-panel preference does not establish broad quality.

Rollback disables the unregistered adapter, returns to the original raw SDK path, stops/joins only owned namespaces, verifies original source/runtime baseline and retains every result. No product migration occurs. ADR-155 remains NOT APPROVED/NOT EXECUTED; D74 product/voice/rights/no-speech/physical latency and D90 release remain OPEN. D60 stays owner-deferred.
