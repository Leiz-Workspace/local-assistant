# D74 — Kết quả sửa cách đọc và giữ ngữ điệu câu hỏi

**Mục đích:** Báo cáo việc đã triển khai, bằng chứng kỹ thuật và bộ clip so sánh mới; giữ rõ những lỗi chất lượng chưa được người dùng xác nhận khắc phục.

**Trạng thái:** Bản nghiên cứu và panel48clip hoàn tất về kỹ thuật; **chưa nghiệm thu cách đọc/độ tự nhiên**. [ADR-156](ADR/156-isolated-speech-reading-and-question-preservation.md), [quyền thực hiện từ lệnh “Làm đi”](evidence/d74-reading-quality-owner-authorization.json), [kết quả thực tế và hash](evidence/d74-reading-quality-result.json), [kiểm chứng sau thực thi](evidence/d74-reading-quality-verification.json). Đây là tác vụ chất lượng mới, không phải phê duyệt ADR-155 chạy lại48lượt hỏi–đáp.

## Đã tìm ra gì

- Với đúng câu giờ/ngày trong panel cũ, thư viện đã chuyển09:15 và14/11 thành “chín giờ mười lăm phút” và “ngày mười bốn tháng mười một”. Python/API cũng đã có phiên âm tiếng Anh. Vì vậy không kết luận lỗi nghe là do hoàn toàn thiếu bước chuẩn hóa hoặc từ điển.
- Có lỗi cụ thể ở câu hỏi ngắn: “Bạn đồng ý chứ?” bị đường SDK cũ đổi dấu hỏi thành dấu chấm, cả trong chunk và âm vị. Bản nghiên cứu mới giữ dấu hỏi tới đầu vào engine bằng API phoneme sẵn có; audio câu hỏi ngắn của cả hai giọng đã khác bản đối chứng, nhưng chưa xác nhận nghe hay hơn; không sửa file SDK/weights hoặc thêm từ để kéo dài câu.
- `style` bị bỏ qua trong SDK đang dùng, còn `silence_p` không điều khiển đường gap của v3. Không coi việc đổi hai tham số này là một cách sửa đã có tác dụng.
- Thử phân đoạn64ký tự bằng probe không model đã cắt “mười lăm” khỏi “phút”. Phương án đó bị loại trước khi sinh audio; giữ receipt cũ. Bản cuối chia theo câu/mệnh đề đầy đủ, không cắt cụm giờ/ngày ở giữa để đạt giới hạn ký tự.

## Thay đổi đã triển khai

Mã mới chỉ ở `benchmarks/`, không nối vào API hoặc pipeline sản phẩm. Renderer tạo bản đọc riêng, giữ nguyên câu trả lời gốc/hiển thị và hash/trace từng phép thay. Chỉ đổi giờ có ngữ cảnh rõ ràng, ngàyDD/MM[/YYYY] có kiểm lịch, và đúng token Python/API; bảo vệ code, URL, email, đường dẫn và identifier ghép. Format không hỗ trợ hoặc không rõ ngữ cảnh được giữ nguyên.

Python→“pai thờn” và API→“ây pi ai” là **cách ghi âm tiết tiếng Việt để thử**, không phải chứng nhận phát âm tiếng Anh chuẩn. Các quy ước đọc số/ngày cũng là policy nghiên cứu được ghi rõ; người dùng có thể không thích chúng. Không sửa text hiển thị, dữ liệu gốc hoặc âm thanh cũ để làm điểm đẹp hơn.

Profile ngữ điệu dùng đúng preset resolver, sampling/frame cap/codec/watermark và hàm ghép native của SDK hiện có. Nó giữ câu hỏi khi normalize/G2P, gửi phoneme qua engine gốc, sinh mỗi chunk một lần và giữ cả native chunk bytes/hash. Đây là thay đổi kết hợp về cách đọc và ranh giới câu, không chứng minh riêng từng yếu tố gây ra một cải thiện.

## Phép thử đã chạy

8câu diagnostic mới ×2giọng hiện có ×3profile = **48request TTS**, gồm54lần sinh chunk bên trong SDK; tất cả đầu ra hữu hạn, mono48kHz, kết thúc EOS. Không retry, không ASR/CORE, không tải model/package, không giảm context hoặc đổi backend/precision. Hai giọng vẫn là Trúc Ly và Ngọc Huyền; chưa chọn một giọng cho sản phẩm.

| Profile | Nội dung | Thời gian TTS nhỏ nhất–lớn nhất | RSS RAM lấy mẫu cao nhất |
|---|---|---:|---:|
| raw | Text mới nguyên bản qua SDK gốc | 0,361–1,951giây | 1.610,2MiB |
| reading | Bản đọc riêng qua cùng SDK gốc | 0,346–1,945giây | 1.609,4MiB |
| clauses | Bản đọc + tách câu/mệnh đề + giữ dấu hỏi qua phoneme API | 0,307–1,837giây | 1.604,9MiB |

**12/16cặp raw–reading có audio giống hệt từng byte**, gồm cả các mẫu giờ/ngày. Điều này phù hợp với việc SDK vốn đã chuẩn hóa những câu đó đúng. Không báo rằng formatter mới đã sửa được lỗi đọc giờ/ngày trong âm thanh; phần acoustic/cách đọc người dùng nghe thấy vẫn cần đánh giá. Bốn cặp khác có thay Python/API; chưa biết người dùng thấy tốt hơn hay kém hơn.

Các số thời gian chỉ đo TTS; chi phí render được ghi riêng trong freeze. Không gồm ASR/CORE/delivery/playback, không xác nhận first-audible≤4giây và không dùng trung bình để thay giới hạn tối đa. Bộ câu do tác giả xây để chẩn đoán lỗi đã báo, không phải tập đánh giá chất lượng độc lập hoặc MOS.

Mỗi worker CPU affinity0,1/hai threads, AS8GiB/RSS lấy mẫu dưới2GiB, headroom trước load≥14GiB; cả ba worker thoát0 và được join. Baseline native/container được khôi phục. 750file ứng dụng,210đầu vào bảo vệ và7file nghiên cứu cũ nguyên hash; toàn bộ24clip cũ/planADR155 giữ nguyên. Full5889trước đây thuộc snapshot750 cũ, không phải full regression vừa chạy.

## Mở bộ nghe so sánh mới

[Trang nghe48clip](../data/backups/d74-vi-approved-campaign-20261103/reading-quality-first/review/index.html) nhúng WAV gốc và chạy trực tiếp, không cần server, không microphone/upload/network/JavaScript. Mỗi hàng là một câu/một giọng, với ba bản để so sánh; bản thiếu/lỗi nếu có phải hiển thị, không được bỏ khỏi mẫu số. [Toàn bộ10file code/test mới](../data/backups/d74-vi-approved-campaign-20261103/reading-quality-first/review/full-code.zip).

Có thể nghe trước:

- `reading-01` đến `03`: giờ/ngày;
- `reading-04` và `05`: Python/API;
- `reading-06` và `07`: ngắt mệnh đề/câu;
- `reading-08`: câu hỏi ngắn.

Gửi nhận xét theo mã câu, giọng và bản bạn thích ngay trong chat. Chưa có nhãn nghe cho48clip mới. Giữ nhận xét trước đó thích Trúc Ly/Ngọc Huyền nhưng chưa tự biến thành lựa chọn cuối.

## Kiểm thử và bước tiếp theo

**221tests PASS /0FAIL/0ERROR/0SKIP,4,37giây**, lint/format PASS trước freeze và native. Các test bao gồm quy tắc đọc/lịch, protected text/trace, giữ câu hỏi và sampling/preset, cap/chunk không chia sai cụm giờ, namespace không model cho probe, lifecycle mismatch/cancel, bộ điều khiển48slot/fail-first, trang nghe và các regression liên quan. Ba probe không model giữ120hàng chẩn đoán; probe cuối xác minh dấu hỏi và cụm giờ được giữ. Đây là software/native-integrity PASS, không phải acoustic quality PASS.

VOICE-TEXT-READING-001: renderer và regression đã triển khai; **phát âm/giờ-ngày trong audio chưa xác nhận khắc phục**. VOICE-PROSODY-001: đường giữ dấu hỏi và chia câu đã triển khai/thử nghiệm; **độ tự nhiên chưa được xác nhận cải thiện**. Cần nhận xét trên bộ mới để quyết định giữ hoặc bỏ từng policy; không tự tải/thay model nếu chưa đạt. ADR-155 vẫn chưa được duyệt/chưa chạy. Quyền sử dụng, no-speech, first-audible, model selection, D74 sản phẩm và D90 release còn mở; D60 tiếp tục chờ.


## Nhận xét sau khi chủ dự án nghe

[Receipt và follow-up](D74_ENGLISH_READING_FOLLOWUP.md) cập nhật trạng thái: chủ dự án xác nhận giờ/ngày đã chuẩn, `clauses` tốt nhất/tự nhiên nhất; Python/API cần đọc như tiếng Anh và API rè/run ở cảhai giọng. Các câu “chưa có nhãn nghe” ở snapshot thực thi trên đây là trạng thái trước phản hồi. Không ghi đè metrics/audio/receipts. Renderer tiếng Anh mới giữ nguyên date/prosody đã được xác nhận;8clip mới vẫn chưa có đánh giá.


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

Ngọc Huyền new-corpus status: NATIVE COMPLETE / OWNER REPORTS API PRONUNCIATION WRONG; [feedback/input audit](evidence/d74-ngoc-api-owner-feedback.json) confirms both actual API plans/phones match Trúc Ly, so no frontend-policy drift is shown. Owner subsequently specifies [E - Pe-I / A - Pe - I](evidence/d74-ngoc-api-exact-owner-feedback.json); specific internal cause/per-clip mapping remain unknown, other ratings absent. [ADR163 one-pair boundary trial](D74_NGOC_API_BOUNDARY_RESULT.md) now completes1newTTS/1chunk with1retained baseline, samecap172/voice/reference and only2APIspaces removed according to pinned native dictionary;328relatedPASS. Owner now reports [improved but still incorrect; stop refinement](evidence/d74-ngoc-api-owner-stop.json). Both Ngọc Huyền and Trúc Ly pronunciation refinement cycles are stopped; preserve API limitation/old scores/audio, no candidate adoption. [Next D74 work](D74_NEXT_WORKFLOW_VALIDATION.md): audit recovery integration and accepted reading policy, prepare full-workflow/latency validation; ADR155 native approval remains separate. Earlier English/I→i rejection remains intact; no acoustic fix, universal quality or product/default choice inferred. No further pronunciation trial scheduled; other unscored properties remain unscored. Next priority is one recovery-integration/test preparation milestone, then a separately approved workflow benchmark; risks small-corpus limits, ASR latency/negative errors and incomplete wiring. Trúc Ly accepted with known limitations and refinement stopped; ADR155workflowunapproved/D60deferred/physical4second/rights/no-speech/product/D90releaseopen.0ASR/CORE/Brave/download/shared-service changes;5889full remains historical.
