# D74 — Chỉ đổi trọng âm API trên cùng câu và giọng cũ

**Mục đích:** Ghi kết quả phép thử hẹp sau khi bộ đối chiếu khác câu bị chủ dự án đánh giá tệ hơn; giữ nguyên ngắt câu, giờ/ngày và toàn bộ bằng chứng trước.

**Ngày:** 2026-11-04, Asia/Ho_Chi_Minh. **Trạng thái:** bốn clip mới hoàn tất kỹ thuật; chất lượng phát âm/rè/tự nhiên **CHƯA ĐƯỢC CHẤP NHẬN**. [ADR-159](ADR/159-api-stress-only-on-retained-clause-path.md), [quyền thực hiện theo “Làm đi”](evidence/d74-api-stress-authorization.json), [kết quả máy](evidence/d74-api-stress-result.json), [kiểm tra sau chạy](evidence/d74-api-stress-verification.json).

## Nghe đúng cặp trước–sau

[Trang nghe bốn cặp cùng câu, cùng giọng](../data/backups/d74-vi-approved-campaign-20261103/api-stress-first/review/index.html): trái là bốn clip ADR-157 cũ nguyên vẹn; phải là bốn clip mới. Hai câu đều đã có trong bộ cũ, mỗi câu dùng Trúc Ly và Ngọc Huyền:

- “Bạn muốn học Python hay dùng API của ứng dụng?”
- “Chị sẽ nhắc bạn lúc 09:15 ngày 14/11; sau đó cùng kiểm tra API.”

Cần đối chiếu API có đọc **Ei–Pi–Ai**, còn rè/run không và cả câu tự nhiên hơn hay tệ hơn. Đối chứng bên trái vẫn có lỗi English/API đã báo; không gọi nó là cấu hình đã đạt phát âm. Bộ carrier bị chê giữ trạng thái **OWNER REPORTED WORSE / NOT ACCEPTED**, không trộn vào lượt mới hoặc yêu cầu nghe lại.

[Toàn bộ bốn file code/test mới](../data/backups/d74-vi-approved-campaign-20261103/api-stress-first/review/full-code.zip); source đã chạy được lưu riêng trong `executed-source/`. Trang tự chứa tám WAV nguyên hash, không server, script, microphone, upload hoặc network.

## Thay đổi duy nhất được thử

Phoneme API trong câu cũ là `ˈeɪ pˈiː ˈaɪ`; từ điển SDK dùng dạng compact `ˌeɪpˌiːˈaɪ`. Lượt này chỉ mượn **kiểu trọng âm** của từ điển: `ˌeɪ pˌiː ˈaɪ`. Hai dấu nhấn chính đổi thành nhấn phụ theo một policy khai báo; khoảng trắng, nguyên âm/phụ âm và phần còn lại không đổi. Không kết luận riêng dấu nào gây tác động hoặc cho rằng pattern này chắc chắn sửa đúng âm Ei.

Adapter mới chỉ bọc dependency phonemizer của **ProsodyAdapter cũ nguyên file**. Giữ renderer English/date/time, câu/giọng trước, chia câu, gaps, dấu hỏi, reference-code ON, preset/sampling/seed/codec và hàm cap gốc. Probe model-free kiểm roundtrip token chính xác, zero unknown, cùng số ký tự/syllable/frame cap và đúng một API span/request. Frame cap gốc vẫn 162 cho câu hỏi; câu ngày/giờ có hai đoạn cap 228 và 108, tuyệt đối ≤300. Không dùng đường ref-off/direct-phoneme carrier bị chê hoặc đổi chữ A sang cách viết phỏng đoán.

Input Python giữ nguyên phoneme; **chưa chứng nhận âm Python không thay đổi khi nghe**, vì sửa prompt chung có thể ảnh hưởng toàn đoạn. Ngày/giờ là đoạn tách trước API nên kiểm được waveform riêng: cả hai giọng khớp từng byte với chunk ADR-157 cũ.

## Kết quả thực tế và giới hạn

**4 request TTS / 6 inner chunks**, tất cả EOS=true/hoàn chỉnh, worker exit0/joined; 0 lỗi/0 chưa gọi/0 retry. Bốn waveform cuối khác bản đối chứng. Đây là thay đổi đầu ra, chưa phải chứng nhận English/API tốt hơn hoặc hết rè.

TTS từng request khoảng 0,917/1,711/0,983/1,821 giây; thời lượng phát 2,56/5,29/2,88/5,49 giây. Worker wall 7,395 giây, peak RSS RAM lấy mẫu 1341,3 MiB. Giữ CPU0,1/hai threads, AS8GiB/RSS2GiB/headroom14GiB/root8GiB/wall120s; không dùng GPU. Các số TTS không thay cho thời gian từ gửi câu hỏi tới loa phát; mục tiêu vật lý tối đa4giây còn mở.

**267 PASS / 0 FAIL / 0 ERROR / 0 SKIP, 4,78 giây**, Ruff format/lint E4,E7,E9,F PASS trước khi đóng source hash. Có 10 tests mới kiểm sửa đúng term, không đụng context/Python/dấu hỏi, cap và reference ON, waveform ngày/giờ, binding với chunk cũ, dừng lỗi đầu tiên, giới hạn4/6, cleanup và media cục bộ. Hai lần lỗi fixture test đầu tiên được giữ riêng: quyền thư mục test không0700; sau đó kiểm nhầm biến HF_HUB_CACHE là mount weights. Cả hai sửa trong test mới, không hạ guard, không chạy model khi test lỗi. [Lần đầu](evidence/d74-api-stress-first-software-failure.json), [lần hai](evidence/d74-api-stress-second-software-failure.json). Full5889 vẫn là snapshot application cũ; không công bố full mới hoặc suy từ software PASS thành chất lượng nghe.

750 application/210 protected files,25 research files trước,4295 SDK inventory entries, weights/presets và mọi audio cũ được giữ. Native/container baseline phục hồi, không thêm model/package, ASR/CORE/Brave, cấu hình sản phẩm hoặc tác động Vault/database/Docker. Không chọn giọng/model hoặc áp dụng policy mới vào sản phẩm.

## Trạng thái tiến độ

Hai task P1 English/API còn mở, chờ kết quả nghe bộ bốn cặp mới; các mục cũ không được chấm lại. Phần giờ/ngày/clauses đã chấp nhận giữ nguyên phạm vi. Python còn mở; ADR15548workflow vẫn chưa duyệt/chưa chạy. D60 tiếp tục pending theo yêu cầu, D74 quyền/no-speech/model/voice/physical4second/product và D90release vẫn mở. Nếu bộ mới vẫn sai hoặc tệ hơn, loại policy khỏi hướng áp dụng, giữ kết quả và không tự retry hay chọn model khác.
