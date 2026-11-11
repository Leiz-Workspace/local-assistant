# D74 — Trúc Ly: kiểm tra câu mới Việt–Anh

**Mục đích:** Ghi kết quả thực tế của lượt xác minh rộng hơn theo [ADR161](../ADR/161-truc-ly-broader-context-validation.md), sau khi chủ dự án chấp nhận phát âm Trúc Ly trên panel en-US trước. Đây là bộ câu mở rộng do người triển khai soạn, không phải benchmark mù độc lập.

**Trạng thái: CHỦ DỰ ÁN CHẤP NHẬN MỨC HIỆN TẠI, CÒN HẠN CHẾ; DỪNG TINH CHỈNH TRÚC LY.** [Phản hồi nguyên văn](../evidence/d74-truc-validation-owner-acceptance.json) cho biết đã đủ ổn, nhưng phụ âm cuối tiếng Anh chưa rõ, ví dụ “this” nghe thành “dít”. Ghi nhận giới hạn này, không coi là phát âm hoàn hảo hoặc tự gán điểm từng clip. [Lượt riêng Ngọc Huyền sau đó](D74_NGOC_HUYEN_VALIDATION_RESULT.md) đã tạo đủ cùng 10 câu và chờ nghe; nhận xét không đạt tiếng Anh ở panel cũ vẫn được giữ riêng.

## Nghe và phản hồi

- [Bốn câu tiếng Anh](../../data/backups/d74-vi-approved-campaign-20261103/truc-ly-validation-first/review/english.html): I, think/this, ship/sheep, right/light, Python, server, GitHub và browser.
- [Ba câu Việt–Anh](../../data/backups/d74-vi-approved-campaign-20261103/truc-ly-validation-first/review/mixed.html): Python/API/server, GitHub/Docker, 09:15 ngày 14/11/2026 và câu hỏi.
- [Ba câu tiếng Việt](../../data/backups/d74-vi-approved-campaign-20261103/truc-ly-validation-first/review/vietnamese.html): 12 sản phẩm/125000 đồng; Chương XI/xi măng và Chương VI/hành vi vi phạm; nhịp câu hỏi.

Mỗi clip có câu nguồn và điểm cần nghe ngay trên trang. Các trang được giữ để đối chiếu; không yêu cầu nghe hoặc tinh chỉnh Trúc Ly thêm trong vòng này. Chủ dự án chấp nhận tổng thể nhưng không cung cấp điểm phát âm/tự nhiên/identity riêng từng clip hoặc xác nhận nghe đủ từng mục. Không cần nhập JSON hoặc chấm MOS. Không có thu microphone, JavaScript, upload hoặc mạng trong các trang nghe; audio nhúng giữ nguyên WAV đã sinh.

## Cách thực hiện

Chỉ thêm hai module nghiên cứu và một file test. Giữ nguyên 37 file nghiên cứu trước, bản clauses/date renderer, thuật toán chia/ghép câu, speaker/reference codes ON, seed/sampling, API stress và ba target Python/GitHub/server đã thử ở ADR160. Không thêm lexicon, thay giọng/reference/model, tăng cap, sửa audio hoặc đổi mặc định sản phẩm. Câu mới khác sáu câu nguồn cũ.

Probe SDK không nạp weights xác minh 10 câu/12 đoạn theo thứ tự, roundtrip token chính xác/0 unknown, I vẫn /aɪ/, dấu hỏi và giá trị ngày giờ/số tiền/VI/XI giữ đúng. Mỗi đoạn dùng cap nhỏ hơn trong hai cap gốc và tối đa 300 frame. Kiểm reference phones là kiểm tính nhất quán với dictionary đang dùng, không chứng nhận phát âm nghe được. Hai câu ngày giờ và VI/XI mỗi câu có hai đoạn.

## Kết quả và giới hạn

10 request TTS mới/12 inner chunks, đủ EOS và native waveform; 0 lỗi/0 retry/0 chưa gọi. Một worker exit0 và được thu hồi, trạng thái dịch vụ/native trở về baseline. Actual plans khớp probe, speaker/reference-code hashes khớp Trúc Ly đã đo ở panel trước. Hash đầu vào giống nhau không chứng minh chất giọng cảm nhận giống nhau.

306 kiểm thử liên quan PASS/0 FAIL/0 ERROR/0 SKIP trong 5,39 giây; Ruff E4,E7,E9,F và format PASS trước khi đóng băng source. Bao gồm 11 test mới cho ngữ nghĩa, policy/cap, chia nhiều đoạn, voice-only, packet drift, native hashes, media, giới hạn lượt, lỗi và hủy/thu hồi worker. Lần kiểm focused đầu có 11 PASS nhưng lint báo import hashlib thừa; đã bỏ import đó trước probe/native, giữ receipt lỗi đầu. Kiểm audit sau chạy gọi nhầm thuộc tính parser.audio thay vì parser.media; sửa riêng lệnh audit; một kiểm tra khác tìm nhầm file result từng câu thay vì events.jsonl cũng được sửa đường đọc. Không sửa source/artifact hoặc chạy model lại. Full5889/750 là kết quả lịch sử, không phải lần chạy full mới.

Worker wall 13,567 giây; peak RSS RAM lấy mẫu 1402,1 MiB; TTS riêng từng câu 0,781–2,214 giây. Đây không phải phép đo submission→first-audible trên thiết bị. Giữ CPU0,1/hai threads, AS8 GiB/RSS2 GiB/headroom14 GiB/root8 GiB/wall120 giây, không GPU. 750 application/210 protected/37 research cũ và 4295 SDK entries, weights/presets/audio cũ giữ nguyên. Không tải thêm, train, gọi ASR/CORE/Brave hoặc thay Vault/database/Docker.

[Receipt kết quả](../evidence/d74-truc-validation-result.json), [audit](../evidence/d74-truc-validation-verification.json), [full version ba file code/test](../../data/backups/d74-vi-approved-campaign-20261103/truc-ly-validation-first/review/full-code.zip); source đã chạy, terminal và input/output lưu riêng nguyên hash.

## Tiến độ

VOICE-ENGLISH-READING-001 và VOICE-BILINGUAL-IDENTITY-001: Trúc Ly được chấp nhận ở mức hiện tại với hạn chế đã ghi; dừng vòng tinh chỉnh này theo ý chủ dự án. Phần Ngọc Huyền trên cùng corpus đã hoàn thành lượt tạo audio riêng theo ADR162, chờ nghe; chưa có bằng chứng đã sửa lỗi I. Module kiểm thử và giới hạn riêng giữ nguyên corpus/policy/model và kết quả cũ; bộ chạy ADR161 vẫn chỉ cho Trúc Ly. Không suy ra product adoption hoặc độ chính xác mọi câu. API/date/VI acceptance trước giữ đúng phạm vi; không bịa nhãn XI hay điểm acoustic riêng từ nhận xét tổng thể. ADR155 48 workflow chưa duyệt/chưa chạy. D60 deferred; physical4second/rights/no-speech/model/voice/product/D90 release còn mở.
