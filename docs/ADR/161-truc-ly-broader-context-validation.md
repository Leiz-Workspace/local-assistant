# ADR 161 — Trúc Ly broader-context validation

**Purpose:** Verify the owner-accepted Trúc Ly US term policy in newly declared VI/en-US/mixed sentences, preserving original evidence and avoiding another parameter-tuning loop.

**Status:** Owner-requested continuation “Tiếp đi” after the voice-specific assessment. This is a bounded research validation, not product voice selection, a new model/reference/training, or ADR-155 workflow recovery.

## Fixed corpus and policy

Ten new source sentences, only Trúc Ly:

1. EN: “I think this is the right answer.”
2. EN: “Please say ship, sheep, right, and light in that order.”
3. EN: “Are you ready to use Python on this server?”
4. EN: “I saved the file on GitHub, and the browser is ready.”
5. MIXED: “Bạn có thể gọi API bằng Python trên server này không?”
6. MIXED: “Bạn muốn xem mã GitHub hay chạy ứng dụng bằng Docker?”
7. MIXED: “Hẹn bạn lúc 09:15 ngày 14/11/2026; bạn muốn nhận thông báo qua API không?”
8. VI: “Đơn hàng có 12 sản phẩm, mỗi sản phẩm giá 125000 đồng.”
9. VI: “Chương XI nói về xi măng; chương VI nói về hành vi vi phạm.”
10. VI: “Chị đã lưu bản ghi, bạn có muốn nghe lại trước khi tiếp tục không?”

Use the exact old `render_english` date/clause renderer, original ProsodyAdapter generation/joining, unchanged API stress function and three fixed ADR160 term targets. No new dictionary entry, tuning, prompt padding, audio repair, reference change or Ngọc Huyền inference. Existing sentence whitelist/single-chunk operators stay frozen: add a separate packet-bound adapter for the new multi-clause corpus, reusing old phone planning, voice resolver/audit and sampling code.

For each original normalized chunk, apply the same existing edits only where its declared term is present; recognize an already-target form without a second replacement. Aggregate term/API counts must match the source corpus metadata. Legacy planner API-presence metadata is not spoken text. Use exactly its conservative `min(original baseline cap, original US cap,300)` per chunk, never increase an allowance. Preserve original chunk/gap/question/date/number semantics. The no-weights probe freezes rendered text, ordered chunks, phones, caps, lexical counts, source/native reference bindings and English reference-phone presence. This is self-consistency/provenance, not an independent accent oracle.

Explicit frontend checks: initial English I remains /aɪ/; ship/sheep and right/light have distinct expected dictionary phones; Vietnamese12/125000 preserve values; time09:15/date14/11/2026 and VI/XI versus Vietnamese words retain their expected spoken meanings. Frozen source sentences are different from the earlier six-case US panel. Author-created extension, not a blind independent benchmark.

## Execution bounds

Exactly10top-level TTS requests; at most16original inner chunks (expected12, determined and frozen by the original chunker). One original CPU worker, Trúc Ly/reference codes ON; same measured speaker/reference hashes as the previous accepted panel. CPU0,1/two threads/AS8GiB/TTS sampledRSS2GiB/aggregate8GiB/headroom14GiB/root8GiB/panel120seconds; zero retry/ASR/CORE/provider calls/downloads/model/reference/training changes.

Freeze new code/tests, passing software, protocol/authority, rendered packet and probe before loading; mount the frozen probe read-only and verify its SHA in the worker. Reject unknown source/rendered input or another voice before prediction. Actual native plans, chunk hashes, EOS, conservative caps and speaker/reference audit must match the frozen probe. Stop/join on first failure and preserve all10slots including unattempted items. No repairing a failed output or using spare budgets from old trials.

Preserve all37prior research files,750application/210protected, SDK/models/voices/audio, earlier first failures and owner judgments. No production route/config/shared-service change. New listening pages grouped by EN/MIXED/VI contain genuine original WAVs and all missing outcomes; no recording, uploads, script or network.

## Gates, effort, risk and rollback

P1 VOICE-BILINGUAL-IDENTITY-001/VOICE-ENGLISH-READING-001. Dependencies: owner en-US/same-voice goal, retained accepted policy/bindings, fixed corpus/semantic targets, tested packet-bound adapter and resource guard. Effort one ten-clip validation milestone. Risks: limited authored corpus/word overfit, variable context stress, perfect phones with wrong accent, multi-clause timing/voice drift and conservative-frame rejection. Software/EOS/voice-input hashes do not certify perceived identity or naturalness.

Owner listening must assess I/target words and contrasts, accent, questions, dates/numbers/Roman meanings, mixed API and voice naturalness/similarity. Preserve prior scoped Trúc Ly pronunciation acceptance; no universal US or product acceptance is inferred. Ngọc Huyền English rejection remains intact. Any failures stay in the result without rerun/tuning. Rollback disables only this optional validation adapter and retires its worker; originals remain unchanged.

D60 deferred; ADR15548workflow unapproved/unexecuted. XI older listening, rights/no-speech/physical4seconds/product/D90release remain separate gates.
