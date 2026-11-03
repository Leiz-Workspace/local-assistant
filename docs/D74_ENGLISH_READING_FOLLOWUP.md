# D74 — Giữ cách ngắt câu đã đạt, sửa đường đọc Python/API

**Mục đích:** Ghi nhận phần đã được chủ dự án xác nhận, giữ nguyên các thành phần đó và đánh giá riêng phát âm tiếng Anh cùng lỗi rè/run ở API.

**Trạng thái:** Giờ/ngày được chủ dự án xác nhận chuẩn trên bộ đã nghe; `clauses` được đánh giá tốt nhất/tự nhiên nhất. **Python và tiếng rè/run của API chưa được nghiệm thu.** [Nhận xét nguyên văn](evidence/d74-reading-quality-owner-followup.json), [ADR-157](ADR/157-english-terms-with-preferred-prosody.md), [kết quả8clip mới](evidence/d74-english-reading-result.json), [kiểm chứng sau thực thi](evidence/d74-english-reading-verification.json).

## Phần đã được xác nhận và phần còn lỗi

| Nội dung | Kết quả của chủ dự án | Phạm vi giữ lại |
|---|---|---|
| Giờ/ngày | Đã chuẩn | Xác nhận trên bộ đã nghe, không suy ra mọi định dạng/ngày chưa thử |
| Cách xử lý | “Cách đọc + ngắt câu và giữ dấu hỏi” tốt nhất và tự nhiên nhất | Giữ đường `clauses` cho bước sửa tiếp theo; chưa tự kích hoạt sản phẩm |
| Python | Lúc “Py thon”, lúc “Py thờ”; phải đọc giống tiếng Anh | Chưa đạt; bỏ cách phiên âm tiếng Việt của thử nghiệm trước |
| API | Cả hai giọng bị rè/run khi phát âm | Chưa đạt ở cả hai giọng; không coi waveform hữu hạn/EOS là hết lỗi |

Đây là nhận xét tổng quát, không phải24/48nhãn riêng hoặc MOS. Chưa chọn giữa Trúc Ly/Ngọc Huyền; không suy ra chấp nhận sản phẩm, quyền model hoặc timing4giây. Nhận xét “không lỗi âm thanh” của D70 trước đó thuộc corpus khác và vẫn được giữ đúng lịch sử.

## Thay đổi mới

Bản trước dùng lexicon thử nghiệm Python→“pai thờn”, API→“ây pi ai”. Cách đó không đáp ứng yêu cầu tiếng Anh vừa được làm rõ. Renderer mới bỏ **chỉ** các edit lexicon đó; giữ nguyên source/display text, edit giờ/ngày, bảo vệ code/URL/identifier, ngắt câu và dấu hỏi. Toàn bộ10file ADR156 và7operator trước đó nguyên hash, không sửa đường prosody đã được người dùng thích.

Tám đầu vào mới đều đi qua normalizer/G2P hiện có với chuỗi phát âm tiếng Anh tham chiếu `pˈaɪθən` và `ˈeɪ pˈiː ˈaɪ`; tokenizer không có unknown token trong probe. Đây là xác minh frontend, không chứng minh âm thanh chuẩn. Các phoneme này đã có trong SDK cũ; không tuyên bố bổ sung một năng lực model hoàn toàn mới.

Kiểm numeric các clip mục tiêu trước đó không thấy mẫu chạm/vượt full scale. Điều đó **không phủ nhận tiếng rè/run người dùng nghe được**, không xác định đoạn API hoặc nguyên nhân. Không denoise, đổi gain, cắt audio, thay sample hay tăng cap để che lỗi.

## Lượt thử mới đã thực hiện

Bốn câu ×hai giọng = **8request TTS/14chunk native**,0retry/0ASR/0CORE,0unattempted; đầu ra mono48kHz/hữu hạn/EOS, worker thoát0/joined. Giữ weights/SDK/precision/sampling/frame caps/codec/preset resolver và cách ghép cũ. Peak RSS lấy mẫu khoảng1.341MiB, dưới2GiB; giữ AS8GiB/headroom14GiB/CPU0,1/hai threads/root8GiB. Baseline native/container khớp trước-sau; không tải model/package hoặc đổi product/default/shared service.

Hai câu đầu lặp đúng text mục tiêu để so sánh **policy mới**, dùng nguyên4clip cũ làm đối chứng, không sinh lại đối chứng. Hai câu sau là diagnostic/control mới, trong đó có giờ/ngày. Tám clip đều khác bản `clauses` cũ ở các câu có đối chứng; hai clip trùng từng byte với bản `raw` cũ, phù hợp với việc đã trả về đường phát âm tiếng Anh có sẵn. Không xóa hoặc chấm lại các kết quả trước.

[Trang nghe8clip mới +4đối chứng cũ](../data/backups/d74-vi-approved-campaign-20261103/english-reading-first/review/index.html) mở trực tiếp, không server/microphone/upload/network/JavaScript. [Toàn bộ2file code/test mới](../data/backups/d74-vi-approved-campaign-20261103/english-reading-first/review/full-code.zip). Chỉ cần kiểm Python đã giống tiếng Anh chưa, API còn rè/run không và phần ngắt câu/giờ-ngày có giữ được như trước không. Chưa có nhận xét của chủ dự án cho bộ8clip này.

## Kiểm thử và giới hạn

Lượt scoped cuối **236PASS/0FAIL/0ERROR/0SKIP,4,22giây**, lint/format PASS. Trước đó có một lượt236case bị1FAIL/235PASS ở test decode video của component audio cũ (`audio_invalid_content`). Test riêng sau đó1PASS/0,47giây, rồi cùng scope236PASS; fixture đúng hashHEAD, không sửa source/test/limit cũ. Giữ receipt lỗi đầu tiên, nguyên nhân **chưa xác định**, không gọi nó là lỗi đã sửa hoặc tự bỏ test. Trial tiếng Anh này không gọi decoder đó; vấn đề intermittent được ghi riêng để điều tra trước nghiệm thu sản phẩm.

Tests mới bảo vệ phần date/prosody đã đạt, giữ English tokens/trace, khóa probe-to-input/unknown-token, namespace không weights cho probe,8slot/fail-first/no-retry và trang nghe. 750file ứng dụng/210đầu vào bảo vệ/17file nghiên cứu cũ,48clip trước/24clip gốc và planADR155 nguyên hash. Full5889 là snapshot ứng dụng trước, không phải một lượt full mới.

Phần nghe mới vẫn cần người dùng xác nhận; không tuyên bố Python/API hoặc tiếng rè đã được khắc phục chỉ từ frontend/signal metrics. ADR155workflow tiếp tục chưa duyệt/chưa chạy. Chưa có model/voice/default activation, physical first-audible≤4giây, quyền sử dụng hoặc release approval. D60 tiếp tục chờ.
