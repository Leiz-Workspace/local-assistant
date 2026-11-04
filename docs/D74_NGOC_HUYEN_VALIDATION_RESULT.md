# D74 — Ngọc Huyền: cùng bộ 10 câu Việt–Anh

**Mục đích:** Ghi kết quả lượt thử riêng Ngọc Huyền theo [ADR162](ADR/162-ngoc-huyen-matched-context-validation.md), sau chỉ dẫn “Làm đi”. Dùng đúng bộ câu đã thử với Trúc Ly để so sánh; không tinh chỉnh lại Trúc Ly hoặc thay model.

**Trạng thái: 10/10 clip hoàn chỉnh; CHỦ DỰ ÁN BÁO API VẪN ĐỌC SAI.** [Phản hồi và đối chiếu đầu vào](evidence/d74-ngoc-api-owner-feedback.json) ghi API chưa đạt; chủ dự án sau đó mô tả [“E - Pe-I, A - Pe - I”](evidence/d74-ngoc-api-exact-owner-feedback.json), chưa có tên clip cụ thể hoặc đánh giá những mục còn lại. Chưa kết luận tiếng Anh được sửa hoặc tốt hơn. Phản hồi cũ Ngọc Huyền đọc I thành i vẫn giữ nguyên. Trúc Ly đã được chấp nhận mức hiện tại với hạn chế “this” nghe thành “dít”, vòng tinh chỉnh đó đã dừng.

## Trang nghe

- [Bốn câu tiếng Anh](../data/backups/d74-vi-approved-campaign-20261103/ngoc-huyen-validation-first/review/english.html): I, think/this, ship/sheep, right/light, Python/server, GitHub/browser.
- [Ba câu Việt–Anh](../data/backups/d74-vi-approved-campaign-20261103/ngoc-huyen-validation-first/review/mixed.html): API/Python/server, GitHub/Docker, ngày giờ và câu hỏi.
- [Ba câu tiếng Việt](../data/backups/d74-vi-approved-campaign-20261103/ngoc-huyen-validation-first/review/vietnamese.html): số tiền, XI/xi măng, VI/hành vi vi phạm và nhịp câu.

Tên câu giống [bộ Trúc Ly](D74_TRUC_LY_VALIDATION_RESULT.md). Chú ý I còn đọc thành i không, phụ âm cuối, thuật ngữ, API có rè/run không, ngắt câu và độ tự nhiên/chất giọng. Chỉ cần báo tên clip và chỗ nghe chưa ổn; không yêu cầu điền JSON/MOS. Trang nghe nhúng nguyên WAV, không thu âm, JavaScript, upload hoặc mạng.

## Vì sao vẫn có lỗi API?

Hai câu có API của Ngọc Huyền nhận cùng câu nguồn, text đã xử lý, toàn bộ phone plans và actual phonemes như Trúc Ly. API vẫn dùng `ˌeɪ pˌiː ˈaɪ` và đúng một lần xử lý ở mỗi câu. Native WAV được kiểm nguyên hash. Không thấy bằng chứng mất quy tắc API hoặc đầu vào quay về cách đọc cũ.

Lượt này là đánh giá cùng cách xử lý khi đổi sang preset Ngọc Huyền, chưa có sửa riêng giọng đó. Cùng phiên âm không bảo đảm cách phát âm nghe được giống nhau khi speaker/reference conditioning khác. Chưa đủ bằng chứng tách nguyên nhân cụ thể trong model/reference/decoder; không suy ra chắc chắn do một thành phần hoặc tự phỏng đoán cách viết âm tiết mới.317 software tests và EOS xác minh bộ chạy, không chứng nhận API đọc đúng. Ngọc Huyền chưa đạt yêu cầu API theo phản hồi; bản Trúc Ly accepted-with-limitations giữ nguyên.

## Giữ nguyên điều kiện

Dùng lại rõ ràng probe SDK không nạp weights của ADR161; không công bố là probe mới. Xác minh SHA, renderer nguồn và tất cả field: cùng source/rendered text, 12 đoạn theo thứ tự, phones, dấu hỏi, gaps, ngày giờ/số/VI-XI và conservative caps. Chỉ đổi preset sang Ngọc Huyền đã có. API stress, Python/GitHub/server targets, model/weights/SDK, reference codes ON, seed/sampling và ghép waveform giữ nguyên. Không thêm lexicon/reference, tải thêm, train, tăng cap hoặc sửa audio.

Thêm hai module nghiên cứu và một file test riêng, giữ nguyên 40 file nghiên cứu trước. Packet chỉ đọc được bind SHA và giọng khi worker sẵn sàng. Worker chặn sai ID/text/voice, lặp request và quá ngân sách. Kế thừa bộ lập kế hoạch/kiểm native của Trúc Ly, nên tên log kiểm tra vẫn có thể mang prefix truc_validation; request thật/readiness và speaker/reference-code hashes xác nhận Ngọc Huyền, khớp preset Ngọc Huyền ở panel cũ và khác Trúc Ly. Không suy từ hash thành giọng cảm nhận hoặc phát âm đúng.

## Kết quả thực tế

10 request TTS mới/12 inner chunks, tất cả EOS/hoàn chỉnh, 0 retry/0 chưa gọi, một worker exit0 và được thu hồi; baseline dịch vụ/native phục hồi. Không ASR/CORE/Brave hoặc ADR155 workflow. Trần 10 request/16 chunks/120 giây được giữ. Bộ câu do người triển khai soạn, không benchmark mù độc lập.

317 kiểm thử liên quan PASS/0 FAIL/0 ERROR/0 SKIP trong 5,34 giây; Ruff E4,E7,E9,F và format PASS trước source freeze. 11 test mới kiểm packet/corpus/voice, drift, ID/text/replay/budget, original multi-chunk/reference/sampling/join, namespace read-only, authority, media và first-error/cancellation/cleanup. Lần focused đầu có 10 PASS/1 FAIL vì thư mục fixture không private, guard gốc từ chối đúng; sửa fixture thành0700, sau đó11 PASS/0,31giây. Giữ receipt đầu, không sửa guard hoặc gọi model trước khi sửa. Full5889/750 vẫn là snapshot lịch sử, không phải full regression mới.

Worker wall14,703 giây; peak sampled RSS RAM1456,0 MiB, TTS riêng từng câu0,742–2,388 giây. Giữ CPU0,1/hai threads/AS8 GiB/RSS2 GiB/aggregate8 GiB/headroom14 GiB/root8 GiB, không GPU. Chưa đo submission→first-audible vật lý4giây. Audit xác minh đủ10actual event/request/native outputs, 12chunks, 10/4/3/3player coverage, source freeze/snapshot/ZIP/terminal/authority, 750application/210protected/40research cũ và4295SDKentries. Không thay app/config/Vault/database/Docker/model/preset hoặc audio cũ.

[Result receipt](evidence/d74-ngoc-validation-result.json), [verification](evidence/d74-ngoc-validation-verification.json), [full version ba file code/test](../data/backups/d74-vi-approved-campaign-20261103/ngoc-huyen-validation-first/review/full-code.zip).

## Tiến độ

VOICE-ENGLISH-READING-001/VOICE-BILINGUAL-IDENTITY-001: Ngọc Huyền đã có cùng corpus hoàn chỉnh, API bị chủ dự án báo đọc sai, các mục còn lại chưa có nhãn riêng. Dependency tiếp theo là mô tả lỗi nghe cụ thể và giả thuyết có căn cứ trước một phương án sửa riêng; effort một milestone đánh giá; rủi ro lỗi phát âm/identity/naturalness ngoài panel nhỏ. Không tự lên lịch tuning hoặc chọn voice/model/default sản phẩm. Trúc Ly accepted-with-limitations/refinement stopped giữ nguyên; kết quả không đạt tiếng Anh trước đây của Ngọc Huyền không bị xóa hoặc thay điểm. D60 deferred, ADR15548workflow chưa duyệt/chưa chạy, physical4second/rights/no-speech/product/D90release còn mở.


## One-pair boundary follow-up — 2026-11-04

[ADR163 result and two-player comparison](D74_NGOC_API_BOUNDARY_RESULT.md) tests only removing two API phone spaces to match the pinned native dictionary, on retained mixed-api text/Ngọc Huyền/reference/sampling/cap172.1newrequest/1chunk/EOS plus1immutable oldbaseline,328relatedPASS; no Trúc Ly run/model/reference change. Owner now reports improvement but API still wrong and stops this refinement; [current disposition/next step](D74_NEXT_WORKFLOW_VALIDATION.md). No API fix or product adoption inferred. The other9metadata rows are not requests; all old10outputs and rejection remain unchanged.
