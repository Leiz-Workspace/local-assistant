# Voice — Yêu cầu ngôn ngữ, chất giọng và thời gian chờ


**Current requirements clarification — 2026-11-05:** [ADR174](ADR/174-proposed-opt-in-authenticated-voice-integration.md) proposes stable principal-bound UI sessions and shared GPU residency admission for optional main integration. The qualified lane, explicit Prepare/Send and existing budgets stay fixed; default-off software work/one conditional panel await owner decision. Final voice/model/default activation and physical first-audible≤4 seconds remain separate acceptance gates. [Rights review](D74_VOICE_RIGHTS_REVIEW.md) covers the existing artifacts; distribution obligations depend on actual packaging scope.
**Mục đích:** Ghi đúng yêu cầu chủ dự án để định hướng D74 và backlog voice, tách biệt yêu cầu sản phẩm với việc chọn hoặc triển khai model.

## Trang thử voice đã chạy — 2026-11-05

**URL trên cùng máy: [http://127.0.0.1:8092](http://127.0.0.1:8092)**. [Cách mở/ghi/dừng/gửi/nghe và kiểm chứng](D74_VOICE_BROWSER_TRIAL_GUIDE.md), [kết quả và receipt](D74_VOICE_BROWSER_TRIAL_RESULT.md). Thêm optional loopback research surface riêng; recorder cũ/750application baseline giữ nguyên, không chọn model/default sản phẩm. Prepare chủ động, không tự thu/nạp/gửi khi mở trang; đúng QwenCUDAFP32/CORE32KFast512/TrúcLyCPU8 đã qualified.

766relatedPythonPASS/20JSPASS, Braveheadless fake-mic/muted/mocked-model UI PASS; browser thật không mock GET/POSTcookie/Origin cũng PASS, không mở microphone. RealHTTPnative6/6:4speech ASR/CORE/playback exactprior, clientroundtrip1.972–3.250s và2negative chặn đúng;6VAD/4ASR/CORE/TTS+1readiness,0retry/guard/runtimefault, toàn bộmodel thu hồi. Lượt Prepare43.843s riêng trướcGửi; không gộp thành cold4secondPASS. Giữ firstCSPfixturefailure/oldresults, không nới policy/model/cap hoặc tải thêm.

**P1 còn lại: chủ dự án kiểm chứng actualmic→Brave→loa/physical4seconds qua URL có thật**, không coi marker “Chuẩn bị phát” là tiếng loa. Web service riêng đangchạy/loopback/4giờ; groupmodel8phút,24attempts/3prepares perwebprocess, RAM-only turnfiles/ephemeral browserresults. Phạm vi userdevice/voice/model/rights/default/product/D74/D90release vẫnOPEN; D60deferred, pronunciationcycles dừng. Full5889là lịch sử, không rerun hoặc tự đóng ngày/gate còn thiếu.

## Checkpoint buffered compute trước trang thử — 2026-11-05

[ADR170–172 / kết quả độ trễ thật](D74_RESIDENT_CUDA_LATENCY_RESULT.md): **LOCAL_BUFFERED_COMPUTE_PASS**, Qwen cùng checkpoint chạy CUDA FP32/eager + CORE32K/Fast512 + Trúc Ly CPU8 đã ready.4/4speech có audio hoàn chỉnh trong2,000–3,334giây;2/2negative chặn trước ASR/CORE/TTS.40/40transcript VI/EN trùng CPU;8native transcript/CORE/audio ở hai lượt PASS trùng byte với CPU8.690relatedPASS/98controls mới; full5889 là lịch sử, không chạy lại.

Sáu nhóm CPU2/4/8 vẫn FAIL maximum4seconds. WhisperCUDA FAIL VI CER253/1984vs248/1984, không chạy native. Lượt CUDA đầu dừng vì mount nhầm bản detector; hash chặn trước inference, giữ nguyên kết quả/code đầu. Bản sửa source-binding đạt6/6 (max3,543s); đã sửa thêm disk-budget polling trỏ nhầm root cũ và xác nhận riêng6/6 (max3,334s), root/guard hiện tại đúng. Giữ cả hai lượt PASS và phiên bản đã chạy; không retry chất lượng, relabel hoặc che lỗi. Chỉ thêm SDK CUDA cô lập, không tải weights/thay model/default/voice/app/config hoặc dịch vụ dùng chung.750application/210protected/14ASRartifacts và runtime cũ giữ nguyên.

**VOICE-LATENCY-AC-001 còn OPEN cho first-audible vật lý:** complete PCM chỉ là gate xử lý cục bộ, không phải tiếng từ loa trong4giây. App recorder chưa nối research runner này. P1 tiếp theo: contract/kiểm thử rồi endpoint nghiên cứu có xác thực và browser playback/đo thực trên Brave/PC; dependency gate hiện tại/explicit-submit/ready/cancel/retention, effort một milestone contract/control+tích hợp cô lập+lượt thiết bị, rủi ro khoảng dư<0,67giây/mạng/autoplay/co-memory/cold-start/cleanup. Chưa yêu cầu owner test một URL workflow chưa có. Model/voice/rights/default/product và D74/D90release vẫn OPEN; D60deferred, pronunciation cycles dừng.

**Ngày cập nhật:** 2026-11-05, Asia/Ho_Chi_Minh. **Trạng thái:** REQUIREMENTS/TARGET RECORDED / LOCAL BUFFERED COMPUTE AND UI/HTTP QUALIFIED / PHYSICAL PERFORMANCE UNVERIFIED. [Yêu cầu ban đầu](evidence/d74-voice-requirements-20261103.json) giữ nguyên lịch sử; [xác nhận “4 giây đi”](evidence/d74-latency-target-4s-20261103.json) chốt giới hạn thời gian chờ.

## Yêu cầu đã xác nhận

| Nội dung | Yêu cầu và phạm vi |
|---|---|
| Mục tiêu ngôn ngữ | Có cả tiếng Việt và tiếng Anh |
| Ưu tiên triển khai hiện tại | **Tiếng Việt trước** |
| Giọng tiếng Việt | **Nữ, miền Bắc**; độ tự nhiên cần được chủ dự án nghe và chấp nhận |
| Tiếng Anh | Giữ trong mục tiêu sản phẩm; chưa chốt lịch/release hoặc voice EN. Không tự bỏ tiếng Anh hoặc xếp sang một bản cụ thể |
| Thêm ngôn ngữ tùy biến | **PENDING cho bản sau**; chưa chỉ định ngôn ngữ, số phiên bản, ngày phát triển hoặc model |
| Thời gian chờ tối đa | **4 giây**, từ lúc gửi câu hỏi đến khi bắt đầu nghe được lời trả lời; chưa có kết quả chứng minh đạt |

Các trường ngôn ngữ/giới tính/vùng giọng ở đây là tiêu chí đánh giá và thiết kế. Chúng không phải cấu hình model đã áp dụng, phê duyệt voice cloning, lựa chọn model mới hoặc bằng chứng một checkpoint đáp ứng được yêu cầu.

## Thời gian chờ nghĩa là gì?

Trong trải nghiệm trò chuyện, đó là khoảng thời gian từ lúc bạn **gửi câu hỏi đã nói** đến lúc **bắt đầu nghe được câu trả lời**. Chủ dự án đã xác nhận chọn tối đa **4 giây** sau khi được giải thích. Ví dụ 4 giây ban đầu vẫn chỉ là ví dụ ở thời điểm cũ; xác nhận mới là nguồn chốt mục tiêu. Độ dài câu trả lời khi phát hết là một đại lượng khác, không bị giới hạn 4 giây bởi quyết định này.

Khoảng chờ có thể gồm nhận dạng giọng nói, tạo câu trả lời, tổng hợp giọng và chuyển audio tới thiết bị phát. Thời gian bạn đang nói hoặc đang cân nhắc trước khi bấm gửi không nên tính thành thời gian xử lý của hệ thống.

Luồng D72 hiện có là ví dụ CLI được đệm toàn bộ: ghi thời gian từ submission tới có đủ PCM trả lời, **chưa đo thời điểm loa bắt đầu phát trong một sản phẩm người dùng**. Sáu số đo khoảng 8–49 giây được giữ riêng ở [bảng D74](D74_VOICE_DECISION_BRIEF.md); không tráo chúng thành số đo first-audible, p95 hoặc cam kết cho giọng nữ miền Bắc chưa được đánh giá. Recorder D71 hiện chỉ thu/nghe lại và không có gửi câu hỏi tới model.

## Tiêu chí 4 giây và phần cần kiểm chứng

- Mục tiêu: từ submission rõ ràng của câu hỏi đã nói tới **lời trả lời thực sự bắt đầu phát tại thiết bị người dùng**, tối đa 4 giây. Phải tính cả ASR, tạo câu trả lời, TTS, chuyển audio và bắt đầu phát.
- Không lấy beep, khoảng lặng hoặc thông báo đang xử lý làm thời điểm đã trả lời. Không dùng thời gian model sinh token đầu hoặc PCM đầu thay cho thời điểm người dùng nghe được.
- Đây là giới hạn tối đa đã yêu cầu, không tự đổi thành trung bình hoặc p95. Protocol cần khai báo workload, độ dài input/output, trạng thái nạp/cache, điều kiện thiết bị/concurrency và cách đo nhất quán; giữ cả timeout/lỗi/vượt 4 giây, không chỉ chọn lượt nhanh.
- **Chưa có phép đo first-audible chứng minh đạt 4 giây.** Cần thiết kế/benchmark cụ thể trước khi nghiệm thu; các ví dụ D72 buffered không thay thế phép đo đó. Không tự thay model, timeout/resource cap, streaming hoặc kiến trúc để coi như đã đạt.

Đây là mục tiêu trải nghiệm, không phải yêu cầu cắt câu trả lời hoặc hủy mọi tiến trình đúng giây thứ 4. Chính sách báo lỗi/timeout vẫn phải được thiết kế và duyệt riêng. Giữ giới hạn thực thi hiện có; không có thay đổi runtime trong lần ghi yêu cầu này.

## Tác động tới D74

Phương án cần xét trước nay là **VI giọng nữ miền Bắc**, không phải ưu tiên triển khai EN. Qwen Ryan vẫn chỉ là một ứng viên EN đã được nghe; kết quả EN không chứng minh phù hợp yêu cầu VI. VI-Auto đã có lỗi và Piper VI voice đã bị chủ dự án nhận xét không tự nhiên/không thích tông. Chưa có bằng chứng một voice đã đánh giá đáp ứng đồng thời tiếng Việt, nữ, miền Bắc và độ tự nhiên mong muốn; không tự gán giới tính/vùng giọng hoặc đánh dấu model đạt.

Bước chuẩn bị tiếp theo có thể đối chiếu metadata/provenance và bằng chứng của các ứng viên đã thống nhất với tiêu chí mới, lập protocol/đề xuất cụ thể cho khoảng trống còn lại. Một đề xuất tải/đổi model hoặc voice phải có benchmark, hiệu năng/tài nguyên, migration, rollback và chủ dự án duyệt trước khi thực hiện. Tài liệu này không phê duyệt một lượt inference, download hoặc thử nghiệm mới.

**Snapshot khảo sát/proposal trước phê duyệt, ngày 2026-11-03:** [shortlist có nguồn](D74_VI_VOICE_CANDIDATE_SURVEY.md) đề xuất đánh giá VieNeu-TTS v3 Turbo FP32/CPU, Trúc Ly và Ngọc Huyền; chưa chọn hoặc tải model. [ADR-154](ADR/154-proposed-isolated-vietnamese-voice-feasibility-campaign.md)/[protocol](D74_VI_VOICE_BENCHMARK_PROTOCOL.md) giữ comparison Piper/both ASR, tổng16payload files608,816,450bytes và cap8GiB toàn thư mục trial. Bằng chứng ASR cũ cho thấy Qwen riêng prediction đã vượt4giây ở17/20câuVI; thay TTS một mình không đủ. Implementation/benchmark/giọng nghe/first-audible vẫn chưa đạt hoặc chưa thực hiện.

## Backlog và đánh giá trước khi xếp lịch

| Task | Ưu tiên / trạng thái | Dependency | Effort | Rủi ro |
|---|---|---|---|---|
| VOICE-VI-NORTH-FEMALE-001 | P1; phản hồi nhóm thích Trúc Ly/Ngọc Huyền hơn, ngữ điệu/cách đọc còn lỗi; chưa chọn model | Metadata/rights của ứng viên, benchmark D70/D72, protocol và approval cụ thể khi cần thay đổi | Một milestone đối chiếu/proposal; effort chạy/triển khai chưa ước lượng khi chưa có phương án | Voice không đúng vùng/giới tính/cảm nhận, sai dấu/phát âm, thiếu quyền hoặc vượt tài nguyên |
| VOICE-TEXT-READING-001 | P1; renderer nghiên cứu/48clip mới đã có; lỗi đọc acoustic giờ/ngày/Python/API chờ đánh giá | Quy tắc đọc giờ/ngày và Python/API mong muốn; kiểm normalizer hiện có; protocol/quyền đánh giá | Một milestone điều tra/thiết kế và một milestone đánh giá riêng; chưa ước lượng thời gian | Sai nghĩa hoặc thay code/URL/ID, sai ngày nhập nhằng, phát âm chỉ đúng vài ví dụ; giữ text gốc/trace và tính chi phí vào latency |
| VOICE-PROSODY-001 | P1; đã thử adapter giữ dấu hỏi/chia câu; độ tự nhiên chờ đánh giá | Ví dụ nghe/tiêu chí chấp nhận; kiểm preset/chunking/dấu câu; protocol/quyền đánh giá | Một milestone điều tra/proposal, một milestone nghe so sánh; chưa ước lượng | Chưa xác định nguyên nhân; không hứa sửa bằng dấu câu/tốc độ, tự thay model hoặc sửa audio cũ |
| VOICE-EN-001 | P1 trong mục tiêu voice; sau ưu tiên VI, lịch/release chưa chốt | Bằng chứng EN đã có, quyết định chất giọng và độ trễ/rights | Một milestone quyết định trước khi ước lượng tích hợp | Tự coi EN benchmark là sản phẩm hoặc bỏ yêu cầu EN khi ưu tiên VI |
| VOICE-LANGUAGE-CUSTOM-001 | P2; **PENDING LATER VERSION**, chưa xếp ngày/phiên bản | Ngôn ngữ ASR/TTS thực sự hỗ trợ, UI chọn language/voice, provenance/rights và thiết kế mapping được duyệt | Một milestone thiết kế; implementation/benchmark chưa ước lượng | Nhầm Auto với hỗ trợ chính thức, silent fallback, sai voice/ngôn ngữ hoặc để input tự tải/chọn model |
| VOICE-LATENCY-AC-001 | P1; **target 4 giây giữ nguyên; ADR173 UI/HTTP PASS6/6; physical first-audible PENDING** | Phạm vi submission→first-audible thực tế, workload/measurement plan và quyền chạy phù hợp | Local compute + UI/HTTP đã xong; còn kiểm chứng thiết bị thực | Nhầm target đã chốt với đạt hiệu năng, nhầm PCM với playback hoặc timeout với UX; che load/cache/device/concurrency |

Đây là phân loại backlog, không tự cấp quyền triển khai hay thêm phase/ngày. Nếu thiết kế chọn ngôn ngữ, streaming hoặc runtime làm thay đổi kiến trúc, phải có ADR riêng trước khi áp dụng.

## Những bằng chứng giữ nguyên

D70 nghe 24/24 và bộ capture/playback microphone người dùng đã đạt trong phạm vi đã báo cáo. Giữ mọi audio/nhãn/kết quả chưa đạt, lựa chọn model/config hiện có và D60 đang chờ. D74 sản phẩm và D90 release vẫn mở. Cập nhật yêu cầu này chỉ sửa tài liệu/thêm evidence, không sửa source, download, inference, endpoint, Vault, Docker hoặc database.

## Trạng thái thử nghiệm sau phê duyệt ADR-154

[Campaign thực tế](D74_VI_VOICE_CAMPAIGN_RESULT.md) có24clip TTS và đã nhận [phản hồi nhóm](D74_OWNER_VOICE_FEEDBACK_20261103.md): cả ba ổn, thích Trúc Ly/Ngọc Huyền hơn; ngữ điệu máy móc và lỗi đọc giờ/ngày/Python/API vẫn mở. Chưa có nhãn từng clip hoặc chốt giọng. Workflow dừng vì lỗi bộ đọc metadata,6slot không hợp lệ/42chưa chạy; bản sửa161tests PASS không phải benchmark native mới. [ADR-155](ADR/155-proposed-workflow-recovery-after-caller-metadata-failure.md) chuẩn bị riêng lượt workflow thay thế, chờ duyệt, không tải thêm hoặc lặp standalone. Yêu cầu4giây first-audible vật lý giữ nguyên và chưa được kiểm chứng.

## Triển khai nghiên cứu theo lệnh “Làm đi”

[ADR156 và kết quả48clip](D74_SPEECH_READING_QUALITY_RESULT.md): phần render speech riêng và đường giữ dấu hỏi đã có221test PASS, chạy đúng48TTS trên weights hiện có; chưa tích hợp sản phẩm hoặc xác nhận chất lượng nghe.12/16cặp raw–reading giống hệt; không báo lỗi giờ/ngày đã được sửa trong audio. Chờ nhận xét bộ so sánh mới; ADR155workflow vẫn chưa duyệt/chưa chạy. Text hiển thị/model/default/target4giây giữ nguyên.

## Chủ dự án xác nhận phần date/prosody, giữ lỗi tiếng Anh riêng

[Phản hồi mới và bản sửa tiếp](D74_ENGLISH_READING_FOLLOWUP.md): giờ/ngày đã chuẩn trên bộ nghe; `clauses` được đánh giá tốt nhất/tự nhiên nhất. Đây là phạm vi đã đạt cần giữ nguyên, không phải mọi quality gate đạt. Python phải đọc như tiếng Anh; API rè/run ở cả2giọng chưa đạt. Renderer mới bỏ chỉ phiên âm Việt và đã tạo8clip trên cùng weights; chờ nghe, chưa chọn voice/model hoặc mở ADR155workflow.


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

**Updated owner language/voice requirement:** retain the same perceived speaker identity for Vietnamese and American English (en-US). Natural/accurate English pronunciation is required; current owner-reported Vietnamese accent is not accepted. This does not select between the two presets, authorize training/cloning/model replacement or remove earlier registry candidates.


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


## D74 reading workflow integration — 2026-11-04

[ADR164 implementation/software result](D74_WORKFLOW_READING_BRIDGE_RESULT.md): optional research bridge now preserves original CORE answer while binding/auditing separately rendered speech, verifies reading-profile/native provenance and reuses original VoicePipeline/gateway/playback conversion.386related PASS/0FAIL/ERROR/SKIP6.09s including58new controls; original SDK probe20/20planned/0unknown, all10accepted Trúc Ly controls exact phone/chunk/gap/cap parity.46priorresearch/750application/210protected/4295SDKentries unchanged;0newnative model/provider/download/product actions. This is software/frontend proof, not native workflow/physical4second acceptance.

Next bounded work is the exact reading-aware workflow operator/scope and real measurements; ADR155 old plan stays immutable/locked. Arbitrary CORE text remains subject to declared protected-input/ambiguous-mapping/chunk/token bounds, with no truncation or hidden fallback. Both pronunciation refinement cycles remain stopped; no new model/voice/default selection. Native/full-product/rights/no-speech/device/4second/D90release gates open; D60deferred.


## D74 real-model reading workflow — 2026-11-04

[ADR165 measured result](D74_NATIVE_READING_WORKFLOW_RESULT.md): owner “Chay để xác nhận đi” authorizes a new fixed reading-aware cohort;48/48observed,48ASR/48CORE/48TTS,0retry/0unattempted/0runtime-or-guard failure.32speech trials produce complete native/playback audio; all16negative trials (2old sources×8combinations) incorrectly produce text and spoken answers. Buffered≤4s only6/32speech, Trúc Ly1/16; warm Whisper–Trúc Ly3.335–6.363s, warm Qwen–Trúc Ly4.264–11.122s. Physical first-audible remains UNVERIFIED; max4second/no-speech gates NOT ACCEPTED, not a D74/product PASS.

398related software PASS/0FAIL/ERROR/SKIP6.11s; actual48chain/24reading mapping/56workers+COREretirement/source/archive/14ASRcheckpoint/4295SDK/23475TTSruntime/52oldresearch/750application/210protected preservation verified, baseline restored. All24COREanswers required zero text/term edits: native wiring is verified, complex-edit runtime coverage is not invented. Original answer semantics/acoustic quality not rescored; all first observations retained. New Trúc Ly/Piper/bothASR research comparison does not choose a model/default; both pronunciation refinement cycles remain stopped. Old ADR155raw stays unexecuted/unchanged; new ADR165completed separately.

Next P1 work: AUDIO-VAD-ASR-001 follow-up on16no-speech failures, preserving quiet/EN speech/clocks; one design/control milestone then bounded measurement, risk false speech rejection/known old concatenation regressions. VOICE-LATENCY-AC-001 needs stage-based ASR/TTS profiling and separately scoped optimization; resident helps but does not satisfy max4s for Trúc Ly. No model/GPU/context/cap/gate changes or new campaign scheduled. Device/auth/retention/rights/default/product/D90release remain open; D60owner-deferred.


## D74 whole-clip presence follow-up — 2026-11-04

[ADR166 prototype and actual results](D74_WHOLE_CLIP_PRESENCE_RESULT.md): the optional research gate admits the identical full PCM/clock when original Silero v5 finds speech, otherwise the original pipeline refuses before downstream ASR/CORE/TTS. Existing application/models/thresholds/defaults stay unchanged; no concatenation or product activation. 524 related PASS/0FAIL/ERROR/SKIP in 6.47s, including 61 new controls.

100 actual VAD observations / 7 clean workers cover 40 unique original VI/EN speech recordings (40 admitted), 2 padded repeats (2 admitted), 5 authored negatives (5 refused) and 6 derived quiet controls (4 admitted, 2 EN refused). The panel is reused, quiet controls have inherited coarse labels and downstream calls are explicit software sentinels, not native ASR/CORE/TTS. Six original D74 ASR input hashes match; 1903 prior code/evidence files plus the 750-application/210-protected baseline and native/container state remain preserved. Original ADR165 16/16 erroneous negative replies and latency failures are not overwritten; no max4second/device/product PASS.

AUDIO-VAD-ASR-002 P1 is assessed as the next research candidate: detector-only amplitude-normalized view while ASR keeps original PCM, with separately fixed bilingual/quiet/negative controls, source/view provenance, one design/control and bounded comparison milestone. Risks are noise/DC/clipping amplification and overfit; no algorithm/gain/model switch, new measurement or activation is chosen here. Short/quiet-word sensitivity, native full-workflow integration, physical timing/rights/default/product/D90release remain OPEN; D60 deferred and both pronunciation cycles stopped.


## D74 local detector/native gate verified — 2026-11-04

[Actual gate result](D74_DETECTOR_PEAK_GATE_RESULT.md): AUDIO-VAD-ASR-002 local detector and native no-speech checks PASS. Fixed detector-only peak0.5 normalization preserves original ASR PCM/clock; original Silero/settings/model/voice/default remain unchanged. Gain32candidate99/100 remains FAIL; v2records147/147correct (80original speech/46quiet derivatives/6padded repeats admitted,15negative rows refused),288actual VAD observations.20utterances are fresh relative to fix selection; inherited quiet labels and repeated signals are not independent acoustic acceptance.

Conditional ADR168native scope is now8/8PASS:4complete speech outputs and4correct early no-speech refusals, exactly4ASR/4CORE/4TTS plus8VADcalls,0retry/guard/runtime failure and restored baseline. This repeats2VI speech/2negative sources across2ASRs; it is not native quiet-ASR/semantic quality or a repaired original48turn score.592relatedPASS/0FAIL/ERROR/SKIP7.67s; all first failures/source snapshots and original750application/210protected/14post-verified ASR artifacts preserved. No model/package download or shared-service/provider/Vault/database/Docker mutation; product gate remains unactivated.

Next assessed P1 VOICE-LATENCY-AC-001: residency/stage profiling with unchanged quality/models/resource guards, one design/control milestone then separately bounded measurement. Dependency: qualified local gate and retained timing/endpoint/playback contracts; risks co-residency RAM, cancellation/TTL and PCM-versus-speaker timing. Current cold buffered speech11.211–17.857s is NOT max4second PASS. Real mic/short/quiet-word/noise/rights/model/default/product and physical timing remain OPEN; D60 deferred, pronunciation cycles stopped, D90 NOT RELEASED.
