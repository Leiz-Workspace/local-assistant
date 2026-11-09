# D74 — Kết quả B3: voice qua API chính

**Ngày:** 2026-11-05 (lượt đầu), 2026-11-06 (lượt thay thế theo ADR176) và 2026-11-07 (lượt theo ADR178). **Phạm vi:** [ADR174](ADR/174-proposed-opt-in-authenticated-voice-integration.md), [ADR175](ADR/175-optional-main-voice-composition-and-entrypoint-binding.md), [ADR176](ADR/176-bounded-foreign-gpu-tolerance-and-b3-preflight.md), [ADR178](ADR/178-graceful-sigterm-exit-in-b3-acceptance.md). **Receipt công khai:** [evidence/d74-main-voice-b3-adr178-result.json](evidence/d74-main-voice-b3-adr178-result.json) (lượt ADR178) và [evidence/d74-main-voice-b3-adr176-result.json](evidence/d74-main-voice-b3-adr176-result.json) (lượt ADR176).

**Kết luận:** Lượt thứ ba, chạy theo ADR178 ngày 2026-11-07, **PASS** theo tiêu chí đã chốt trước khi chạy: 4/4 câu nói `EXACT_COMPLETE_PCM` với server 2,608–3,747 s, 2/2 negative bị chặn đúng, ngân sách gọi và dọn dẹp đúng, CORE mượn vẫn sống sau khi app tắt, đúng một panel và không retry. Hai lượt trước giữ nguyên **NOT_PASS** như đã ghi: lượt đầu fail ở bước chuẩn bị; ở lượt thay thế, cả 6 dòng đều đạt tiêu chí chấp nhận, nhưng bước kiểm tra sau panel fail vì runner khi đó đòi web process thoát với mã 0. Không đổi nhãn lượt nào. B3 PASS chỉ áp dụng cho đường `/voice` mặc định tắt, mục đích `integration_evaluation`. Đo vật lý (bấm Gửi đến lúc loa phát), câu ngắn, nói nhỏ, tiếng ồn phòng và quyết định sản phẩm/model/giọng/default vẫn mở. Bằng chứng PASS gắn với commit `73cecdf`, trước bản sửa lỗi decoder P2 (PR #33) vào `develop`; chủ dự án giữ PASS này kèm ghi chú *(owner 2026-11-07, operator record)*, xem mục [Sau PR #33](#sau-pr-33-2026-11-07).

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
- Điều kiện này nằm trước bước kiểm tra "CORE vẫn sống sau khi app tắt", nên runner **chưa đánh giá** bước đó trong lượt này.

## Lượt theo ADR178 — 2026-11-07

**Quyết định và thay đổi runner:** Ngày 2026-11-06, chủ dự án trả lời "Duyệt B3 mới": sửa runner để chỉ chấp nhận mã thoát −SIGTERM của uvicorn khi audit chứng minh ứng dụng đã tắt êm đầy đủ, rồi chạy đúng một panel mới. [ADR178](ADR/178-graceful-sigterm-exit-in-b3-acceptance.md) (ACCEPTED 2026-11-07) được merge vào develop qua PR #28 (merge commit `73cecdf`, commit nhánh `6e78f8d`). Về mã, ADR178 chỉ đổi runner B3 (`benchmarks/scripts/main_voice_integration.py`) và test của nó:
- `graceful_web_exit` chỉ chấp nhận mã thoát 0 hoặc −15 khi audit có đủ 5 sự kiện tắt của lifespan voice, đúng thứ tự, mỗi sự kiện đúng một lần, và không có dòng quarantine, Traceback, ERROR hay CRITICAL.
- Mỗi worker phải join sạch: mã thoát 0, không bị buộc dừng (`forced=False`), vai trò khác nhau.
- Release phải trả HTTP 200 và trạng thái sau release phải là `idle`, không lỗi.
- Phần phán quyết sau panel chuyển thành hàm thuần `audit_summary` và `verify_cleanup` để test được. Khi phải giữ log thô ở nhánh lỗi, `retain_audit` che token và mã ghép phiên. `source_snapshot` gắn thêm ADR178.

**Review trước merge:** Một lượt review đối kháng theo 4 chiều đưa ra 8 phát hiện. 5 phát hiện được xác nhận: chưa kiểm join sạch của worker; phần nối dây trong `run()` chưa có test; test chưa phủ dòng lỗi nằm trước các marker hoặc dòng của logger khác xen giữa; bản sao log thô ở nhánh lỗi có thể giữ credential; một dòng SQL-tools chưa commit, không liên quan, trong `dev_log.md` phải để ngoài commit. 3 phát hiện bị bác bỏ (đều về câu chữ trong ADR). Mọi phát hiện về mã đã được sửa trước khi merge, và các điều kiện chặt hơn được ghi trong ADR178. CI của PR #28 (run 42333443467): ci-gate thành công; test-python 6.150 passed, 368 skipped, 164 deselected; test-python-quarantine 134 passed; lint và test-js pass.

**Cổng phần mềm (không gọi model):** Cùng lệnh phạm vi hồi quy liên quan như hai lượt trước: 1.122 test Python liên quan pass, 0 fail/lỗi/skip, và 27 test JS pass trên commit `73cecdf`. Ruff check và format pass trên các file đã đổi, đã ghim hash SHA-256 của 307 file nguồn.

**Lượt chạy:** Thư mục cục bộ `data/backups/d74-main-integration-adr178/` (không đưa vào git). Bắt đầu lúc 10:31:15, ghi kết quả lúc 10:32:53 (giờ địa phương của Home Server). Đúng một panel, 0 retry.

**Kiểm tra trước, sau khi CORE sẵn sàng và trước khi nạp model voice:** CORE dùng 1.255.170.048 byte RSS (khoảng 1,17 GiB). 2 tiến trình GPU lạ dùng tổng 235.839.488 byte (khoảng 225 MiB). Cả hai đều dưới ngưỡng dừng (6 GiB và 1 GiB), nên panel được chạy.

**Chuẩn bị nhóm model:** 51,45 giây, đo riêng và không tính vào 4 giây.

| Dòng | Kết quả | Server (s) | Client (s) | ASR / LLM / TTS (s) |
|---|---|---:|---:|---|
| heldout-vi_vn-0036 | EXACT_COMPLETE_PCM | 3,412 | 3,447 | 0,689 / 1,082 / 1,571 |
| heldout-vi_vn-0024 | EXACT_COMPLETE_PCM | 2,608 | 2,619 | 0,681 / 0,476 / 1,435 |
| heldout-vi_vn-0078 | EXACT_COMPLETE_PCM | 3,747 | 3,753 | 0,912 / 0,694 / 2,131 |
| heldout-vi_vn-0040 | EXACT_COMPLETE_PCM | 3,182 | 3,187 | 1,077 / 0,428 / 1,665 |
| negative-1 | CORRECT_NO_SPEECH | — | 0,024 | chặn trước ASR/CORE/TTS |
| negative-3 | CORRECT_NO_SPEECH | — | 0,017 | chặn trước ASR/CORE/TTS |

Cả 6 dòng cho ra playback, PCM và WAV có SHA-256 giống hệt lượt ADR176, tức cùng transcript, câu trả lời và audio như lượt đã qualified trên trang thử 8092. Thời gian server của 4 câu nói là 2,608–3,747 s (client 2,619–3,753 s). Đây là thời gian xử lý và mạng loopback, **không** phải thời gian đến khi loa phát.

**Biên thời gian hẹp hơn:** Dòng chậm nhất chỉ còn khoảng 0,25 s dưới trần 4 giây. Ở lượt ADR176, cùng các dòng này mất 2,247–3,241 s. Dòng 0036 tăng từ 2,247 s lên 3,412 s; phần tăng lớn nhất nằm ở giai đoạn LLM, từ 0,511 s lên 1,082 s, dù câu trả lời giống hệt. Thời gian xử lý, nhất là của LLM, dao động giữa các lượt; một panel 4 câu nói không phải p95 và không bảo đảm biên này.

**Ngân sách và dọn dẹp:**
- Số lượt gọi đúng VAD 6 / ASR 4 / CORE 4 / TTS 4, readiness 1.
- 3 worker đã join, cả 3 đều sạch (mã thoát 0, không bị buộc dừng).
- Web process thoát với mã −15, và runner xác nhận đã tắt êm đầy đủ (`web_shutdown_graceful` true).
- Release trả HTTP 200; trạng thái sau release là `idle`, không lỗi.
- CORE mượn vẫn sống sau khi app tắt. Đây là lần đầu bước này được đánh giá trong một B3.
- CORE do runner khởi động thoát với mã 0, đã được reap, không có lỗi guard. Đỉnh RSS lấy mẫu 8.076.844 KiB (khoảng 7,70 GiB, lấy mẫu trong lúc nạp model như các lượt trước). Đỉnh VRAM 8.792 MiB, VRAM trống thấp nhất 2.251 MiB, MemAvailable thấp nhất 17.810.108 KiB (khoảng 17,0 GiB).
- Sau lượt chạy không còn tiến trình native nào, và nguồn không đổi.
- Audit có 0 dòng ERROR/CRITICAL/Traceback và không chứa credential.

Panel duy nhất mà ADR178 cho phép đã được dùng (`panel_consumed` true). Receipt chi tiết nằm trong thư mục cục bộ ở trên; SHA-256 của các file riêng tư chính, gồm `result.json`, được ghi trong [receipt công khai](evidence/d74-main-voice-b3-adr178-result.json).

## Sau PR #33 (2026-11-07)

Bằng chứng PASS ở trên gắn với commit `73cecdf` và snapshot 307 file nguồn mà cổng phần mềm đã ghim hash. Cùng ngày, PR #33 được merge vào `develop` (merge `cebf9a0`) để sửa lỗi decoder P2 ([phân tích nguyên nhân](P2_MEDIA_DECODER_ROOT_CAUSE.md)). So snapshot đã ghi với `develop` tại `cebf9a0`: hai bên đều có 307 file, không thêm hay bớt file nào, và chỉ đúng một file khác là `src/infrastructure/ocr_worker.py` (13 dòng thêm, 5 dòng xóa). Thay đổi này chỉ thêm biến `MALLOC_ARENA_MAX=1` vào môi trường của tiến trình con do `child_output` khởi chạy; trần 512 MiB giữ nguyên và không thêm retry.

Đường `/voice` có chạy qua launcher này. Bước TTS chuyển audio native sang playback (`src/infrastructure/voice/native.py`) gọi `NativeAudioNormalizer`, đi qua worker audio trong sandbox rồi `child_output` để chạy ffmpeg. Bước này nằm trong thời gian server mà B3 đo. Biến môi trường chỉ đổi số arena malloc của glibc, không đổi phép tính của FFmpeg, và loại bỏ kiểu lỗi ENOMEM ngẫu nhiên cũng có thể xảy ra ở bước chuyển playback này. Ảnh hưởng của nó tới thời gian B3 **chưa được đo**, trong khi biên chỉ khoảng 0,25 s (dòng chậm nhất 3,747 s so với trần 4 giây).

Kết quả PASS ở trên là bằng chứng cho nguồn trước bản sửa. Chủ dự án được hỏi chọn một trong hai hướng:
- chấp nhận B3 PASS hiện có cho release này, kèm ghi chú rằng khác biệt nguồn duy nhất là biến môi trường của PR #33; hoặc
- duyệt đúng một panel B3 mới trên commit sau bản sửa (thư mục kết quả mới, cùng quy tắc ADR176/ADR178, cần chủ dự án duyệt rõ).

**Quyết định** *(owner 2026-11-07, operator record)*: sau khi PR #34 được merge, chủ dự án trả lời "Giữ PASS kèm ghi chú", tức chọn hướng thứ nhất. B3 PASS theo ADR178 (commit `73cecdf`, snapshot 307 file) là bằng chứng B3 cho release này, kèm ghi chú sau:
- Khác biệt nguồn duy nhất so với mã sau bản sửa là thay đổi của PR #33 trong `src/infrastructure/ocr_worker.py`: biến `MALLOC_ARENA_MAX=1` cho tiến trình con do `child_output` khởi chạy, trong đó có lượt ffmpeg chuyển audio TTS sang playback của `/voice`, nằm trong thời gian server mà B3 đo.
- Trần 512 MiB giữ nguyên và không thêm retry; biến này chỉ đổi số arena malloc của glibc, không đổi phép tính của FFmpeg.
- Ảnh hưởng tới thời gian B3 chưa được đo, với biên khoảng 0,25 s (dòng chậm nhất 3,747 s so với trần 4 giây). Rủi ro còn lại này được chấp nhận theo lựa chọn của chủ dự án.

Panel B3 mới không được duyệt và sẽ không chạy. Quyết định cũng được ghi trong [hồ sơ D90](D90_RELEASE_DECISION_DOSSIER.md). Một phép đo vật lý B4 trên bản build có PR #33 sẽ bao gồm thay đổi này. Các kết quả B3 đã ghi không bị đổi nhãn.

## Còn mở

- B4: đo vật lý từ lúc bấm Gửi đến lúc loa phát tiếng đầu tiên, do chủ dự án tự đo theo [checklist](D74_PHYSICAL_FIRST_AUDIBLE_CHECKLIST.md). Vì B3 đã PASS, checklist có thể lặp lại trên `/voice` theo gate B4 của ADR174. Physical first-audible ≤4 giây vẫn UNVERIFIED.
  - Cập nhật 2026-11-08: sau một buổi trên `/voice` không quay video, chủ dự án chấp nhận phần first-audible của B4 kèm ghi chú (không có bản ghi khách quan nên độ trễ loa/HDMI chưa được đo; khoảng thời gian phía server chậm nhất 3,93 s; chưa thử tình huống im lặng; không báo các lượt thuộc tình huống nào; lần Chuẩn bị đầu lỗi `dependency_failed` và được thử lại ngay; chỉ áp dụng cho PC, Brave, microphone, đầu ra HDMI và lane trong manifest B3, không phải p95 hay SLO). Physical first-audible ≤4 giây vẫn chưa được đo khách quan; quyết định model/giọng/default/sản phẩm vẫn mở. Xem [chấp nhận B4](D74_B4_OWNER_ACCEPTANCE.md). Kết quả B3 ở trên không đổi.
- Câu ngắn, nói nhỏ và tiếng ồn phòng.
- Quyết định bật dùng sản phẩm, model, giọng và default; D90. `ASSISTANT_VOICE_ENABLED` vẫn mặc định 0 và chỉ cho phép mục đích `integration_evaluation`.
- Nhánh: kết quả này vào `develop` qua PR #29 (`d97119c`); cùng với LICENSE (PR #25), ADR176 (PR #26) và ADR178 (PR #28), nó lên `staging` qua PR #30 (`0ec664d`) và `production` qua PR #31 (`4dcf8db`) ngày 2026-11-07. Đây chỉ là promote nhánh: không có tag, GitHub Release hay deploy lên Home Server. Sau đó `develop` nhận thêm PR #32 (tài liệu), PR #33 (sửa mã P2, merge `cebf9a0`) và PR #34 (tài liệu, merge `8ecff62`); khi đó `staging` và `production` chưa đổi, nên lượt promote kế tiếp sẽ mang theo thay đổi mã của PR #33. Sau PR #35 (tài liệu ghi lựa chọn B3 của chủ dự án, merge `dea1b55`), ngày 2026-11-08 `develop` được promote lên `staging` qua PR #36 (`4c99408`) và lên `production` qua PR #37 (`2e5e242`), mang theo PR #32–#35, trong đó có thay đổi mã của PR #33; ngay sau lượt này, ba nhánh có cùng một cây. Đây cũng chỉ là promote nhánh: không có tag, GitHub Release hay deploy lên Home Server.
