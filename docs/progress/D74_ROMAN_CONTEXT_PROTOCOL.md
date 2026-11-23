# D74 — Roman-numeral and Vietnamese-word context verification

**Purpose:** Verify the existing frontend/audio distinguishes Vietnamese `vi` from Roman `VI`, preserve the owner's scoped API pronunciation acceptance and diagnose remaining Python quality without inventing a fix.

**Authority:** The owner explicitly requests this context check after confirming API pronunciation correct and Python still wrong. [Exact feedback](../evidence/d74-api-python-roman-owner-feedback.json). No new model, package, voice selection, product activation or ADR-155 workflow.

## Fixed scope and expected readings

Keep original renderer/normalizer/G2P/ProsodyAdapter, SDK, model, voices, sampling and caps unchanged. No Roman replacement rule is added: test existing behavior first. Four spoken context cases for each retained Trúc Ly/Ngọc Huyền preset:

1. “Hành vi vi phạm này cần được kiểm tra.” — retain both Vietnamese `vi`, never turn them into `sáu`.
2. “VI PHẠM là cụm từ tiếng Việt.” — uppercase Vietnamese phrase, still `vi phạm`.
3. “Chương VI có sáu mục.” — Roman VI must read `sáu`.
4. “CHƯƠNG VI nói về hành vi vi phạm.” — both meanings in one sentence: `chương sáu`, followed by Vietnamese `vi`.

Also generate one full English control per voice: “I write code in Python every day.” Preserve the English Python dictionary phones, without a new pronunciation edit. Reuse the two previous mixed Python/API clips as unchanged references; do not regenerate accepted API clips. An English-only context control cannot establish a causal fix or universal English quality.

Total **10 new TTS requests/10 original inner chunks**, one worker, zero retries. A model-free investigation additionally checks `Chương IV/chương IX`, identifier VI and explicit English-tagged Python. Identifier reading has no owner-defined target; report it as an observation, not automatically correct. Bare versus tagged Python already yields identical frontend phones; do not waste native calls regenerating an identical tag-only candidate.

## Gates and retained boundaries

The no-weights probe uses actual original clause splitting, normalization, G2P and tokenizer. Check exact normalized expectations for the five unambiguous Roman/Vietnamese cases, ordered chunks/gaps/phones, token roundtrip/zero unknowns, original frame caps and Python phoneme equality. Keep ambiguous identifier and unreviewed acoustic fields separate. Bind every native request to that probe and preserve actual EOS/output/chunk hashes.

Use the unchanged original QualityWorker/clauses entry point for the new sentences, which contain no API. The API stress operator is not edited or exercised with missing API inputs. Preserve all29 prior research files, all750 application/210 protected inputs, existing SDK/weights/presets/audio and frozen protocols. Only a new benchmark controller/tests and reports are added; no architectural change or product conversion policy.

CPU0,1/two threads/AS8GiB/TTS sampled RSS2GiB/aggregate8GiB/headroom14GiB before load/root8GiB; panel/worker≤120seconds, existing frame function/absolute300 unchanged. Freeze software/source/protocol/feedback/probe before neural loading; stop/join at the first completeness, provenance, resource or cleanup failure. Keep all10 slots and missing/failed outcomes. Publish genuine WAVs plus exact retained references; do not denoise, trim, repair or relabel audio.

## Priority, dependencies, effort and risk

P1 VOICE-CONTEXT-READING-001, alongside existing Python task. Dependencies: exact owner examples, retained SDK/path, fixed expected text, tests and resource headroom. Effort: one frontend verification and bounded ten-clip milestone. Risks: frontend correctness may still sound wrong; uppercase identifiers and bare Roman letters are ambiguous; five authored contexts cannot establish universal Roman recognition; new English context differs from a mixed-language sentence. Owner listening remains the acoustic gate. Do not tune cases or normalization after seeing results.

Rollback retires only the owned worker and leaves the existing speech paths intact. API pronunciation is accepted only for the previous reviewed panel; Python/APIbuzz/general voice quality, rights/no-speech/physical4second/product/D90 release remain separate gates. D60 deferred; ADR-155 workflow unapproved/unexecuted. If context normalization fails, retain/report the failure and assess a separate correction before generating misleading “fixed” speech.
