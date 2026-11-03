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
