# D74 — Kiểm tra “vi phạm”, số La Mã và Python

**Mục đích:** Ghi nhận API đã được người dùng xác nhận đọc đúng, Python còn sai, và kiểm chứng cách đọc theo ngữ cảnh trên đúng SDK/model hiện có.

**Ngày:** 2026-11-04, Asia/Ho_Chi_Minh. **Trạng thái cập nhật:** chủ dự án xác nhận **VI/vi đã ổn trên panel đã nghe**; tiếng Anh còn accent Việt/chưa đạt. [Phản hồi mới](evidence/d74-vi-xi-bilingual-owner-feedback.json). Kết quả kỹ thuật5/5 kỳ vọng chuẩn hóa/10clip dưới đây giữ nguyên; không tự tạo nhãn từng clip. [Kiểm XI và mục tiêu cùng giọng Anh–Mỹ](D74_XI_BILINGUAL_RESULT.md). [Phản hồi nguyên văn](evidence/d74-api-python-roman-owner-feedback.json), [protocol](D74_ROMAN_CONTEXT_PROTOCOL.md), [kết quả máy](evidence/d74-roman-context-result.json), [xác minh sau chạy](evidence/d74-roman-context-verification.json).

## Kết quả phân biệt ngữ cảnh

Đã chạy normalizer/G2P/tokenizer thật, không thêm luật thay số hay sửa cách đọc:

| Đầu vào | Đầu vào phát âm sau chuẩn hóa | Kiểm tra |
|---|---|---|
| Hành vi vi phạm này cần được kiểm tra. | hành vi vi phạm này cần được kiểm tra. | Giữ hai chữ `vi`, không thành `sáu` |
| VI PHẠM là cụm từ tiếng Việt. | vi phạm là cụm từ tiếng việt. | Viết hoa vẫn là từ tiếng Việt |
| Chương VI có sáu mục. | chương sáu có sáu mục. | VI trong số chương chuyển thành sáu |
| CHƯƠNG VI nói về hành vi vi phạm. | chương sáu nói về hành vi vi phạm. | Phân biệt được hai cách dùng trong cùng câu |
| Chương IV và chương IX cần được đọc lại. | chương bốn và chương chín cần được đọc lại. | Kiểm frontend bổ sung; chưa sinh audio cho mục này |

“Mã định danh VI phải được giữ nguyên.” trở thành “mã định danh vi phải được giữ nguyên.”, không chuyển VI thành sáu. Đây là **quan sát**, chưa có yêu cầu người dùng chốt phải đọc mã đó theo chữ cái hay âm `vi`, nên không chấm là đúng/sai. Không suy rộng năm ví dụ thành mọi số La Mã hoặc mọi tên viết tắt.

Native trace của tám clip La Mã/từ Việt khớp đúng chuỗi phoneme từ probe ở bốn hàng đầu. Điều này chứng minh đường tổng hợp nhận đúng cách diễn giải, không thay thế việc nghe xem âm thanh thực tế có rõ/đúng không.

## API và Python

Người dùng xác nhận **API đã phát âm đúng trên panel vừa nghe**; giữ nguyên source/policy/audio ADR-159. Python tiếng Anh vẫn **OWNER REPORTED NOT ACCEPTABLE**. Phản hồi chưa xác nhận riêng API hết rè/run hoặc chất lượng toàn bộ câu; không tự đóng các gate đó hay chọn model/giọng/sản phẩm.

Trong SDK thật, Python tự nhận dạng và Python được bọc `<en>python</en>` đều cho cùng chuỗi `pˈaɪθən`; cả câu mixed cũng cho phoneme giống nhau. Vì vậy không tuyên bố thêm tag tiếng Anh là bản sửa và không sinh lại một candidate tag-only giống đầu vào.

Thêm đúng hai control: “I write code in Python every day.”, mỗi giọng một clip. Chuỗi Python đầu vào vẫn như trên. Đây là kiểm tra ngữ cảnh tiếng Anh, **chưa phải bản sửa Python**; câu khác ngữ cảnh không cho phép kết luận nhân quả hay xếp hạng model. Hai clip mixed Python/API cũ giữ nguyên để tham khảo.

## Audio và kiểm thử

[Mở trang nghe](../data/backups/d74-vi-approved-campaign-20261103/roman-context-first/review/index.html): tám clip `vi`/`VI`, hai control Python trong câu tiếng Anh và hai clip mixed cũ giữ nguyên. Trang tự chứa 12 WAV, không script/server/microphone/upload/network. [Toàn bộ hai file code/test mới](../data/backups/d74-vi-approved-campaign-20261103/roman-context-first/review/full-code.zip), source đã chạy lưu riêng trong `executed-source/`.

**10 TTS/10 inner chunks/EOS=true**, 0 lỗi/0 chưa gọi/0 retry; worker exit0/joined. Wall 8,511 giây, peak RSS RAM lấy mẫu khoảng1261,6 MiB; TTS riêng0,410–0,819giây. CPU0,1/hai threads/AS8GiB/RSS2GiB/headroom14GiB/root8GiB/wall120s, original frame caps giữ nguyên. Không suy từ TTS riêng thành first-audible vật lý≤4giây.

**275 PASS / 0 FAIL / 0 ERROR / 0 SKIP, 5,03 giây**, Ruff format/lint PASS trước freeze. Tám tests mới kiểm ngữ cảnh viết thường/hoa/La Mã, từ chối normalized text sai hoặc unknown token, tag-equivalence, actual phoneme/EOS/frame/chunk provenance, giới hạn10/10, lỗi đầu/cancellation/join và trang nghe không tạo nhãn chất lượng giả. Không có lỗi test mới trong lượt này. Full5889 vẫn là snapshot lịch sử.

750 application/210 protected files,29 research files trước,4295 SDK inventory entries, weights/presets/audio cũ và API đã đọc đúng được giữ nguyên. Không đổi code đọc/normalizer/SDK/model; chỉ thêm benchmark controller/tests. Native/container baseline phục hồi; 0 download/package/ASR/CORE/Brave/Vault/database/Docker mutation.

## Tiến độ

VOICE-CONTEXT-READING-001 P1 hoàn tất kiểm frontend theo corpus, phần nghe còn mở. Python tiếp tục task P1 English reading; API pronunciation accepted-scope giữ riêng với API artifact/timbre chưa đánh giá lại. Phần ngày/giờ/clauses đã chấp nhận không đổi. ADR155 workflow chưa duyệt/chưa chạy, D60 deferred; model/voice/rights/no-speech/physical4second/product/D90release vẫn mở.
