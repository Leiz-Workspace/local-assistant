# D74 — Kiểm tra microphone thật trước nghiệm thu voice

**Mục đích:** Hướng dẫn chủ dự án kiểm tra phần recorder local đã có bằng thiết bị thật, tách biệt với TTS listening và ASR/CORE/TTS sản phẩm.

**Trạng thái 2026-11-03:** READY / NOT EXECUTED. Chủ dự án đã nghe TTS D70 bằng loa; chưa có kết quả microphone thật. Agent không tự mở microphone, cấp quyền hoặc điền PASS. [Phạm vi recorder D71](D71_EXPLICIT_RECORDING.md) vẫn giữ nguyên.

## Mở recorder khi muốn kiểm tra

Trên máy chạy repository, từ `ai/`, chạy surface local đã có:

```sh
uv run --no-sync uvicorn apps.voice.main:app --host 127.0.0.1 --port 8091 --no-proxy-headers
```

Mở `http://127.0.0.1:8091` trong Chrome/Firefox trên **máy có microphone của bạn**. Nếu server ở máy khác, dùng SSH local port forwarding đã cấu hình; microphone là thiết bị của trình duyệt, không phải server. Nếu port đã được sử dụng, kiểm tra process trước; không dừng dịch vụ khác để lấy port.

Recorder chỉ tạo bản nghe trong bộ nhớ trình duyệt, không có upload/ASR/TTS. Chỉ bấm “Bắt đầu ghi” và cấp quyền khi bạn muốn thu âm. Có thể dùng câu trung tính, không cần gửi nội dung hoặc file ghi âm vào chat.

## Các thao tác và kết quả cần quan sát

| Kiểm tra | Thao tác | Kết quả cần quan sát |
|---|---|---|
| Không tự thu | Mở hoặc reload trang | Không có microphone đang capture trước khi bấm bắt đầu |
| Ghi và dừng | Bấm bắt đầu, cấp quyền, nói một câu, bấm “Dừng và nghe lại” | Capture dừng; bản nghe có đúng tiếng nói của bạn, không feedback lặp liên tục |
| Hủy | Bắt đầu lượt mới rồi bấm “Hủy / xóa audio” | Capture dừng, preview bị bỏ; không tự bắt đầu lại |
| Escape | Trong lượt ghi mới, nhấn Escape | Capture dừng và audio bị hủy |
| Chuyển tab | Trong lượt ghi mới, chuyển sang tab khác | Capture dừng; trở lại không tự ghi tiếp |
| Từ chối quyền | Khi kiểm tra trường hợp này, từ chối quyền microphone | Thông báo lỗi hữu hạn; không capture hoặc tự retry |
| Giới hạn thời gian | Bắt đầu lượt mới và để quá 30 giây | Capture kết thúc trong giới hạn; không tự bắt đầu lượt kế |

Biểu tượng “đã cấp quyền” có thể vẫn còn khi capture đã dừng; phân biệt với chỉ báo đang sử dụng microphone. Nếu browser/OS không cho kiểm tra một tình huống, ghi chưa kiểm tra và lý do; không đánh dấu PASS. Có thể chia nhiều buổi.

## Gửi kết quả

Chỉ cần gửi trong chat: browser/version, hệ điều hành, loại microphone, ngày kiểm tra, từng thao tác đã làm và kết quả/lỗi. Không cần key, JSON hoặc upload audio. Chưa làm mục nào thì ghi rõ mục đó.

Khi kiểm tra xong, dừng đúng process recorder bạn vừa mở bằng Ctrl+C. Hoàn tất recorder/device không tự chốt ASR/VAD/TTS, giấy phép, endpoint sản phẩm hoặc release. [Bảng quyết định D74](D74_VOICE_DECISION_BRIEF.md) giữ riêng các điều kiện đó.
