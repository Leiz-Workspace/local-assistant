# D74 — XI/xi-măng verification and same-voice bilingual quality

**Purpose:** Extend the owner's accepted VI/vi distinction to XI/xi măng without changing working speech paths, and assess the requirement for accurate Vietnamese and English in one retained voice.

**Authority:** [Owner feedback](../evidence/d74-vi-xi-bilingual-owner-feedback.json) accepts the reviewed VI distinction, rejects the English accent quality and explicitly requests XI checking. No new model, reference audio, package, training, cloning or product activation is authorized by this verification.

## Existing-path XI corpus

Use the original SDK normalizer/G2P/ProsodyAdapter unchanged. Nine frontend cases, five unambiguous expected readings:

1. “Xi măng được dùng để xây nhà.” → xi măng được dùng để xây nhà.
2. “XI MĂNG được dùng để xây nhà.” → xi măng được dùng để xây nhà.
3. “Chương XI có mười một mục.” → chương mười một có mười một mục.
4. “Chương XI nói về xi măng và cách sử dụng.” → chương mười một nói về xi măng và cách sử dụng.
5. “CHƯƠNG XI nói về XI MĂNG.” → chương mười một nói về xi măng.

Identifier XI, bare XI, noncanonical IIX and lowercase identifier xi are observation-only controls, not silently scored as Roman correctness. No added conversion rule, retuned case or normalization repair. Before any neural call require exact normalized expectations, original clause/phone/cap bindings, zero unknown tokens and token roundtrip. Preserve first failures; if any of five targets fails, report the failure and do not generate a claimed successful panel.

Generate only cases1/3/4 for Trúc Ly and Ngọc Huyền: **6requests/6innerchunks**, one original clauses worker. These new sentences contain no API; preserve its accepted stress operator and all31previous research files. Source/code/test/protocol/software/probe freezes precede native load. Keep all6slots and unattempted/failed outcomes.

CPU0,1/two threads/AS8GiB/TTS sampledRSS2GiB/aggregate8GiB/headroom14GiB/root8GiB/wall120seconds, original per-sentence/absolute300frame limits. Zero retries/ASR/CORE/provider calls/downloads. Stop/join on first resource/provenance/completeness/cleanup failure. Preserve raw/WAV and original SDK joining, no waveform repair. Owner listening is the acoustic quality gate, not software/token normalization PASS.

## Bilingual assessment, not a new trial

The publisher describes Turbo as VI/EN bilingual; this does not guarantee native-like pronunciation for the retained presets. The pinned SDK exposes speaker embedding/reference codes and ignores `style`; no verified English-accent switch is exposed in its inference signature. Existing frontend already has English Python phones; adding English tags gave identical phones. The reference-ablation panel was rejected as worse, without per-condition ratings or demonstrated benefit from ref-off. Neither route is an established general accent fix.

Assess VOICE-BILINGUAL-IDENTITY-001 before scheduling: **P1** under the owner's same-voice VI/EN requirement. Dependencies: fixed bilingual/mixed corpus, listening rubric for pronunciation/accent and perceived voice identity, retained presets/rights, resource budget and an explicitly reviewed intervention. Effort: one evaluation-design milestone; data collection/training/migration effort unknown pending feasibility. Risks: changing references alters perceived voice; word-specific fixes overfit; shared phonetic capability does not ensure acoustic accent; extra processing increases latency/RAM. Rollback preserves current voices/API/date/prosody and rejects unaccepted variants.

Possible future research: suitable bilingual reference material from the same speaker, or separately approved adaptation/model comparison if retained capability is inadequate. These are hypotheses needing data/rights, benchmark/performance/resource/migration/rollback analysis and owner approval, not guaranteed solutions. No new reference, model, training or deployment is scheduled here. Existing ref-off failure remains rejected.

Frontend/context task remains P1 with one nine-case/six-clip milestone; broader Roman contexts remain unqualified. D60 deferred; ADR155workflow/physical4second/rights/no-speech/model/voice/product/D90release stay separate gates.
