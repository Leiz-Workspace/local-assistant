# Voice — Yêu cầu ngôn ngữ, chất giọng và thời gian chờ

**Mục đích:** Ghi đúng yêu cầu chủ dự án để định hướng D74 và backlog voice, tách biệt yêu cầu sản phẩm với việc chọn hoặc triển khai model.

**Ngày:** 2026-11-03, Asia/Ho_Chi_Minh. **Trạng thái:** REQUIREMENTS AND 4-SECOND TARGET RECORDED / PERFORMANCE UNVERIFIED. [Yêu cầu ban đầu](evidence/d74-voice-requirements-20261103.json) giữ nguyên lịch sử; [xác nhận “4 giây đi”](evidence/d74-latency-target-4s-20261103.json) chốt giới hạn thời gian chờ.

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
| VOICE-LATENCY-AC-001 | P1; **target 4 giây đã chốt; ADR154 protocol đã duyệt, workflow recovery/physical timing PENDING** | Phạm vi submission→first-audible thực tế, workload/measurement plan và quyền chạy phù hợp | Một milestone thiết kế/benchmark; effort chạy chưa ước lượng khi chưa có phương án | Nhầm target đã chốt với đạt hiệu năng, nhầm PCM với playback hoặc timeout với UX; che load/cache/device/concurrency |

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
