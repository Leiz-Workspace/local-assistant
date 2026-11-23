# D74 — Mở trang thử giọng nói trên PC

**Mục đích:** Hướng dẫn chủ dự án dùng trang hỏi–đáp thực và phân biệt số đo trình duyệt với tiếng thực sự phát từ loa.

## Mở và dùng ngay

Trên Brave của **chính máy chạy Codex**, mở [http://127.0.0.1:8092](http://127.0.0.1:8092). Đây là trang thử riêng, không phải recorder cũ ở8091. Không cần tài khoản, key hoặc cấu hình mạng.

1. Bấm **Chuẩn bị**, đợi thông báo **Sẵn sàng**. Lượt kiểm tra đã đo mất43,843giây cho bước xác minh/nạp model; khoảng một phút là bình thường trong lượt này. Mốc4giây bắt đầu từ Gửi, không tính bước chuẩn bị này.
2. Bấm **Ghi câu hỏi**, tự cấp quyền microphone khi Brave hỏi. Nói một câu tiếng Việt từ1đến20giây, ví dụ “Xin chào, bạn có thể giúp tôi việc gì?”. Không tự thu khi mở/reload trang.
3. Bấm **Dừng và nghe lại**. Microphone được tắt, audio chưa gửi; có thể nghe lại câu hỏi.
4. Bấm **Gửi câu hỏi**. Trang hiển thị câu nhận dạng và câu trả lời, đồng thời phát audio. Nếu trình duyệt chặn phát, dùng nút nghe lại câu trả lời; không tính trường hợp này thành tự động đạt4giây.
5. **Hủy / xóa**, Escape hoặc chuyển tab sẽ tắt thu, hủy lượt đang chạy và bỏ audio/kết quả trên trang. Nếu đang xử lý thì runtime bị thu hồi; đợi trạng thái cập nhật rồi bấm Chuẩn bị lại, không tự gửi lại câu cũ.

## Kiểm chứng mốc4giây

Đo khoảng từ **bấm Gửi** đến **tiếng đầu tiên của lời trả lời nghe từ loa**. Có thể quay màn hình kèm thu tiếng loa trong cùng bản ghi để đối chiếu hai mốc. Thời gian bạn đang nói trước khi Gửi và thời gian phát hết câu trả lời không nằm trong4giây này. Không tính tiếng báo, khoảng lặng hoặc lấy trung bình thay maximum.

Hai số trên trang — “Nhận audio” và “Chuẩn bị phát” — là marker phần mềm, chưa chứng minh loa thực sự phát tiếng. Hãy báo câu đã thử, số hiển thị, có nghe rõ/đủ lời không và độ trễ nghe thực tế nếu có bản đo. Không cần gửi file ghi âm hoặc key vào chat. Agent chưa mở microphone thật hoặc chấm thay bạn phần nghe trên thiết bị.

## Phiên thử và dữ liệu

Tiếng Việt/Trúc Ly là đúng lane nghiên cứu đã đo, chưa phải lựa chọn default sản phẩm. Bản ghi/kết quả trên trang tự xóa sau5phút, khi Hủy hoặc khi chuyển tab. Server không lưu raw audio/transcript/answer vào log/database/disk; các file trung gian ởRAM được xóa sau lượt đã thu hồi. Buffer nội bộ của SDK/model có thể tồn tại trongRAM/VRAM tới khi nhóm model dừng; không tuyên bố secure memory erasure. Nhóm được giới hạn8phút và cần Chuẩn bị lại sau khi hết hạn.

Mỗi lần chạy web surface có tối đa24lượt gửi và3lần Chuẩn bị; bộ kiểm tra tự động đã dùng6lượt/1lần, còn18lượt/2lần tại thời điểm bàn giao. Trạng thái hiển thị có thể đổi khi bạn dùng. Reload không reset quota. Web service thử hiện có thời hạn4giờ; chỉ bindlocalhost, không chia sẻ link này cho máy khác.

## Vận hành khi cần

Service do lượt này tạo: `local-assistant-voice-trial.service`. Dừng đúng service này bằng `systemctl --user stop local-assistant-voice-trial.service`; không dừng service khác. Muốn chạy lại bằng terminal từ `ai/` sau khi đã dừng service và kiểm tra port trống:

```sh
TMPDIR=/dev/shm uv run --no-sync uvicorn apps.voice_trial.main:app --host 127.0.0.1 --port 8092 --no-proxy-headers --no-access-log
```

Giữ `TMPDIR=/dev/shm` để conversion dùng file tạm RAM. Nguồn chưa có receipt kiểm thử/hash phù hợp thì Prepare sẽ từ chối. [Kết quả kỹ thuật và giới hạn](D74_VOICE_BROWSER_TRIAL_RESULT.md). Physical4seconds, quyền dùng/model/default và D74sản phẩm/D90release vẫn OPEN.
