# D70 — Phần đã hoàn tất và tiêu chí còn thiếu

> **Trạng thái hiện tại — 2026-10-24:** D70 đã hoàn tất đo máy; nghe thực tế **0/24, chủ dự án để test sau**. [ADR-111](ADR/111-owner-deferred-tts-listening-and-explicit-recording.md) đã cho phép tiếp tục; D71–D73 đã kiểm chứng phạm vi local, D74 còn nghiệm thu sản phẩm. Các dòng “D71 NOT STARTED” ở lịch sử bên dưới mô tả thời điểm trước quyết định này. Các guard research vẫn đóng; xem phê duyệt và lượt chạy theo đúng ngày của từng thí nghiệm. Không mở lại evaluator campaign hoặc sửa điểm/nhãn cũ. Xem [trạng thái dự án hiện tại](RELEASE_CANDIDATE_STATUS.md), [hướng dẫn nghe](D70_MANUAL_LISTENING_TEST.md).

**Mục đích:** Đối chiếu trực tiếp AC gốc của D70 với bằng chứng hiện có, tránh nhầm tiến độ nghiên cứu evaluator hoặc số lượng test với hoàn thành so sánh TTS.

**Cập nhật:** 2026-10-23, Asia/Saigon. **D70: benchmark máy hoàn tất, kiểm thử nghe HOÃN THEO YÊU CẦU CHỦ DỰ ÁN; D71 được phép tiếp tục.** [ADR-111](ADR/111-owner-deferred-tts-listening-and-explicit-recording.md) ghi quyết định mới, thay thế ràng buộc thứ tự cũ của ADR-097. [Hướng dẫn nghe sau](D70_MANUAL_LISTENING_TEST.md) và [phiếu24mục chưa điền](D70_MANUAL_LISTENING_RESULTS.pending.md). Nguồn AC vẫn là [ADR-096](ADR/096-offline-registry-tts-comparison.md); không có naturalness PASS.

## Đối chiếu Acceptance Criteria

| Phần việc theo AC gốc | Bằng chứng hiện có | Trạng thái |
|---|---|---|
| Đóng băng đúng Qwen3-TTS-0.6B, Piper EN/VI, codec, runtime, corpus, voice và provenance/license | Đã ghi revision/hash/runtime/giới hạn; chuỗi giấy phép Piper VI còn hạn chế được công khai, chưa phê duyệt triển khai | Đã đánh giá trong phạm vi offline; không đồng nghĩa đủ quyền triển khai |
| Kiểm tra VI/EN và giữ mọi kết quả đầu tiên |30lượt đầu,24audio,6từ chối explicit-VI của Qwen; VI-Auto được ghi riêng, không gọi thành hỗ trợ VI chính thức | Đã đo và báo cáo, gồm các kết quả không hỗ trợ |
| Đo latency, duration/RTF, tài nguyên và diagnostics | Số đo CPU/RAM, source-bound waveforms,24ASR roundtrips đã lưu | Đã có bằng chứng; ASR không thay thế nghe |
| Nghe audio thực tế và lưu nhận xét theo từng output về phát âm, nhịp/ngắt, artifacts, độ tự nhiên và bất định |24output còn `has_actually_listened=false`, `naturalness_judgement=null` | **CHƯA ĐẠT: 0/24 được đánh giá nghe thực tế** |
| Báo cáo so sánh, tương thích, migration/rollback và giới hạn | Báo cáo benchmark máy và các giới hạn đã có; chưa thể kết luận so sánh độ tự nhiên | Chưa đủ để đóng toàn bộ D70 |
| Giữ source/model/data/runtime/CORE và bằng chứng cũ | Audit trước đó và kiểm tra hiện tại xác nhận661source không đổi; kết quả, dữ liệu và các guard giữ nguyên | Đã xác minh trong phạm vi đã ghi; không phải kết quả chất lượng giọng |

[Báo cáo TTS gốc](D70_OFFLINE_TTS_COMPARISON.md), [packet nghe đầy đủ](../data/backups/d70-tts-listening-review/index.html), [24nhận xét đang trống](../data/backups/d70-tts-listening-review/review.pending.json).

## Vì sao các lượt tiếp tục chưa đóng được D70

Các lượt sau benchmark đã chuyển trọng tâm sang tìm và chẩn đoán một AI có thể nghe thay công cụ hiện tại. Qwen reviewer không đạt giao thức đã duyệt; dịch vụ công khai trả lỗi; Voxtral đạt4/12control; đối chiếu eager/SDPA không sửa bốn đáp án presence cũ. Những kết quả này giải thích vì sao chưa thể dùng các reviewer đó, nhưng không tạo ra bất kỳ nhận xét nghe hợp lệ nào cho24audio TTS. Việc có470software tests PASS không hoàn tất tiêu chí này.

Đã kiểm tra lại trực tiếp một audio smoke có sẵn qua helper audio của phiên hiện tại. Công cụ vẫn trả **`audio content omitted because you do not support audio input`**. Không suy đoán nội dung hoặc điền nhãn từ tên file, transcript, biểu đồ hay ASR. [Kết quả kiểm tra mới](evidence/d70-native-audio-acceptance-recheck.json).

## Ranh giới hoàn tất và công việc tiếp theo

AC gốc yêu cầu **thực sự nghe/kiểm tra audio và lưu nhận xét theo từng output**. AC không bắt buộc xây evaluator local, dùng Voxtral, đạt12/12trong mọi phương án, thêm ADR nghiên cứu hoặc có independent human MOS. Các gate12/12đã duyệt áp dụng cho những campaign AI cụ thể và được giữ nguyên; chúng không được biến thành mục tiêu thay thế cho D70. Same-agent listening được phép nếu công cụ thực sự nhận audio và provenance được ghi trung thực.

Task còn lại là **AUDIO-TTS-NATURALNESS-001: chủ dự án nghe và đánh giá đủ24audio đã giữ khi có thời gian**. Tiêu chí vẫn chưa đạt; theo quyết định mới ADR-111, việc này được hoãn và D71 có thể bắt đầu. Giữ gate trước chấp nhận voice/chọn model/release. Không tự thêm lượt nghiên cứu model/backend để thay cho kết quả nghe. Các kết quả nghiên cứu cũ và mọi quyền chạy đã dùng hết vẫn được giữ nguyên.

Việc chọn/deploy model và chấp thuận đầy đủ quyền sử dụng voice vẫn là các quyết định riêng, không tự phát sinh từ hoàn thành benchmark offline. Không thay model, code, Docker, Vault, database hoặc dữ liệu trong lần đối chiếu AC này.

## Kiểm tra lại đường nghe công khai — 2026-10-23

[Kiểm tra metadata mới](evidence/d70-auditory-route-availability-recheck.json) ghi nhận demo tác giả SpeechJudge vẫn `RUNTIME_ERROR`; demo cộng đồng vẫn `RUNNING`, đúng revision/giao diện đã gặp lỗi `GPU task aborted`. Đây chỉ là kiểm tra bốn metadata GET, **không chứng minh inference đã phục hồi**. Không gửi audio, gọi inference hoặc mở lại campaign đã dùng hết. Inventory công cụ hiện tại không có connector nhận audio; kết quả từ chối native audio gần nhất vẫn được giữ riêng, không gọi lại.

Xác minh lại661source,917file được bảo vệ,176input gốc và hash packet nhãn: không đổi, vẫn0/24nhận xét nghe. Không chạy lại software tests vì không sửa source;470PASS là kết quả lịch sử. D70 đang bị chặn bởi khả năng nghe thực tế, không còn phần code có thể viết để thay thế bằng chứng này. Không thêm thử nghiệm evaluator, thay model/giới hạn hoặc chuyển D71 theo một kết quả metadata.
