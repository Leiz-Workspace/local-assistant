# D74 — Giữ cách ngắt câu đã đạt, sửa đường đọc Python/API

**Mục đích:** Ghi nhận phần đã được chủ dự án xác nhận, giữ nguyên các thành phần đó và đánh giá riêng phát âm tiếng Anh cùng lỗi rè/run ở API.

**Trạng thái:** Giờ/ngày được chủ dự án xác nhận chuẩn trên bộ đã nghe; `clauses` được đánh giá tốt nhất/tự nhiên nhất. **Python và tiếng rè/run của API chưa được nghiệm thu.** [Nhận xét nguyên văn](evidence/d74-reading-quality-owner-followup.json), [ADR-157](ADR/157-english-terms-with-preferred-prosody.md), [kết quả8clip mới](evidence/d74-english-reading-result.json), [kiểm chứng sau thực thi](evidence/d74-english-reading-verification.json).

## Phần đã được xác nhận và phần còn lỗi

| Nội dung | Kết quả của chủ dự án | Phạm vi giữ lại |
|---|---|---|
| Giờ/ngày | Đã chuẩn | Xác nhận trên bộ đã nghe, không suy ra mọi định dạng/ngày chưa thử |
| Cách xử lý | “Cách đọc + ngắt câu và giữ dấu hỏi” tốt nhất và tự nhiên nhất | Giữ đường `clauses` cho bước sửa tiếp theo; chưa tự kích hoạt sản phẩm |
| Python | Lúc “Py thon”, lúc “Py thờ”; phải đọc giống tiếng Anh | Chưa đạt; bỏ cách phiên âm tiếng Việt của thử nghiệm trước |
| API | Cả hai giọng bị rè/run khi phát âm | Chưa đạt ở cả hai giọng; không coi waveform hữu hạn/EOS là hết lỗi |

Đây là nhận xét tổng quát, không phải24/48nhãn riêng hoặc MOS. Chưa chọn giữa Trúc Ly/Ngọc Huyền; không suy ra chấp nhận sản phẩm, quyền model hoặc timing4giây. Nhận xét “không lỗi âm thanh” của D70 trước đó thuộc corpus khác và vẫn được giữ đúng lịch sử.

## Thay đổi mới

Bản trước dùng lexicon thử nghiệm Python→“pai thờn”, API→“ây pi ai”. Cách đó không đáp ứng yêu cầu tiếng Anh vừa được làm rõ. Renderer mới bỏ **chỉ** các edit lexicon đó; giữ nguyên source/display text, edit giờ/ngày, bảo vệ code/URL/identifier, ngắt câu và dấu hỏi. Toàn bộ10file ADR156 và7operator trước đó nguyên hash, không sửa đường prosody đã được người dùng thích.

Tám đầu vào mới đều đi qua normalizer/G2P hiện có với chuỗi phát âm tiếng Anh tham chiếu `pˈaɪθən` và `ˈeɪ pˈiː ˈaɪ`; tokenizer không có unknown token trong probe. Đây là xác minh frontend, không chứng minh âm thanh chuẩn. Các phoneme này đã có trong SDK cũ; không tuyên bố bổ sung một năng lực model hoàn toàn mới.

Kiểm numeric các clip mục tiêu trước đó không thấy mẫu chạm/vượt full scale. Điều đó **không phủ nhận tiếng rè/run người dùng nghe được**, không xác định đoạn API hoặc nguyên nhân. Không denoise, đổi gain, cắt audio, thay sample hay tăng cap để che lỗi.

## Lượt thử mới đã thực hiện

Bốn câu ×hai giọng = **8request TTS/14chunk native**,0retry/0ASR/0CORE,0unattempted; đầu ra mono48kHz/hữu hạn/EOS, worker thoát0/joined. Giữ weights/SDK/precision/sampling/frame caps/codec/preset resolver và cách ghép cũ. Peak RSS lấy mẫu khoảng1.341MiB, dưới2GiB; giữ AS8GiB/headroom14GiB/CPU0,1/hai threads/root8GiB. Baseline native/container khớp trước-sau; không tải model/package hoặc đổi product/default/shared service.

Hai câu đầu lặp đúng text mục tiêu để so sánh **policy mới**, dùng nguyên4clip cũ làm đối chứng, không sinh lại đối chứng. Hai câu sau là diagnostic/control mới, trong đó có giờ/ngày. Tám clip đều khác bản `clauses` cũ ở các câu có đối chứng; hai clip trùng từng byte với bản `raw` cũ, phù hợp với việc đã trả về đường phát âm tiếng Anh có sẵn. Không xóa hoặc chấm lại các kết quả trước.

[Trang nghe8clip mới +4đối chứng cũ](../data/backups/d74-vi-approved-campaign-20261103/english-reading-first/review/index.html) mở trực tiếp, không server/microphone/upload/network/JavaScript. [Toàn bộ2file code/test mới](../data/backups/d74-vi-approved-campaign-20261103/english-reading-first/review/full-code.zip). Chỉ cần kiểm Python đã giống tiếng Anh chưa, API còn rè/run không và phần ngắt câu/giờ-ngày có giữ được như trước không. Chưa có nhận xét của chủ dự án cho bộ8clip này.

## Kiểm thử và giới hạn

Lượt scoped cuối **236PASS/0FAIL/0ERROR/0SKIP,4,22giây**, lint/format PASS. Trước đó có một lượt236case bị1FAIL/235PASS ở test decode video của component audio cũ (`audio_invalid_content`). Test riêng sau đó1PASS/0,47giây, rồi cùng scope236PASS; fixture đúng hashHEAD, không sửa source/test/limit cũ. Giữ receipt lỗi đầu tiên, nguyên nhân **chưa xác định**, không gọi nó là lỗi đã sửa hoặc tự bỏ test. Trial tiếng Anh này không gọi decoder đó; vấn đề intermittent được ghi riêng để điều tra trước nghiệm thu sản phẩm.

Tests mới bảo vệ phần date/prosody đã đạt, giữ English tokens/trace, khóa probe-to-input/unknown-token, namespace không weights cho probe,8slot/fail-first/no-retry và trang nghe. 750file ứng dụng/210đầu vào bảo vệ/17file nghiên cứu cũ,48clip trước/24clip gốc và planADR155 nguyên hash. Full5889 là snapshot ứng dụng trước, không phải một lượt full mới.

Phần nghe mới vẫn cần người dùng xác nhận; không tuyên bố Python/API hoặc tiếng rè đã được khắc phục chỉ từ frontend/signal metrics. ADR155workflow tiếp tục chưa duyệt/chưa chạy. Chưa có model/voice/default activation, physical first-audible≤4giây, quyền sử dụng hoặc release approval. D60 tiếp tục chờ.


## Phản hồi tiếp theo: API vẫn đọc sai chữ A

Chủ dự án nghe bản mới và báo “A-Pi-Ai”, yêu cầu “Ei-Pi-AI” theo tiếng Anh. [Receipt và đối chiếu log](evidence/d74-api-first-letter-owner-feedback.json) xác minh cả8trace native đã nhận `ˈeɪ pˈiː ˈaɪ`; tokenizer normalization làNFC, không phải một quy tắc đổi chữA tiếngAnh sangA tiếngViệt. Điều này xác nhận sửa frontend chưa đủ: API pronunciation tiếp tục **OWNER REPORTED NOT ACCEPTABLE**. Không bịa nguyên nhân chính xác trong network/preset/tokenizer/decoder; khả năng lỗi nằm ở quá trình hiện thực âm thanh sau frontend cần được kiểm riêng.

Tin nhắn này không cập nhật Python hoặc việc API còn rè/run, nên hai phần đó vẫn mở; không tự coi đã hết lỗi. Giờ/ngày và sở thích `clauses` trước đó giữ nguyên. Chỉ ghi nhận/đối chiếu bằng chứng, không sinh clip mới, thay text/model/settings, chạy ADR155 hoặc đánh dấu quality PASS.


## API reference diagnostic — 2026-11-04

[Actual result and eight paired listening clips](D74_API_REFERENCE_DIAGNOSTIC_RESULT.md): first16-slot diagnostic remains stopped at Ngọc Huyền isolated-A13frames/EOSfalse (4complete/1failed/11unattempted); no retry or raised cap. A separately declared8-slot full-carrier cohort completes all4exact phoneme/token/speaker/anchor pairs with reference-code on/off; combined13actualTTS≤16, not original16PASS. Final257scoped software PASS/0FAIL/ERROR/SKIP4.29s, RuffPASS;250initialPASS. Exact token roundtrip/zero unknowns do not establish acoustic Ei or absence of APIbuzz.

VOICE-ENGLISH-READING-001/VOICE-API-ARTIFACT-001 remain P1. Subsequent owner feedback reports the new set worse; diagnostic quality NOT ACCEPTED (see current disposition below). No automatic reference-off/model/voice/default selection; weights/SDK/presets unchanged. Python not re-evaluated; reviewed date/time and preferred `clauses` retained. All750application/210protected/19prior research files and prior audio unchanged. No new downloads, ASR/CORE/Brave calls, shared service changes or ADR155workflow execution. Physical4second/rights/no-speech/product/D90release remain open; D60owner-deferred. Full5889/earlier236scoped counts remain historical, not new full runs.


**Current owner disposition, 2026-11-04:** [Exact feedback](evidence/d74-api-reference-owner-rejection.json): “Còn tệ hơn cả bản trước nữa”. Reject adoption of this diagnostic and preserve the earlier `clauses` path/date/time acceptance. No separate clip, ref-on/off or Ei/buzz/timbre ratings are inferred. API quality remains open; Python not reassessed. Different texts/direct-phoneme preparation prevent causal attribution of the old-to-new regression. Next engineering step is a source-backed minimal same-text/same-voice comparison design on the retained clauses path; no new native trial scheduled or remaining slots consumed.257scoped PASS is historical software evidence only. No model/default/workflow activation or new source/config/model/provider calls.


## Same-text API stress follow-up — 2026-11-04

[ADR159 actual result and four same-text pairs](D74_API_STRESS_COMPARISON_RESULT.md): latest owner “Làm đi” continues narrowly on the old english-01/04 sentences and both retained voices.4newTTS/6innerchunks complete/EOS/exit0/no retry; four exact ADR157baselines reused. Only API stress marks change at the old ProsodyAdapter phonemizer dependency, preserving text/date/clauses/question/Pythoninput/referenceON/sampling/frame caps. Two first date chunks match old audio byte-for-byte.267scoped software PASS4.78s/RuffPASS; two initial test-fixture failures retained.

Ei/APIbuzz/whole-sentence naturalness remain unaccepted pending owner listening; unchanged Python phones do not certify its waveform. The rejected carrier trial remains OWNER_REPORTED_WORSE_NOT_ACCEPTED; no ref-off or model/voice/default/policy adoption.25prior research/750application/210protected/SDK/model/audio preserved, no ASR/CORE/provider/download/service change. ADR155workflow unapproved/unexecuted; physical4second/rights/no-speech/product/D90release open, D60owner-deferred;5889full remains historical.


## API owner acceptance and Roman context check — 2026-11-04

[Exact owner feedback](evidence/d74-api-python-roman-owner-feedback.json) confirms API pronunciation correct on the reviewed ADR159panel; Python remains unacceptable. Preserve that API operator/audio. No per-clip or separate APIbuzz/timbre acceptance, voice/model/default/product approval is inferred.

[Roman/Python context result](D74_ROMAN_CONTEXT_RESULT.md): original SDK verifies5of5fixed unambiguous targets, preserving vi in vi phạm/VI PHẠM and reading Chương VI as sáu, including both meanings in one sentence; IV/IX frontend-only. Identifier VI is observation-only. Bare/tagged Python phones identical, not a fix.8Roman-word+2EnglishPython native controls complete10TTS/10chunks/EOS/exit0/no retry;2oldmixed references unchanged, new acoustic listening pending.275scoped software PASS5.03s/RuffPASS. No normalization/pronunciation rule or model/SDK/acceptedAPI change;29oldresearch/750application/210protected and previous audio preserved. VOICE-CONTEXT-READING-001 P1 frontend corpus complete, acoustic gate open; Python P1 remains open. ADR155workflow/physical4second/rights/no-speech/product/D90release unaccepted; D60deferred.


## XI context and same-voice American English — 2026-11-04

[Owner feedback](evidence/d74-vi-xi-bilingual-owner-feedback.json) accepts reviewed VI/vi, reports Vietnamese-accented English not acceptable, and asks XI/xi măng. [Explicit preference](evidence/d74-owner-en-us-preference.json): en-US, retaining the same voice identity. API pronunciation/date/prosody accepted-scope preserved; no per-clip labels, new voice/model or deployment approval.

[XI and bilingual result](D74_XI_BILINGUAL_RESULT.md): existing frontend5of5fixed targets correct, including XI MĂNG and mixed Roman/word usage;6nativeXIcontrols/6chunks complete/EOS/exit0/no retry, listening pending.282scoped software PASS5.25s/RuffPASS.31oldresearch/750application/210protected/SDK/model/audio preserved, no reading-rule/source-policy change or ASR/CORE/Brave/new model/reference/training.

P1VOICE-BILINGUAL-IDENTITY-001 assessed, not executed: same-identity VI/EN-US pronunciation/accent/voice-similarity rubric, source-backed PythonUS frontend comparison as next design step; broader bilingual reference/adaptation proposals need data/rights/resource/migration/rollback review and explicit owner approval. Existing bilingual support is not acoustic acceptance; pinned infer has no accent/language parameter and ignores style. No guaranteed preset accent fix established. D60deferred/ADR155workflowunapproved; physical4second/rights/no-speech/model/voice/product/D90release open.


## Same-voice US term comparison — 2026-11-04

[ADR160 actual result and paired listening pages](D74_US_TERMS_COMPARISON_RESULT.md): owner explicitly continues PythonUS plus other words. Six exact sentences/two retained voices; change only Python US vowel, GitHub whole-word dictionary form and server rhotic hypothesis. Docker/browser/database input phones unchanged, accepted API function and clause path retained. Shared min(original) frame budgets never increased; GitHub fresh baseline allowance conservatively reduced140→136.

16newTTS/16chunks/EOS/exit0/no retry +4oldPythonbaselines +4sharedunchangedcontrols =24logicalobservations/12pairs,20actualplayers split into two voice pages. Eight changed pairs differ in waveform; no acoustic PASS inferred. Four fresh GitHub/server pairs match measuredspeaker/reference hashes; oldPython provenance bound to retained source/audio without retrospective measurements.295scoped software PASS5.31s/RuffPASS;4newsource/test,33oldresearch/750application/210protected/SDK/model/audio preserved,baseline restored. No model/reference/training/app/config/ASR/CORE/Brave changes.

VOICE-ENGLISH-READING-001/VOICE-BILINGUAL-IDENTITY-001 now have a real paired word panel; en-US pronunciation/accent, perceived voice similarity, naturalness and API inside new mixed audio await listening. Accepted prior API/VI/date/clauses remain scoped, XI review pending. No model/voice/default/policy adoption; D60deferred/ADR155workflowunapproved, physical4second/rights/no-speech/product/D90releaseopen;5889full historical.


## Owner assessment by voice — 2026-11-04

[Exact feedback and retained I traces](evidence/d74-us-terms-owner-voice-assessment.json): Trúc Ly pronunciation accepted as en-US on the reviewed word panel; Ngọc Huyền English not acceptable, with I heard as i. Exact clip/role ratings and full-playback confirmation were not supplied. Both voices' retained baseline/candidate I sentence inputs already beginˈaɪ, so no frontend I→/i/ conversion is demonstrated; a specific model/reference/decoder cause remains unknown.

[Current disposition](D74_US_TERMS_COMPARISON_RESULT.md) prioritizes preserved Trúc Ly for wider same-voice VI/en-US validation. Ngọc Huyền is unqualified for English under this panel; Vietnamese findings remain intact. Broader pronunciation/accent, naturalness, perceived identity and API in new mixed audio remain separate; no per-clip scores, universal quality claim or product voice/model/default selection. Next validation depends on a declared broader corpus and tested bounded protocol; effort one milestone, risk authored-panel overfit/regression, no new native run scheduled. Documentation only/0new inference/source/config/model actions; old panel/source/audio and295softwarePASS retained. ADR155workflow unapproved, D60deferred, XI listening/physical4second/rights/no-speech/product/D90release open.


## Trúc Ly broader-context validation — 2026-11-04

[ADR161 actual result and grouped listening pages](D74_TRUC_LY_VALIDATION_RESULT.md): ten new sentences, only retained Trúc Ly, four EN/three mixed/three VI. All10TTS/12original chunks complete/EOS,0retry,worker exit0/baseline restored. Same API/date/clause/US-term policy and measured speaker/reference binding, no new lexicon/model/reference/training/default.306related software PASS/0FAIL/ERROR/SKIP5.39s;37oldresearch/750application/210protected/4295SDKentries preserved. Prior Trúc Ly en-US panel acceptance and Ngọc Huyền English rejection remain scoped and intact.

VOICE-ENGLISH-READING-001/VOICE-BILINGUAL-IDENTITY-001: broader native corpus complete, acoustic review OPEN. Hear I/ship-sheep/right-light, terms, mixed API, date/amount and VI/XI; score pronunciation/accent separately from naturalness/perceived identity and artifacts. Dependency owner listening, effort one review milestone, risk authored-panel overfit/regression; no further tuning run scheduled. Physical first-audible4seconds remains unverified despite TTS-only0.781–2.214s; prior XI review/rights/no-speech/product/release stay open. ADR155workflow NOT APPROVED/NOT EXECUTED; D60deferred, no product voice/model selection.


## Owner accepts current Trúc Ly quality; refinement stopped — 2026-11-04

[Exact feedback](evidence/d74-truc-validation-owner-acceptance.json) accepts the latest broader Trúc Ly panel as sufficient and asks to stop this refinement cycle. Known English articulation limitation retained: final sounds unclear, “this” heard as “dít”. No perfect-pronunciation claim, per-clip labels, separate naturalness/identity scores or product voice/model selection inferred. [Current report](D74_TRUC_LY_VALIDATION_RESULT.md) supersedes its earlier pending-listening status; old native results remain immutable.

Ngọc Huyền has NOT run this new10-sentence corpus; its earlier US-term panel was tested and owner-rejected, including I→i, which remains historical evidence. New-corpus evaluation PENDING separately: same corpus/policy/model and retained first failures, tested bounded voice-specific runner required because ADR161 is Trúc Ly-only; effort one evaluation milestone, risk articulation/identity/cap failure, no new run or fix claimed.0new inference/code/config/model/download changes or software tests in this feedback update;306scoped/5889full remain historical. ADR155workflow unapproved, D60deferred; physical4second/rights/no-speech/product/D90release remain open.


## Ngọc Huyền matched-context evaluation — 2026-11-04

[ADR162 result and grouped listening pages](D74_NGOC_HUYEN_VALIDATION_RESULT.md): owner “Làm đi” authorizes one Ngọc Huyền-only evaluation on exactly the same ten source/rendered sentences and twelve phone/chunk plans as Trúc Ly. Explicitly reuse the original no-weights frontend observations; no new probe/tuning/model/reference/lexicon changes.10TTS/12chunks complete/EOS,0retry/0unattempted,worker exit0/baseline restored; measured reference/speaker binding matches prior Ngọc Huyền and differs from Trúc Ly.317related PASS/0FAIL/ERROR/SKIP5.34s;40oldresearch/750application/210protected/4295SDKentries and accepted Trúc Ly audio preserved.

Ngọc Huyền new-corpus status now NATIVE COMPLETE / LISTENING PENDING, superseding its previous not-run checkpoint. Earlier English/I→i rejection remains intact; no acoustic fix, universal quality or product/default choice inferred. Next dependency owner listening for I/contrasts/terms/API/VI/date/Roman words, naturalness/identity/artifacts; effort one review milestone, risk small authored corpus/regression, no further tuning scheduled. Trúc Ly accepted with known limitations and refinement stopped; ADR155workflowunapproved/D60deferred/physical4second/rights/no-speech/product/D90releaseopen.0ASR/CORE/Brave/download/shared-service changes;5889full remains historical.
