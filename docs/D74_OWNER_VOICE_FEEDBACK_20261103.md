# D74 — Nhận xét của chủ dự án về ba giọng thử

**Mục đích:** Ghi nhận phản hồi nghe mới, tách sở thích chất giọng khỏi lỗi cách đọc và nghiệm thu sản phẩm.

**Ngày:** 2026-11-03, Asia/Saigon. **Trạng thái:** Đã nhận phản hồi định tính ở cấp nhóm; chất lượng còn vấn đề, chưa chọn giọng/model và chưa duyệt workflow recovery. [Receipt nguyên văn](evidence/d74-owner-voice-feedback-20261103.json), [24 clip và kết quả kỹ thuật](D74_VI_VOICE_CAMPAIGN_RESULT.md).

## Nhận xét đã nhận

| Nội dung | Phản hồi của chủ dự án | Trạng thái |
|---|---|---|
| Tổng thể | Cả ba giọng đều ổn | Nhận xét tổng quát, chưa phải tất cả AC đạt |
| Sở thích | Thích Trúc Ly và Ngọc Huyền hơn Piper | Giữ cả hai trong nhóm ưu tiên; chưa chọn giữa hai giọng |
| Ngữ điệu | Máy móc, không tự nhiên | Vấn đề chất lượng còn mở |
| Giờ và ngày | Đọc chưa đúng format | Cần xác định quy tắc đọc mong muốn và kiểm chứng |
| Tên/thuật ngữ tiếng Anh | Python và API đọc không đúng | Cần xác định cách phát âm mong muốn và kiểm chứng |

Đây là phản hồi cho nhóm ba giọng, không phải 24 nhãn riêng. Người dùng chưa gán từng lỗi cho một giọng/clip cụ thể, chưa chốt cách đọc giờ/ngày/Python/API hoặc xác nhận thiết bị nghe trong lần này. Không tự tạo điểm MOS, xác nhận không rè/méo, kết luận accent/gender hay 24/24 clip đã nghe. Không yêu cầu người dùng lặp lại toàn bộ việc nghe chỉ để điền biểu mẫu; có thể nhận ví dụ hoặc cách đọc mong muốn ngay trong chat khi cần thiết kế phần sửa.

Nhận xét này thuộc panel ADR-154. Các nhận xét D70 trước đó thuộc corpus riêng và được giữ nguyên, kể cả ý kiến không thích Piper VI ở lần cũ.

## Hướng xử lý được đưa vào backlog

Hai hướng dưới đây là đề xuất điều tra và thiết kế, chưa phải kết luận nguyên nhân hoặc quyền chạy model mới.

| Task | Ưu tiên / lịch | Dependency | Effort | Rủi ro và điều kiện nghiệm thu |
|---|---|---|---|---|
| VOICE-TEXT-READING-001 | P1 trước nghiệm thu cách đọc VI; chưa xếp ngày hoặc chạy thử | Cách đọc giờ/ngày mong muốn; tham chiếu phát âm Python/API; kiểm source normalizer hiện có; protocol và quyền chạy phù hợp | Một milestone điều tra/thiết kế và một milestone đánh giá riêng; thời gian chưa ước lượng | Chuẩn hóa sai ngày nhập nhằng, mã định danh/code/URL hoặc ý nghĩa câu; biến từ viết tắt thành cách đọc không mong muốn; chỉ đúng vài mẫu. Giữ text trả lời gốc và bản dành cho phát âm riêng, trace phép biến đổi; test số/ngày/giờ/thuật ngữ cùng trường hợp không được thay đổi. Đánh giá trên mẫu chưa dùng để thiết kế, giữ mọi lỗi và tính thêm chi phí xử lý vào latency |
| VOICE-PROSODY-001 | P1 trước chấp nhận độ tự nhiên; chưa xếp ngày hoặc chạy thử | Ví dụ có vấn đề và tiêu chí nghe; kiểm khả năng preset/chunking/dấu câu hiện có; protocol và quyền chạy phù hợp | Một milestone điều tra/proposal, sau đó một milestone nghe so sánh; chưa ước lượng | Chưa biết lỗi đến từ model, preset hay xử lý văn bản. Không hứa sửa được bằng dấu câu/tốc độ hoặc tự đổi model. Giữ nghĩa, text/audio gốc và bằng chứng chưa đạt; không cắt/gain-repair audio cũ, không đổi yêu cầu4giây. Chủ dự án đánh giá lại bằng clip mới có provenance rõ ràng |

Ưu tiên điều tra cách biểu diễn văn bản đọc và ngữ điệu trên các thành phần đã có trước khi đề xuất tải/thay model. Nếu cần lớp chuyển đổi speech text hoặc thay đổi composition, phải có thiết kế/ADR phù hợp, benchmark, phân tích chi phí và rollback trước khi áp dụng. Một phương án có thể quay lui bằng tắt adapter nghiên cứu và trả lại đường đọc gốc; chưa có adapter nào được triển khai ở cập nhật này.

## Giới hạn và bước tiếp theo

[ADR-155](ADR/155-proposed-workflow-recovery-after-caller-metadata-failure.md) vẫn **NOT APPROVED / NOT EXECUTED**. Nhận xét nghe không tự cấp quyền chạy lại 48 slot. Fixed workflow voice vẫn là Trúc Ly theo preregistration; không đổi sang Ngọc Huyền sau khi xem kết quả. Nếu sửa text đọc hoặc settings, đó là biến thể cần đánh giá riêng, không được tráo vào benchmark gốc và ghi là cùng cấu hình.

Mục tiêu tối đa4giây từ submission tới first-audible vẫn chưa được kiểm chứng. Quyền sử dụng, no-speech, chất lượng, model/voice selection, D74 sản phẩm và D90 release còn mở. D60 giữ trạng thái chờ. Chỉ cập nhật tài liệu và devlog; không inference, tải model, đổi source/config, Vault, database, Docker hoặc provider.
