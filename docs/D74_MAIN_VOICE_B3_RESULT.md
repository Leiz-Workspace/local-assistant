# D74 — Kết quả B3: voice qua API chính

**Ngày:** 2026-11-05 (lượt đầu) và 2026-11-06 (lượt thay thế theo ADR176). **Phạm vi:** [ADR174](ADR/174-proposed-opt-in-authenticated-voice-integration.md), [ADR175](ADR/175-optional-main-voice-composition-and-entrypoint-binding.md), [ADR176](ADR/176-bounded-foreign-gpu-tolerance-and-b3-preflight.md). **Receipt công khai:** [evidence/d74-main-voice-b3-adr176-result.json](evidence/d74-main-voice-b3-adr176-result.json).

**Kết luận:** Cả hai lượt đều **NOT_PASS** theo tiêu chí đã chốt trước khi chạy. Ở lượt thay thế, **cả 6 dòng đều đạt tiêu chí chấp nhận**, nhưng bước kiểm tra sau panel fail vì runner đòi web process thoát với mã 0. Không retry, không đổi nhãn. Đo vật lý (bấm Gửi đến lúc loa phát) và quyết định sản phẩm/model/default vẫn mở.

## Lượt đầu — 2026-11-05

- `NOT_PASS`, `main_voice_prepare_fault`: 6/6 dòng chưa chạy, 0 retry. CORE do runner khởi động đã thoát với mã 0 và được reap.
- Log ứng dụng cho thấy worker VAD được nạp lúc 21:17:18.384, rồi `dependency_failed` lúc 21:17:18.400, trước khi có câu nào được xử lý. Log không ghi guard nào đã kích hoạt.
- Nguyên nhân có bằng chứng: guard NVML của ADR175 từ chối mọi tiến trình GPU lạ. Sau lỗi, NVML ghi nhận `gnome-remote-desktop` dùng khoảng 223 MiB; ngày 2026-11-06 trên cùng máy còn thấy thêm `nautilus` và `rustdesk`. Chủ dự án duyệt ADR176 để nới guard có giới hạn và chạy lại đúng một panel.

## Lượt thay thế — 2026-11-06 (ADR176)

**Cổng phần mềm (không gọi model):** 1.070 test Python liên quan và 27 test JS pass trên commit `eeabbe8`, đã ghim hash của 306 file nguồn.

**Kiểm tra trước, sau khi CORE sẵn sàng và trước khi nạp model voice:** CORE dùng 1.031.987.200 byte RSS (khoảng 0,96 GiB). 2 tiến trình GPU lạ dùng tổng 272.539.648 byte (khoảng 260 MiB). Cả hai đều dưới ngưỡng dừng, nên panel được chạy. Kết quả này cho thấy giới hạn RAM 8 GiB không phải nguyên nhân của lượt đầu: con số 7,7 GiB ghi trong receipt CORE là đỉnh trong lúc nạp model.

**Chuẩn bị nhóm model:** 56,78 giây, đo riêng và không tính vào 4 giây.

| Dòng | Kết quả | Server (s) | Client (s) | ASR / LLM / TTS (s) |
|---|---|---:|---:|---|
| heldout-vi_vn-0036 | EXACT_COMPLETE_PCM | 2,247 | 2,250 | 0,346 / 0,511 / 1,380 |
| heldout-vi_vn-0024 | EXACT_COMPLETE_PCM | 2,736 | 2,739 | 0,652 / 0,361 / 1,713 |
| heldout-vi_vn-0078 | EXACT_COMPLETE_PCM | 3,241 | 3,244 | 0,779 / 0,458 / 1,994 |
| heldout-vi_vn-0040 | EXACT_COMPLETE_PCM | 3,178 | 3,181 | 1,055 / 0,360 / 1,752 |
| negative-1 | CORRECT_NO_SPEECH | — | 0,017 | chặn trước ASR/CORE/TTS |
| negative-3 | CORRECT_NO_SPEECH | — | 0,016 | chặn trước ASR/CORE/TTS |

`EXACT_COMPLETE_PCM` nghĩa là transcript, câu trả lời và audio trùng khớp với lượt đã qualified trên trang thử, và server trả đủ phản hồi trong ≤4 giây. Đây là thời gian xử lý và mạng loopback, **không** phải thời gian đến khi loa phát.

**Ngân sách và dọn dẹp:**
- Số lượt gọi đúng VAD 6 / ASR 4 / CORE 4 / TTS 4, readiness 1, 3 worker đã join.
- CORE do runner khởi động thoát với mã 0, đã được reap, không có lỗi guard. Đỉnh VRAM 8.792 MiB, VRAM trống thấp nhất 2.486 MiB.
- Sau lượt chạy không còn tiến trình native nào, và nguồn không đổi.

**Vì sao vẫn NOT_PASS:**
- Runner đặt điều kiện web process phải thoát với mã 0.
- uvicorn 0.54.0 (bản đã khóa) bắt SIGTERM, tắt êm, rồi phát lại tín hiệu đó (`Server.capture_signals` gọi `signal.raise_signal`), nên mã thoát là −15. Log ứng dụng ghi đủ chuỗi tắt: dịch vụ voice đóng, GPU admission được gỡ, các entry point được khôi phục, manifest đóng.
- Điều kiện này nằm trước bước kiểm tra "CORE vẫn sống sau khi app tắt", nên runner **chưa đánh giá** bước đó.

## Còn mở

- Một lượt B3 mới với runner sửa để chấp nhận đúng mã −SIGTERM sau khi tắt êm cần chủ dự án duyệt riêng. ADR176 chỉ cho phép một panel.
- Đo vật lý theo [checklist](D74_PHYSICAL_FIRST_AUDIBLE_CHECKLIST.md); câu ngắn, nói nhỏ và tiếng ồn phòng; quyết định bật dùng, model, giọng và default; D90.
