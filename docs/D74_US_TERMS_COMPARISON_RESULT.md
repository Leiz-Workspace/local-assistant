# D74 — Python Anh–Mỹ và các từ tiếng Anh khác trên cùng giọng

**Mục đích:** Đối chiếu thay đổi phiên âm có căn cứ cho Python/GitHub/server, thêm Docker/browser/database làm kiểm tra, giữ nguyên model, giọng và đường API/ngắt câu trước.

**Ngày:** 2026-11-04, Asia/Ho_Chi_Minh. **Trạng thái:** hoàn tất kỹ thuật 12 cặp/24 vị trí audio; **chưa có đánh giá nghe bản mới**. Không tuyên bố đã sửa accent Mỹ hoặc giữ nguyên cảm nhận giọng chỉ dựa trên hash đầu vào. [ADR-160](ADR/160-us-term-phonemes-with-retained-voice-and-api.md), [authority](evidence/d74-us-terms-authorization.json), [actual result](evidence/d74-us-terms-result.json), [verification](evidence/d74-us-terms-verification.json).

## Trang nghe trước–sau

- [Trúc Ly — sáu câu, mười player](../data/backups/d74-vi-approved-campaign-20261103/us-terms-first/review/truc-ly.html).
- [Ngọc Huyền — sáu câu, mười player](../data/backups/d74-vi-approved-campaign-20261103/us-terms-first/review/ngoc-huyen.html).
- [Trang đủ hai giọng](../data/backups/d74-vi-approved-campaign-20261103/us-terms-first/review/index.html).
- [Toàn bộ bốn file code/test đã chạy](../data/backups/d74-vi-approved-campaign-20261103/us-terms-first/review/full-code.zip); exact source giữ thêm trong `executed-source/`.

Các cặp dùng đúng cùng câu và preset. Cột trái là bản hiện có, cột phải là bản thử. Với Docker/browser chỉ có một clip đối chứng vì input không đổi; không tạo thêm một lượt giống input rồi coi là cải thiện. Python có cả câu Việt chứa API và câu Anh hoàn chỉnh. Database nằm trong câu có server: phoneme database không đổi, nhưng âm thanh cả câu vẫn có thể thay đổi.

Nghe xem từ đích đúng/tự nhiên hơn không, cả câu có bị máy móc hoặc đổi chất giọng không. Riêng câu Python/API cần nghe API còn đúng không: policy API giữ nguyên nhưng prompt thay đổi có thể ảnh hưởng âm thanh. Panel không phải benchmark mù độc lập và không chứng nhận toàn bộ khả năng tiếng Anh.

## Thay đổi và căn cứ

| Từ | Cách xử lý trong lượt thử |
|---|---|
| Python | `pˈaɪθən` → `pˈaɪθɑːn`, theo [mẫu US Cambridge](https://dictionary.cambridge.org/pronunciation/english/python) |
| GitHub | Context `ɡˈɪt hˈʌb` → dictionary nguyên từ `ɡˈɪthʌb` của SDK đang giữ; không gọi đây là IPA chính thức của hãng |
| server | `sˈɜːvɚ` → `sˈɜːɹvɚ`, thử thể hiện âm r theo [American entry của Cambridge](https://dictionary.cambridge.org/dictionary/english/server); đây là cách biểu diễn thử nghiệm, chưa chứng minh âm học tương đương |
| Docker | Giữ `dˈɑːkɚ` làm control; [dictionary docker](https://dictionary.cambridge.org/dictionary/english/docker) là tham chiếu từ đồng dạng, không xác minh riêng giọng thương hiệu |
| browser | Giữ `bɹˈaʊzɚ` làm control, đối chiếu [mẫu US](https://dictionary.cambridge.org/us/pronunciation/english/browser) |
| database | Giữ `dˈeɪɾəbˌeɪs` của SDK; chưa kết luận phát âm nghe được là đạt |

Probe SDK/tokenizer thực tế xác nhận đúng các span cần đổi, roundtrip token chính xác/0unknown, giữ dấu hỏi/gaps và API stress ở cả hai phía bằng nguyên hàm ADR-159. Ngoài span đã khai báo không sửa phoneme. Không dùng cách viết âm tiết Việt, thêm câu đệm, đổi tham chiếu giọng hoặc xử lý sửa audio.

Mỗi cặp dùng chung cap nhỏ hơn của hai input gốc: Python VI162/EN102; Docker118; GitHub136 thay vì baseline gốc140; browser146; server/database148. Không tăng allowance để có kết quả. Cap GitHub phía baseline mới được giảm để giữ điều kiện chung; không gọi mọi cap là nguyên giá trị mặc định. Các giới hạn đầy đủ được đóng trong probe trước model load.

## Số lượt thực tế và kiểm tra

**16 request mới/16 inner chunks**, chia8baseline mới +8candidate; tất cả EOS/hoàn chỉnh, hai worker exit0/joined,0retry/0chưa gọi. Giữ nguyên4baseline Python cũ và chia sẻ4control input không đổi, tạo đủ24vị trí logic/12cặp. Trần20request chỉ dùng16; bốn suất còn lại không sử dụng. Trang đủ có20player:16output mới +4cũ, mỗi trang giọng có10player.

Tám cặp có thay phiên âm đều cho waveform khác; bốn control dùng chung baseline nên byte-identical theo thiết kế. Không coi khác waveform là phát âm tốt hơn. Bốn cặp GitHub/server có baseline mới được đo speaker/reference-code hashes ở cả hai phía và đều khớp. Bốn baseline Python cũ được giữ theo source/model/preset/audio provenance; không bịa phép đo embedding quá khứ. Perceived voice identity vẫn cần nghe.

**295 PASS/0FAIL/0ERROR/0SKIP,5,31giây**, Ruff format/check E4,E7,E9,F PASS trước source freeze.13tests mới kiểm term-only/API preservation, controls, cap chung không tăng, original speaker/ref/sampling/native joining, source/probe mismatch, old/shared reuse, actual pair voice drift, fixed request budget, first error/cancellation/join và media trung thực. Full5889 vẫn là snapshot lịch sử.

Worker baseline wall8,223giây/peak sampledRSS RAM1313,3MiB; worker US8,531giây/1304,2MiB, cả hai exit0. Giữ CPU0,1/hai threads/AS8GiB/RSS2GiB/headroom14GiB/root8GiB/panel120s, không GPU. Không dùng TTS riêng thay số đo first-audible vật lý≤4giây.

750application/210protected/33prior research files,4295SDKentries, weights/presets/audio cũ và hàm API đều giữ nguyên; native/container baseline phục hồi. Không tải model/reference/audio ngoài, train, thay app/config/SDK/Vault/database/Docker hoặc gọi ASR/CORE/Brave. Chỉ đọc dictionary công khai, thêm nghiên cứu/test/báo cáo.

## Tiến độ

VOICE-ENGLISH-READING-001/VOICE-BILINGUAL-IDENTITY-001 đã có paired word panel thực tế, acoustic en-US/identity/naturalness còn mở. API pronunciation, VI/date/prosody accepted-scope trước giữ nguyên; API trong clip mới cần kiểm lại. XI chưa có nhận xét nghe mới. Model/voice/default/policy sản phẩm chưa chọn; ADR155workflow chưa duyệt/chưa chạy, D60 deferred, rights/no-speech/physical4second/product/D90release vẫn mở.
