# ADR 163 — Ngọc Huyền API dictionary-boundary trial

**Purpose:** Test a single source-backed API grouping hypothesis after the owner hears “E - Pe-I, A - Pe - I”, preserving accepted Trúc Ly and all Ngọc Huyền failures.

**Status:** One bounded continuation of the owner-requested Ngọc Huyền repair investigation. Same model/preset/reference assets; no product adoption or ADR155 workflow recovery.

## Hypothesis and exact comparison

The retained actual mixed-sentence API input is `ˌeɪ pˌiː ˈaɪ`. The pinned SDK G2P's native standalone dictionary form, already observed under ADR159, is `ˌeɪpˌiːˈaɪ`. The stress-only trial preserved spaces; this trial changes only the two internal API spaces. Vowel/consonant symbols and stress marks remain identical. Grouping may influence acronym realization, but correct dictionary phones do not establish the cause of the reported errors or guarantee improvement.

Use exactly the existing `mixed-api` sentence: “Bạn có thể gọi API bằng Python trên server này không?”, existing Ngọc Huyền reference codes ON, original clause path, US Python/server targets, seed/sampling/joining. Reuse the immutable original Ngọc Huyền baseline, do not regenerate it. Exactly one new candidate request/one original chunk. Native dictionary/control and baseline/chunk/candidate token roundtrip must be checked without weights; zero unknown tokens. The candidate uses min(retained shared cap, candidate original cap,300), and must equal the retained baseline's cap172 to permit the matched comparison. Refuse neural execution if that equality fails; do not change the old allowance. The date/API sentence is excluded in advance because deleting spaces can reduce its allowance below its recorded baseline; do not silently compare unequal budgets.

The earlier ADR158 direct standalone Ngọc Huyền compact API slot was UNATTEMPTED after standalone A failed; this new full-sentence clause-path comparison neither retries the failed A case nor completes/renames that old cohort. The rejected reference-ablation/carrier study remains rejected. No ref-off, respelling, added context, new phonemes/dictionary entry, audio repair, additional model/reference/training or Trúc Ly generation.

## Execution and evidence

Add separate worker/controller/tests; preserve all43prior research source/test files. Reuse Ngọc Huyền admission/reference audit, original chunk generation, owned lifecycle and native validation. Keep the ten-row source packet for existing semantic validation, but freeze `mixed-api` as the only admitted ID/text; all other rows are metadata, not planned or unattempted requests. Packet SHA and exact voice/profile must match at readiness. Actual new phones/cap/voice hashes must match the no-weights probe and retained Ngọc Huyền binding. Retain genuine native WAV/chunk and exact code snapshots.

One candidate, one chunk, zero retries/ASR/CORE/Brave; wall60seconds. Preserve CPU0,1/two threads/AS8GiB/TTS sampledRSS2GiB/aggregate8GiB/headroom14GiB/root8GiB. Freeze code, passing software, authority, probe and baseline provenance before load. Stop/join on first failure, preserve the failed/missing candidate, never enlarge a cap or synthesize alternatives after listening. Publish two clearly labeled players: retained baseline and actual complete candidate if available. Software/EOS/token/hash checks do not certify acoustic correctness, naturalness or perceived identity.

P1 VOICE-ENGLISH-READING-001 / VOICE-API-ARTIFACT-001; dependencies are the owner's exact heard forms, native dictionary evidence, original same-text baseline, tested guards and owner listening. Effort one one-pair diagnostic milestone. Risks include no improvement, whole-sentence prosody/timbre changes despite local input edits, authored-case overfit and conservative-frame rejection. Rollback discards only this optional policy from consideration and joins its worker; all existing source/models/presets/audio/defaults remain intact. No automatic tuning, migration, voice/model selection or release follows. D60deferred/ADR155workflowunapproved/physical4second/rights/no-speech/product/D90release remain separate.
