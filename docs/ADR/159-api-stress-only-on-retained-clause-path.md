# ADR 159 — API stress pattern on the retained clause path

**Purpose:** Test a source-backed, term-only hypothesis after the owner rejected the different-text reference diagnostic.

**Status:** Owner-requested research under the latest “Làm đi”, not product/model selection or ADR-155 recovery. Preserve ADR-158 and its group rejection. No new model, package or external service.

## Hypothesis and fixed comparison

The pinned SDK dictionary emits API as `ˌeɪpˌiːˈaɪ`, whereas the retained sentence frontend emits `ˈeɪ pˈiː ˈaɪ`. Multiple primary stresses may contribute to the unacceptable acronym realization. This is an unverified hypothesis; correct vowel symbols and a native dictionary stress pattern do not establish audible English A.

Keep the exact ADR-157 English-preserving text renderer, original ProsodyAdapter, sentence boundaries, gaps, question punctuation, Python pronunciation, date/time reading, reference codes, speaker presets and sampling. Wrap only the phonemizer dependency: replace the single API span `ˈeɪ pˈiː ˈaɪ` with `ˌeɪ pˌiː ˈaɪ`. Spaces and vowel/consonant symbols remain identical. This borrows only the dictionary stress hierarchy; it does not reuse the compact standalone control or ref-off path. Both first-letter and P stress change as one declared pattern; no separate causal claim for either character.

Use exactly the earlier `english-01` and `english-04` source sentences for both Trúc Ly and Ngọc Huyền. Four new requests, with the four exact original ADR-157 outputs as retained baselines, not regenerated. Expect respectively one and two chunks, six inner generations total. Retain the identical first date/time chunk as a preservation control. The baseline was not accepted for English/API quality; its clause/date behavior is the preserved path, not a previously successful API fix.

Model-free probe must bind every source/rendered text, ordered chunk, gap, original/changed phonemes and token roundtrip. Require exactly one API span per request, no other phone changes, unchanged character length, syllable count and original computed frame cap, zero unknown tokens and preserved punctuation. Refuse neural execution if any check fails. Actual native trace must match the frozen probe and original baseline trace for all unchanged chunks/gaps; verify preserved first date chunk byte-for-byte after synthesis.

## Limits and stopping

New files only; preserve all25 prior research source/test files,750 application/210 protected files, all prior audio and frozen protocols. One CPU worker, affinity0,1/two threads, AS8GiB/TTS sampled RSS2GiB/aggregate8GiB/headroom14GiB before load/root8GiB; worker and panel≤120seconds, original frame caps/absolute300 unchanged. Four TTS/six inner generations maximum, zero retries/ASR/CORE/provider calls/downloads. Stop/join at first completeness/provenance/resource/cleanup failure; retain failed and unattempted rows. This is a new four-request scope, not reuse of ADR-158's spare slots.

Freeze source/tests, tested software, probe, authority and exact baseline hashes before loading. Store genuine native outputs/chunks without waveform repair. Publish all four slots beside their retained baseline, including failures/missing clips. Owner listening is the quality gate; reject the policy if it is worse or still wrong. Do not claim that EOS, token identity or software PASS establish naturalness, correct Ei or absence of buzz.

## Priority, dependencies, risk and rollback

P1 under VOICE-ENGLISH-READING-001/VOICE-API-ARTIFACT-001. Dependencies: unchanged original clauses/English inputs and same SDK, native dictionary/probe verification, tests and resource guard. Effort: one bounded four-clip comparison milestone. Risks: weaker stresses worsen intelligibility; model realization remains wrong; repeated authored stimuli overfit; term changes affect subsequent sampling despite unchanged parameters. No universal code-switch or final voice/model approval follows.

Rollback rejects this optional experimental phonemizer and joins only its worker, preserving originals and every failed observation. No product cutover occurs. Python remains separately open; accepted date/time/clause findings stand. ADR-155 workflow, physical first-audible4seconds, rights/no-speech, model/voice/product/D90 release stay open; D60 owner-deferred.
