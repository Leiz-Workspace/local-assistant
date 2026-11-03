# D74 — Kết quả campaign giọng Việt ADR-154

**Mục đích:** Ghi kết quả thực tế của lượt thử đã duyệt, lỗi bộ chạy, dữ liệu được giữ lại và điều kiện cho bước tiếp theo.

**Ngày:** 2026-11-03. **Trạng thái:** TTS standalone hoàn tất về kỹ thuật; workflow bị vô hiệu do lỗi bộ chạy, đã dừng. D74 sản phẩm và D90 release vẫn OPEN. [Phê duyệt](evidence/d74-adr154-owner-approval-20261103.json), [kết quả có mã băm](evidence/d74-adr154-partial-result-20261103.json), [kiểm chứng cuối](evidence/d74-adr154-final-verification-20261103.json), [ADR-154](ADR/154-proposed-isolated-vietnamese-voice-feasibility-campaign.md).

## Lựa chọn hiện tại của chủ dự án

Chủ dự án ban đầu chọn **“Chờ nghe 24 clip”**, chưa duyệt ADR-155; [receipt quyết định](evidence/d74-owner-wait-listening-20261103.json) giữ nguyên lịch sử. Sau đó đã có [phản hồi nhóm ba giọng](D74_OWNER_VOICE_FEEDBACK_20261103.md): cả ba đều ổn, thích Trúc Ly và Ngọc Huyền hơn; ngữ điệu máy móc, giờ/ngày đọc sai format, Python/API đọc chưa đúng. Chưa có nhãn từng clip hoặc lựa chọn giữa hai giọng. Các lỗi chất lượng còn mở; workflow recovery vẫn chưa được duyệt/chưa chạy.

## Những gì đã chạy

Đã tải đúng 16 artifact được duyệt, tổng **608.816.450 byte**; kiểm kích thước và SHA256 LFS hoặc Git blob của từng file. SDK riêng có 26 package, khóa phiên bản và mã băm bằng `uv`; không cài Torch/CUDA. Toàn bộ thư mục trước review khoảng 1,09 GB, dưới giới hạn 8 GiB. Hai preset thực tế chứa metadata nữ/Bắc/tự nhiên và được gọi đúng tên, không dùng alias hoặc giọng mặc định thay thế.

Bộ audit ban đầu nhận nhầm bốn file SDK theo đuôi `.pth/.bin/.npz`. Kiểm nội dung xác nhận đây là loader `uv`, từ điển phát âm `sea-g2p` và hai fixture object-array NumPy; ba graph toán học ORT cũng được kiểm mã băm riêng. Đã sửa phân loại trước khi nạp model. Giữ receipt lỗi đầu tiên; không cài lại SDK hoặc tải lại source để che lỗi.

151 tests PASS trước khi đóng băng bộ chạy, không FAIL/ERROR/SKIP. Hai lượt qualification và 24 lượt standalone đều trả âm thanh gốc hợp lệ, có EOS và kết thúc tiến trình với exit 0. CPU affinity 0,1, 2 threads, AS 8 GiB, RSS TTS lấy mẫu không vượt 2 GiB; chỉ dùng CPU, offline, không retry. RSS dưới đây là RAM tiến trình, không phải VRAM.

| Giọng, 8 câu/giọng | Thời gian gọi TTS nhỏ nhất–lớn nhất | Load riêng | RSS lấy mẫu cao nhất | Âm thanh gốc |
|---|---:|---:|---:|---:|
| Piper VI đối chứng cũ | 0,074–0,122 giây | 0,741 giây | 240,2 MiB | 22.050 Hz |
| VieNeu Turbo Trúc Ly | 0,694–1,438 giây | 1,466 giây | 1.380,0 MiB | 48.000 Hz |
| VieNeu Turbo Ngọc Huyền | 0,819–1,674 giây | 1,460 giây | 1.445,6 MiB | 48.000 Hz |

Các số TTS không gồm ASR, CORE, truyền/phát âm thanh; không chứng minh yêu cầu chờ tối đa 4 giây. SDK giữ nguyên text normalization, frame cap và sampling mặc định; `babble_retries=0`. Wrapper chỉ quan sát EOS và trả nguyên đối tượng native. Không chỉnh gain, cắt khoảng lặng hoặc sửa âm thanh.

## Workflow bị dừng vì lỗi gì

Bộ chạy nghiên cứu đọc `local_assistant.preset_selected`, trong khi gateway thật với preset Fast cố định trả `local_assistant.preset`. CORE đã trả câu hoàn chỉnh với `finish_reason=stop`, nhưng bộ đọc mới ném lỗi trước TTS. Test giả lập ban đầu đã dùng sai cùng cấu trúc nên không phát hiện lỗi tích hợp này.

Có **6/48 slot được dispatch, cả 6 không hợp lệ để chấm workflow; 42 chưa chạy**. Tổng native attempts của toàn campaign: **26 TTS / 6 ASR / 6 CORE**, không chạy lại sau khi dừng. Cả hai negative đã dispatch có transcript không rỗng; giữ nguyên bằng chứng, không công nhận no-speech PASS. Không có một lượt trả lời hoàn chỉnh tới PCM để chấm latency workflow hoặc phát âm thanh.

Bộ chạy cũng chưa dừng ngay ở lỗi schema vì VoicePipeline chuyển nó thành `dependency_failed`; lỗi đã lặp qua sáu slot trước khi được phát hiện và ngắt. Điều này không tuân thủ ý định dừng ngay khi lỗi phần mềm của protocol. Đã sửa đường ghi nhận lỗi metadata thành fatal, hỗ trợ đúng `preset`/`preset_selected`, và bổ sung test qua gateway thật với HTTP giả lập.

Hai tín hiệu ngắt tới wrapper/controller khiến receipt lúc đầu còn thấy CORE và thiếu receipt retirement cuối. Sau đó đã kiểm tra lại đúng tiến trình đã sở hữu: CORE đã thoát; native 0 và toàn bộ container khớp baseline. Receipt đầu tiên được giữ nguyên, thêm receipt khôi phục riêng; không bịa exit/wait4 hoặc peak RAM/VRAM CORE bị thiếu. Mã cleanup hiện giữ tác vụ stop/join qua repeated cancellation và có regression test.

## Nghe 24 clip

Mở [trang nghe24clip](../data/backups/d74-vi-approved-campaign-20261103/review/index.html) trong checkout hiện tại. [Toàn bộ7file code/test hiện tại](../data/backups/d74-vi-approved-campaign-20261103/review/full-code.zip) được đóng gói riêng; audio/SDK/weights không đưa vào Git. Trang nhúng đủ 24 WAV float gốc, không cần server, không microphone/upload/JavaScript hoặc tài nguyên mạng. Bấm phát từng clip. Mỗi mã gồm `piper-vi`, `truc-ly` hoặc `ngoc-huyen`, rồi `vi-voice-01` đến `08`.

Bạn có thể gửi nhận xét ngay trong chat theo mã clip: phát âm/dấu/đọc số ngày giờ; ngắt nhịp; rè/méo/đứt tiếng; cảm nhận nữ/miền Bắc; tự nhiên và mức chắc chắn. Phản hồi nhóm mới đã được ghi riêng; metadata giọng và EOS không thay thế nhận xét chất lượng. Ngữ điệu, cách đọc giờ/ngày và Python/API còn vấn đề. D70 cũ, 24 audio và nhận xét cũ được giữ nguyên.

## Bản sửa và bước tiếp theo

Bản sửa cùng trang nghe có **161 tests PASS / 0 FAIL / 0 ERROR / 0 SKIP, 4,27 giây**, lint và format PASS; không suy luận model thêm. Replay offline chấp nhận đúng cả6 phản hồi CORE cũ, giữ nguyên nội dung; đây chỉ là kiểm parser, không sửa điểm của workflow cũ. Có test gateway thật tạo metadata Fast, no-speech không gọi CORE/TTS, kiểm raw/WAV 48 kHz, hash/symlink, giới hạn tài nguyên, hủy/cleanup và khóa recovery khi chưa duyệt.

750 file ứng dụng/cấu hình/test cũ và 210 đầu vào bảo vệ vẫn đúng mã băm. Full 5.889 PASS trước đây thuộc snapshot ứng dụng đó; đây không phải một lượt full regression mới. Mã nghiên cứu mới nằm trong `benchmarks/`, có bộ test riêng. Không sửa model/default, source sản phẩm, Docker, Vault, database hoặc gọi Brave.

[ADR-155](ADR/155-proposed-workflow-recovery-after-caller-metadata-failure.md) chuẩn bị một lượt workflow thay thế 48 slot với bản sửa; chưa duyệt/chưa chạy. Giữ 24 clip hiện có, không lặp qualification/standalone hoặc tải model. Cần quyền chạy mới vì ADR-154 yêu cầu dừng và không tự retry khi lỗi phần mềm; sửa code không tự cấp quyền chạy lại benchmark. Phản hồi nhóm đã nhận nhưng độ tự nhiên/cách đọc chưa đạt mong muốn; cần điều tra VOICE-TEXT-READING-001 và VOICE-PROSODY-001 trước nghiệm thu. Phép đo first-audible vật lý vẫn là gate riêng, không đóng D74 bằng PCM proxy.
