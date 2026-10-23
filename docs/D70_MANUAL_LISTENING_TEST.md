# D70 — Hướng dẫn nghe kiểm thử sau

**Mục đích:** Giúp chủ dự án hoàn tất phần nghe 24 audio TTS đã tạo, giữ nguyên kết quả benchmark và mọi file gốc.

**Trạng thái:** Chủ dự án hoãn kiểm thử nghe theo [ADR-111](ADR/111-owner-deferred-tts-listening-and-explicit-recording.md). Benchmark máy đã có kết quả; chất lượng nghe **chưa được chấp nhận**. D71 được phép tiếp tục. Không cần tải model, chạy inference, cấp key hoặc chỉnh JSON để nghe.

## Mở bộ audio

1. Trên máy có trình duyệt và tai nghe/loa, mở file `ai/data/backups/d89-native-tts-listening/index.html`. Nếu đang làm qua SSH, chép riêng file HTML này về máy của bạn: đủ24WAV gốc nguyên byte đã nhúng trong trang, không cần server hay mạng.
2. Trang có24mục với mã output, câu cần đọc và nút Play. Mở âm lượng vừa phải. Bấm Play và nghe hết từng mục; có thể nghe lại để kiểm tra, ghi rõ khi còn phân vân.
3. Có12mục tiếng Anh và12mục văn bản tiếng Việt. Qwen VI dùng **Auto ngoài danh sách hỗ trợ được công bố**; sáu lượt gọi explicit-Vietnamese đã bị từ chối và được giữ trong báo cáo, không nằm trong24waveform này.
4. Trang mới dùng WAV gốc, không nén lại, đổi sample rate hoặc tăng gain. Trang Opus cũ vẫn được giữ nguyên để đối chiếu; không dùng khác biệt do bản nén/gain để suy chất lượng model.

Trang nghe WAV gốc: [mở file offline](../data/backups/d89-native-tts-listening/index.html). [Bản Opus lịch sử](../data/backups/d70-tts-listening-review/index.html) giữ nguyên.

Đã kiểm tra độc lập24hashWAV/waveform và browser đọc được metadata/duration của đủ24file, không phát thử hoặc nghe. Việc browser decode được không phải đánh giá chất lượng;0/24nhận xét nghe vẫn chưa điền. [Báo cáo số đo](D70_OFFLINE_TTS_COMPARISON.md). [Nhãn gốc đang trống](../data/backups/d70-tts-listening-review/review.pending.json) phải được giữ nguyên; ghi kết quả vào bản mới hoặc gửi trong chat để nhập sau.

## Ghi nhận xét

Bạn có thể điền trực tiếp [phiếu24mục đã tạo sẵn](D70_MANUAL_LISTENING_RESULTS.pending.md), hoặc gửi nhận xét trong chat theo mẫu dưới đây. Phiếu đang để CHƯA TEST, không phải nhãn đã đánh giá.

Mỗi mục ghi mã output và bốn ý: **phát âm/đọc đúng câu; nhịp, ngắt và ngữ điệu; lỗi âm thanh; cảm nhận tự nhiên và mức chắc chắn**. Dùng “ổn”, “có vấn đề” hoặc “chưa chắc”, kèm mô tả cụ thể. Không bắt buộc cho điểm MOS. Không dùng kết quả ASR thay cho nghe.

Ví dụ về **định dạng**, không phải kết quả đã nghe:

```text
Người nghe: <tên hoặc mã của bạn>; ngày: <ngày nghe>; thiết bị: <tai nghe/loa>
<mã output>: đã nghe hết; phát âm: <...>; nhịp/ngắt: <...>;
lỗi âm thanh: <...>; tự nhiên: <...>; chắc chắn: <cao/vừa/thấp>.
```

Nếu không hiểu đủ ngôn ngữ, ghi rõ và để phần đó chưa kết luận. Nếu file không phát được, ghi lỗi thay vì đánh chất lượng kém. Có thể chia nhiều buổi; không cần làm đủ24mục trong một lần.

## Điều kiện hoàn tất

- Đủ24mã output và xác nhận thực sự nghe hết; giữ nhận xét không thuận lợi và bất định.
- Có nhận xét riêng cho phát âm, nhịp/ngắt, artifacts và độ tự nhiên của mỗi output; chưa chắc thì yêu cầu đối chiếu thay vì điền kết quả tưởng tượng.
- Đối chiếu mã/hash với packet gốc, lưu danh tính/loại reviewer và ngày nghe trong một kết quả mới; không ghi đè packet pending hoặc sửa audio.
- Tổng hợp so sánh với giới hạn corpus nhỏ, voice khác nhau và Qwen VI-Auto; không suy ra hỗ trợ VI chính thức hoặc tự chọn model.

Đánh giá nghe hoàn tất không tự phê duyệt triển khai. Quyền sử dụng engine/voice, lựa chọn model, ASR/VAD và các gate sản phẩm vẫn cần đạt riêng.
