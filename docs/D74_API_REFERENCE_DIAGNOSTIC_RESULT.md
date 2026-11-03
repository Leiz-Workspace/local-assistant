# D74 — Đối chiếu cách đọc API và điều kiện âm thanh tham chiếu

**Mục đích:** Ghi kết quả điều tra yêu cầu đọc API như tiếng Anh “Ei–Pi–Ai”, giữ nguyên lỗi đầu tiên, các bản đã nghe và phần giờ/ngày/ngắt câu đã được chấp nhận.

**Ngày:** 2026-11-04, Asia/Ho_Chi_Minh. **Trạng thái:** tám clip câu đầy đủ đã hoàn tất kỹ thuật; phát âm, rè/run và chất giọng **CHỜ NGHE**, chưa xác nhận sửa được lỗi. Không thay model, chọn giọng hoặc áp dụng cấu hình mới vào sản phẩm. [ADR-158](ADR/158-paired-api-phoneme-and-reference-diagnostic.md), [kết quả máy](evidence/d74-api-reference-result.json), [kiểm tra sau chạy](evidence/d74-api-reference-verification.json).

## Nghe đối chiếu

[Mở trang nghe tám clip, bốn cặp](../data/backups/d74-vi-approved-campaign-20261103/api-reference-first/context-followup/review/index.html). Mỗi hàng có cùng câu và giọng Trúc Ly hoặc Ngọc Huyền; hai bên lần lượt dùng/không dùng mã âm thanh tham chiếu của preset. Đặc trưng người nói vẫn được truyền nguyên hash ở cả hai bên, nhưng cảm nhận chất giọng có thể thay đổi.

Hai câu mới: “Chị sẽ hướng dẫn cách gọi API ngay bây giờ.” và “Please say A, P, I.” Với mỗi cặp, cần nghe: chữ A có thành **Ei** không, API có rè/run không, và giọng còn tự nhiên/giống giọng mong muốn không. Không suy ra bên nào tốt hơn từ tên điều kiện hoặc thời gian xử lý. Đây là đối chiếu chẩn đoán có nhãn, không phải benchmark mù độc lập.

[Bốn clip hoàn chỉnh của lượt đầu cùng trạng thái lỗi/chưa chạy](../data/backups/d74-vi-approved-campaign-20261103/api-reference-first/review/index.html). Clip Ngọc Huyền thiếu kết thúc không được phát như một clip đạt. [Toàn bộ sáu file code/test mới](../data/backups/d74-vi-approved-campaign-20261103/api-reference-first/context-followup/review/full-code.zip); bản source đã chạy cũng được giữ riêng trong `executed-source/` của từng lượt.

## Đã xác minh được gì?

Tokenizer mã hóa/giải mã đúng từng ký tự phoneme, không có unknown token; chưa tìm thấy việc làm mất âm `/eɪ/`. SDK có dạng API đứng riêng `ˌeɪpˌiːˈaɪ` và dạng trong câu `ˈeɪ pˈiː ˈaɪ`. Probe đầu tiên từ chối dạng compact vì kỳ vọng chuỗi quá cụ thể; giữ nguyên lần từ chối và đầu ra điều tra. Đây không phải bằng chứng dictionary/tokenizer hỏng.

Source SDK cho thấy đặc trưng người nói vẫn được chiếu và cộng vào các hàng embedding khi bỏ mã âm thanh tham chiếu. Vì vậy lượt đối chiếu mới chỉ đổi việc đưa các hàng mã tham chiếu vào prompt; giữ nguyên phoneme, token ID thực tế, speaker embedding, projected anchor, seed, sampling, codec, trọng số và giới hạn frame. Bốn cặp thực tế đều khớp các bất biến này; phía bật có 59 hàng tham chiếu cho Trúc Ly/63 cho Ngọc Huyền, phía tắt có 0. Bốn cặp waveform khác nhau; điều đó **không chứng minh** “Ei” đúng hoặc hết rè. Chưa xác định nguyên nhân âm học của lỗi chủ dự án nghe.

## Hai lượt được giữ riêng

| Lượt | Số mục khai báo | Đã gọi TTS | Hoàn chỉnh | Lỗi | Chưa gọi |
|---|---:|---:|---:|---:|---:|
| ADR-158, chữ/cụm/câu ngắn | 16 | 5 | 4 | 1 | 11 |
| Câu đầy đủ theo protocol riêng | 8 | 8 | 8 | 0 | 0 |

Lượt đầu dừng ngay khi chữ A đứng riêng của Ngọc Huyền chạm cap gốc **13 frame nhưng EOS=false**. Giữ lỗi `native_generation_did_not_end`, không tăng cap, retry hoặc chạy tiếp 11 mục. Điều kiện tắt tham chiếu chưa được thử trong lượt này. Bốn clip Trúc Ly trước đó hoàn chỉnh. Không dùng lỗi control xuất hiện sau để giải thích chắc chắn lỗi API contextual trước đó: tám clip contextual cũ đã có EOS.

[Protocol câu đầy đủ](D74_API_CARRIER_PROTOCOL.md) được ghi riêng sau lần dừng, trước khi chạy tám mục mới; không đổi tên/hoàn thành lại cohort 16 mục. Cap được tính bằng đúng hàm gốc theo độ dài câu: VI 13 syllable/156 frame, EN 5 syllable/74 frame. Đây là stimulus khác, không chứng minh chữ A đứng riêng đã đạt. Tổng thực tế **13/16 request tối đa**, không retry, ba suất còn lại không được dùng. Tổng 24 mục khai báo giữ đúng 12 hoàn chỉnh/1 lỗi/11 chưa gọi; không công bố original16 PASS.

## Kiểm thử và tài nguyên

Trước lượt đầu: **250 PASS**; trước lượt câu đầy đủ: **257 PASS / 0 FAIL / 0 ERROR / 0 SKIP, 4,29 giây**. Ruff format/lint E4,E7,E9,F PASS; source được đóng hash trước chạy. Tests kiểm tra controller, giới hạn request, dừng lỗi đầu tiên, không retry, bất biến cặp, token/input binding, hoàn tất native và trang nghe không có script/microphone/upload/network. Đây là scope phần mềm liên quan, không phải full regression mới hoặc đánh giá nghe. Full 5889/750 application files vẫn là snapshot lịch sử. Lỗi decoder chập chờn của lượt trước vẫn giữ, chưa xác định nguyên nhân hoặc tuyên bố sửa.

Ba worker TTS lần lượt dùng peak RSS RAM lấy mẫu khoảng **1219,9 / 1261,2 / 1272,4 MiB**; không đo VRAM vì chạy CPU. Thời gian worker tương ứng 3,655/4,749/4,684 giây, tổng 13,088 giây. Worker đầu bị dừng/join sau lỗi; hai worker câu đầy đủ thoát 0/join. Giữ AS 8 GiB, RSS TTS 2 GiB, headroom 14 GiB trước nạp, CPU 0,1/hai threads, tổng thư mục ≤8 GiB; lượt câu đầy đủ siết wall deadline còn 120 giây. Thời gian TTS riêng khoảng 0,47–0,90 giây không thay thế thời gian gửi câu hỏi tới loa phát và **không chứng nhận mục tiêu 4 giây**.

750 file application/210 file bảo vệ, 19 file nghiên cứu trước, SDK/weights/presets và audio trước giữ nguyên. Sáu file code/test mới khớp source đã thực thi và bản ZIP. Native/container baseline được phục hồi. Không tải weights/package, gọi ASR/CORE/Brave, thay Vault/database/Docker hoặc kích hoạt đường sản phẩm.

## Trạng thái và bước tiếp theo

VOICE-ENGLISH-READING-001/VOICE-API-ARTIFACT-001 vẫn P1: nghe bốn cặp để xác định Ei, rè/run và thay đổi giọng trước khi đề xuất tiếp. Chưa tự chọn `without_reference`; kết quả nhỏ, thích ứng theo lỗi và carrier có thể không khái quát. Python không nằm trong lượt mới nên vẫn mở; giờ/ngày và `clauses` đã chấp nhận theo panel trước giữ nguyên. Không thay đổi đề cử/lựa chọn model trong registry.

ADR-155 với 48 workflow vẫn chưa duyệt/chưa chạy. D60 tiếp tục để pending theo yêu cầu. D74 voice/model/rights/no-speech, đo vật lý first-audible ≤4 giây, tích hợp sản phẩm và D90 release vẫn mở; D70 đánh giá offline 24/24 với giới hạn chất lượng giữ nguyên.
