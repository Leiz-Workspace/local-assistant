# D74 — Python Anh–Mỹ và các từ tiếng Anh khác trên cùng giọng

**Mục đích:** Đối chiếu thay đổi phiên âm có căn cứ cho Python/GitHub/server, thêm Docker/browser/database làm kiểm tra, giữ nguyên model, giọng và đường API/ngắt câu trước.

**Ngày:** 2026-11-04, Asia/Ho_Chi_Minh. **Trạng thái cập nhật:** chủ dự án xác nhận **Trúc Ly phát âm chuẩn Anh–Mỹ trên bộ đã nghe**, **Ngọc Huyền không đạt**, ví dụ “I” đọc như “i”. [Phản hồi nguyên văn và trace](evidence/d74-us-terms-owner-voice-assessment.json). Đây là nhận xét theo giọng/cấp panel, chưa có nhãn từng clip hoặc xác nhận riêng naturalness/identity/API trong bản mixed mới. Giữ kết quả kỹ thuật 12 cặp/24 vị trí audio và mọi file trước. [ADR-160](ADR/160-us-term-phonemes-with-retained-voice-and-api.md), [authority](evidence/d74-us-terms-authorization.json), [actual result tại thời điểm chạy](evidence/d74-us-terms-result.json), [verification](evidence/d74-us-terms-verification.json).

## Quyết định sau khi nghe

| Giọng | Đánh giá chủ dự án | Hướng tiếp tục |
|---|---|---|
| Trúc Ly | Phát âm chuẩn Anh–Mỹ trên panel đã nghe | Giữ nguyên audio/source; ưu tiên cho bước xác minh song ngữ VI/en-US tiếp theo |
| Ngọc Huyền | Không đạt tiếng Anh, nhiều lỗi; I nghe như i | Chưa đủ điều kiện tiếng Anh theo panel này; giữ kết quả làm bằng chứng, không suy ra chất lượng VI bị bác bỏ |

Đã kiểm tra lại **cả baseline và candidate của câu “I write code in Python every day.” ở hai giọng**. Cả bốn trace thật đều bắt đầu bằng `ˈaɪ`; token/probe/native binding đã được kiểm và các clip đều kết thúc EOS. Chưa có bằng chứng frontend biến pronoun I thành `/i/`. Ngọc Huyền vẫn tạo cách đọc không đạt theo người nghe dù nhận đầu vào `/aɪ/`; chưa xác định cơ chế riêng của model/reference/decoder và không kết luận giọng này không bao giờ có thể nói tiếng Anh tốt.

Không tạo per-clip PASS/FAIL, MOS, xác nhận nghe đủ hoặc gán lỗi riêng baseline/candidate khi người dùng chưa chỉ rõ. Naturalness, mức giống giọng và API trong mixed audio mới vẫn chưa có xác nhận riêng. Ưu tiên nghiên cứu Trúc Ly phù hợp với mục tiêu cùng giọng Việt/Anh, chưa phải chọn voice/model/default hay kích hoạt sản phẩm.

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

VOICE-ENGLISH-READING-001/VOICE-BILINGUAL-IDENTITY-001 có kết quả nghe theo giọng: Trúc Ly accepted pronunciation trong phạm vi panel, Ngọc Huyền rejected English. Bước tiếp theo ưu tiên xác minh Trúc Ly trên corpus VI/en-US/mixed rộng hơn, tách rubric pronunciation/accent khỏi naturalness/identity; dependency là panel/source hiện có, corpus khai báo trước và bounded protocol/code riêng được kiểm thử. Effort một milestone xác minh, rủi ro overfit panel nhỏ và regression ngoài từ đã sửa; Lượt xác minh riêng sau đó đã tạo đủ 10 clip mới theo ADR161; xem [kết quả và trang nghe](D74_TRUC_LY_VALIDATION_RESULT.md). Không dùng suất dư của lượt cũ. Giữ toàn bộ source/audio đã qua nghe.

API pronunciation, VI/date/prosody accepted-scope trước giữ nguyên; API trong clip mới cần kiểm lại. XI chưa có nhận xét nghe mới. Model/voice/default/policy sản phẩm chưa chọn; ADR155workflow chưa duyệt/chưa chạy, D60 deferred, rights/no-speech/physical4second/product/D90release vẫn mở.


## Owner accepts current Trúc Ly quality; refinement stopped — 2026-11-04

[Exact feedback](evidence/d74-truc-validation-owner-acceptance.json) accepts the latest broader Trúc Ly panel as sufficient and asks to stop this refinement cycle. Known English articulation limitation retained: final sounds unclear, “this” heard as “dít”. No perfect-pronunciation claim, per-clip labels, separate naturalness/identity scores or product voice/model selection inferred. [Current report](D74_TRUC_LY_VALIDATION_RESULT.md) supersedes its earlier pending-listening status; old native results remain immutable.

Ngọc Huyền has NOT run this new10-sentence corpus; its earlier US-term panel was tested and owner-rejected, including I→i, which remains historical evidence. New-corpus evaluation PENDING separately: same corpus/policy/model and retained first failures, tested bounded voice-specific runner required because ADR161 is Trúc Ly-only; effort one evaluation milestone, risk articulation/identity/cap failure, no new run or fix claimed.0new inference/code/config/model/download changes or software tests in this feedback update;306scoped/5889full remain historical. ADR155workflow unapproved, D60deferred; physical4second/rights/no-speech/product/D90release remain open.


## Ngọc Huyền matched-context evaluation — 2026-11-04

[ADR162 result and grouped listening pages](D74_NGOC_HUYEN_VALIDATION_RESULT.md): owner “Làm đi” authorizes one Ngọc Huyền-only evaluation on exactly the same ten source/rendered sentences and twelve phone/chunk plans as Trúc Ly. Explicitly reuse the original no-weights frontend observations; no new probe/tuning/model/reference/lexicon changes.10TTS/12chunks complete/EOS,0retry/0unattempted,worker exit0/baseline restored; measured reference/speaker binding matches prior Ngọc Huyền and differs from Trúc Ly.317related PASS/0FAIL/ERROR/SKIP5.34s;40oldresearch/750application/210protected/4295SDKentries and accepted Trúc Ly audio preserved.

Ngọc Huyền new-corpus status: NATIVE COMPLETE / OWNER REPORTS API PRONUNCIATION WRONG; [feedback/input audit](evidence/d74-ngoc-api-owner-feedback.json) confirms both actual API plans/phones match Trúc Ly, so no frontend-policy drift is shown. Owner subsequently specifies [E - Pe-I / A - Pe - I](evidence/d74-ngoc-api-exact-owner-feedback.json); specific internal cause/per-clip mapping remain unknown, other ratings absent. [ADR163 one-pair boundary trial](D74_NGOC_API_BOUNDARY_RESULT.md) now completes1newTTS/1chunk with1retained baseline, samecap172/voice/reference and only2APIspaces removed according to pinned native dictionary;328relatedPASS. Owner now reports [improved but still incorrect; stop refinement](evidence/d74-ngoc-api-owner-stop.json). Both Ngọc Huyền and Trúc Ly pronunciation refinement cycles are stopped; preserve API limitation/old scores/audio, no candidate adoption. [Next D74 work](D74_NEXT_WORKFLOW_VALIDATION.md): audit recovery integration and accepted reading policy, prepare full-workflow/latency validation; ADR155 native approval remains separate. Earlier English/I→i rejection remains intact; no acoustic fix, universal quality or product/default choice inferred. No further pronunciation trial scheduled; other unscored properties remain unscored. Next priority is one recovery-integration/test preparation milestone, then a separately approved workflow benchmark; risks small-corpus limits, ASR latency/negative errors and incomplete wiring. Trúc Ly accepted with known limitations and refinement stopped; ADR155workflowunapproved/D60deferred/physical4second/rights/no-speech/product/D90releaseopen.0ASR/CORE/Brave/download/shared-service changes;5889full remains historical.
