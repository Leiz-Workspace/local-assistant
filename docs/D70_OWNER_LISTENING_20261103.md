# D70 — Kết quả nghe của chủ dự án

**Mục đích:** Lưu kết quả nghe thực tế của chủ dự án cho 24 audio TTS gốc và kết luận phép so sánh, tách biệt với quyết định chọn giọng/model.

**Ngày nhận nhận xét:** 2026-11-03, Asia/Ho_Chi_Minh. **Trạng thái D70: EVALUATION COMPLETE WITH QUALITY LIMITATIONS.** Benchmark máy đã có; chủ dự án xác nhận nghe hết, nghe lại nhiều lần bằng loa và không thấy lỗi âm thanh ở cả hai model. Phần chờ người nghe đã được giải quyết. Các lỗi chất lượng dưới đây vẫn là kết quả chưa đạt; không đánh dấu mọi model/giọng PASS.

## Nguồn và phạm vi

[Bằng chứng 24 mục](evidence/d70-owner-listening-20261103.json) giữ nguyên nội dung nhận xét, mã output, hash WAV/waveform và xác nhận nghe. Reviewer là chủ dự án, assistant chỉ nhập và tổng hợp; đây không phải assistant nghe, đánh giá mù hoặc nghiên cứu MOS nhiều người. Ngày nghe cụ thể và mức chắc chắn không được cung cấp riêng; để trống, không suy từ số lần nghe. Thiết bị là loa; không suy ra kết quả trên tai nghe hoặc mọi thiết bị.

Có 18 nhận xét riêng và một nhận xét chung được chủ dự án áp dụng rõ cho Piper VI 01–06. Sáu dòng Piper VI kế thừa cùng nhận xét nhóm, không phải sáu nhận xét độc lập. “Không lỗi âm thanh” được ghi theo xác nhận bổ sung cho toàn bộ 24 mục; không có nghĩa phát âm/ngữ điệu đúng. Những khía cạnh không được chấm riêng giữ `null`; Qwen EN 02–05 có ghi rõ câu ngắn nên chưa đánh giá được ngắt hơi. Không tạo điểm hoặc ngưỡng đạt sau khi thấy kết quả.

## Tổng hợp theo nhóm

| Nhóm | Kết quả nghe của chủ dự án | Kết luận trong corpus này |
|---|---|---|
| Qwen3-TTS EN, 6 mục | Đọc đúng 6/6, giọng được nhận xét tự nhiên; 01 kéo dài “Hello”, hơi chậm; 04 ngữ điệu chưa hợp ngữ cảnh | Có triển vọng cho EN, còn hạn chế; chưa được chọn/triển khai |
| Qwen3-TTS VI-Auto, 6 mục | 5 mục có lỗi phát âm/dấu/ngữ điệu; riêng 03 được người nghe nhận xét thành tiếng Trung | Không đáp ứng đọc VI ở cả 6 mục đã nghe; không suy ra hỗ trợ VI chính thức |
| Piper EN, 6 mục | Đọc đúng 5/6; 02 sai “notebook”; 01 giọng ngang; 05 hạ tông bất thường ở “before you leave” | Còn lỗi phát âm/ngữ điệu; không có kết luận vượt Qwen hoặc đủ chất lượng sản phẩm |
| Piper VI, 6 mục | Theo nhận xét nhóm: đọc VI đúng, nhấn nhá hay, nhưng chủ dự án không thích tông giọng và thấy không tự nhiên | Không đáp ứng mong muốn về chất giọng của chủ dự án ở voice đã thử |

Không thấy lỗi âm thanh ở 24/24 theo người nghe. “Thành tiếng Trung” là quan sát của chủ dự án cho Qwen VI 03, chưa có phép đo nhận diện ngôn ngữ độc lập. Không quy đổi các nhận xét thành MOS, tỷ lệ chất lượng tổng quát hoặc bảng xếp hạng mọi giọng. Sáu câu mỗi ngôn ngữ, voice khác nhau và chế độ Qwen VI-Auto là các giới hạn của phép so sánh.

## Đối chiếu từng output

| Output | Phát âm và ngôn ngữ | Nhịp/ngữ điệu, tự nhiên và hạn chế được nêu |
|---|---|---|
| qwen3-tts-0_6b-en-01 | Chuẩn | Ngắt hơi ổn nhưng kéo dài “Hello”; tự nhiên, hơi chậm |
| qwen3-tts-0_6b-en-02 | Chuẩn | Tự nhiên; câu ngắn nên chưa đánh giá được ngắt hơi |
| qwen3-tts-0_6b-en-03 | Chuẩn | Tự nhiên; câu ngắn nên chưa đánh giá được ngắt hơi |
| qwen3-tts-0_6b-en-04 | Chuẩn | Tự nhiên nhưng lên xuống giọng chưa hợp ngữ cảnh; chưa đánh giá được ngắt hơi |
| qwen3-tts-0_6b-en-05 | Chuẩn | Tự nhiên; câu ngắn nên chưa đánh giá được ngắt hơi |
| qwen3-tts-0_6b-en-06 | Chuẩn | Ngắt hơi chuẩn, tự nhiên |
| qwen3-tts-0_6b-vi-01-auto | Sai nhiều; “xin chào” thành “xin zhao” | Dấu câu đọc không đúng; không có nhận xét tự nhiên riêng |
| qwen3-tts-0_6b-vi-02-auto | Sai phát âm và nhiều dấu | Không có nhận xét nhịp/tự nhiên riêng |
| qwen3-tts-0_6b-vi-03-auto | Người nghe nhận xét thành tiếng Trung | Không đáp ứng câu VI; không có nhận xét tự nhiên riêng |
| qwen3-tts-0_6b-vi-04-auto | Tốt hơn nhưng vẫn sai dấu, “cuộc họp” thành “cuông hop” | Không có nhận xét nhịp/tự nhiên riêng |
| qwen3-tts-0_6b-vi-05-auto | Sai phát âm | Sai ngữ điệu; không có nhận xét tự nhiên riêng |
| qwen3-tts-0_6b-vi-06-auto | Sai phát âm và dấu | Sai ngữ điệu; không có nhận xét tự nhiên riêng |
| piper-en-en-01 | Chuẩn | Ngắt nhịp tốt nhưng ngang, thiếu intonation |
| piper-en-en-02 | Sai “notebook” | Không có nhận xét nhịp/tự nhiên riêng |
| piper-en-en-03 | Chuẩn | Ngắt nhịp tốt, tự nhiên |
| piper-en-en-04 | Chuẩn | Ngắt nhịp tốt, tự nhiên |
| piper-en-en-05 | Chuẩn | Ngắt nhịp tốt; hạ tông bất thường ở “before you leave”, đoạn đó không tự nhiên |
| piper-en-en-06 | Chuẩn | Ngắt nhịp tốt, tự nhiên |
| piper-vi-vi-01 | Chuẩn theo nhận xét nhóm | Nhấn nhá hay nhưng không thích tông giọng, không tự nhiên |
| piper-vi-vi-02 | Chuẩn theo nhận xét nhóm | Cùng nhận xét nhóm Piper VI |
| piper-vi-vi-03 | Chuẩn theo nhận xét nhóm | Cùng nhận xét nhóm Piper VI |
| piper-vi-vi-04 | Chuẩn theo nhận xét nhóm | Cùng nhận xét nhóm Piper VI |
| piper-vi-vi-05 | Chuẩn theo nhận xét nhóm | Cùng nhận xét nhóm Piper VI |
| piper-vi-vi-06 | Chuẩn theo nhận xét nhóm | Cùng nhận xét nhóm Piper VI |

## Acceptance Criteria và bước tiếp theo

Theo [ADR-096](ADR/096-offline-registry-tts-comparison.md), phép đánh giá cần đầu ra thật, số đo, nghe thực tế và báo cáo giới hạn; không bắt buộc mọi ứng viên phải tốt. Nay có nhận xét nghe đủ 24 mục, xác nhận nghe hết và nguồn reviewer. Vì vậy D70 kết thúc **phép so sánh offline với kết quả chất lượng còn hạn chế**, không còn chờ khả năng nghe. Giữ sáu từ chối explicit-Vietnamese, tất cả lỗi evaluator và mọi kết quả máy gốc. Phiếu pending và nhãn trống cũ là snapshot lịch sử, không ghi đè.

**D74 vẫn OPEN:** chưa có giọng/model được phê duyệt triển khai, đặc biệt chưa có voice VI được chủ dự án chấp nhận. Chuỗi giấy phép engine/voice/dataset, quyền triển khai, ASR/VAD/no-speech, thiết bị microphone thật và nghiệm thu sản phẩm vẫn là gate riêng. D71–D73 đã kiểm chứng phạm vi local; không cần bắt đầu lại từ D71. D60 được để chờ theo yêu cầu mới nhất, không thử Brave trong tác vụ này.

**VOICE-TTS-DECISION-001 đã hoàn tất phần chuẩn bị hồ sơ ngày 2026-11-03:** [bảng quyết định D74](D74_VOICE_DECISION_BRIEF.md), trạng thái PROPOSAL READY / OWNER DECISION PENDING. P1 trước kích hoạt voice: tổng hợp chính các ứng viên đã thống nhất, chất lượng vừa nghe, số đo tài nguyên/độ trễ và license đã có thành đề xuất để chủ dự án duyệt. Dependency: bằng chứng D70/D72 và rights chain; effort một milestone quyết định; rủi ro: suy rộng corpus nhỏ, chọn giọng không được thích hoặc thiếu quyền. Nếu đề xuất đổi model/voice hoặc điều chỉnh tham số, phải đánh giá riêng benchmark, hiệu năng/tài nguyên, migration, rollback và được chủ dự án phê duyệt trước khi tải/chạy/đổi lựa chọn. Không tự xếp lịch thử thêm model.

Đợt cập nhật này chỉ sửa tài liệu và thêm evidence. Kiểm tra đối chiếu đủ 24 ID/hash trong player nguyên byte, 176 input D70 và pending gốc giữ nguyên, 750 file ứng dụng/config/test không đổi. Full 5889 PASS là bằng chứng đã có cho đúng snapshot, không phải lượt chạy mới. Không truy cập Vault/database, chạy model/provider hay khởi động lại dịch vụ.
