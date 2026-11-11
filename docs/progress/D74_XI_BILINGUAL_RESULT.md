# D74 — XI/xi măng và yêu cầu cùng giọng Việt–Anh Mỹ

**Mục đích:** Ghi kết quả kiểm tra XI, bảo toàn VI/vi/API đã được chấp nhận theo panel và làm rõ giới hạn/hướng đánh giá chất lượng tiếng Anh trong cùng chất giọng.

**Ngày:** 2026-11-04, Asia/Ho_Chi_Minh. **Trạng thái:** 5/5 kỳ vọng chuẩn hóa XI đúng trong corpus; sáu clip hoàn chỉnh, **chưa có đánh giá nghe bộ XI mới**. Người dùng xác nhận VI/vi ổn và chọn tiếng Anh–Mỹ; tiếng Anh hiện tại còn bị nhận xét accent Việt, chưa đạt. [Phản hồi](../evidence/d74-vi-xi-bilingual-owner-feedback.json), [chọn en-US](../evidence/d74-owner-en-us-preference.json), [protocol](D74_XI_BILINGUAL_PROTOCOL.md), [result](../evidence/d74-xi-context-result.json), [verification](../evidence/d74-xi-context-verification.json).

## Cùng giọng có thể nói chuẩn cả Việt và Anh không?

Có hướng kỹ thuật để giữ danh tính giọng trong hệ thống song ngữ, nhưng chưa có bằng chứng bộ preset hiện tại đạt yêu cầu tiếng Anh của chủ dự án. Model đang dùng vốn được [tác giả công bố hỗ trợ Việt/Anh và code-switching](https://huggingface.co/pnnbao-ump/VieNeu-TTS-v3-Turbo); không nên diễn giải đơn giản là model chỉ biết tiếng Việt. Tuyên bố hỗ trợ ngôn ngữ chưa chứng minh accent/ngữ điệu tự nhiên hoặc mức giống giọng ở từng preset.

Đã kiểm tra đúng [SDK đang giữ](https://github.com/pnnbao97/VieNeu-TTS/blob/04044e1b8f822f946bafb2c88b716459f4164152/src/vieneu/v3turbo.py): signature `infer` không có tham số `language`/`accent`, `style` bị bỏ qua trên backend này; giọng tham chiếu chứa speaker embedding và reference codes. Vì vậy chưa có nút cấu hình đã được xác minh để chọn “accent Mỹ chuẩn” mà giữ mọi thứ khác. Chưa xác định tỷ trọng lỗi do frontend, model hay conditioning; không khẳng định preset reference là nguyên nhân. Bộ ablation tham chiếu trước bị chê ở cấp nhóm, không có kết quả riêng ref-off chứng minh cải thiện.

**Chốt mục tiêu en-US, cùng identity giọng VI/EN.** Tách chấm phát âm/accent/ngữ điệu khỏi mức giống giọng. Với Python, SDK hiện tạo `pˈaɪθən`; [Cambridge ghi phiên âm US `/ˈpaɪ.θɑːn/`](https://dictionary.cambridge.org/pronunciation/english/python). Đây là một khác biệt có căn cứ để chuẩn bị đối chiếu frontend Mỹ trên cùng câu/giọng, giữ API/date/clauses. Chưa chạy candidate US, chưa coi thay nguyên âm chắc chắn sửa âm thanh hoặc toàn bộ accent. Thêm tag tiếng Anh trước đó không đổi phoneme nên không được gọi là bản sửa.

VOICE-BILINGUAL-IDENTITY-001 đã đánh giá **P1**, phụ thuộc corpus VI/EN/mixed, chuẩn en-US, tiêu chí identity/phát âm, dữ liệu/quyền tham chiếu và budget. Effort một milestone thiết kế đánh giá; effort dữ liệu/training chưa ước lượng khi chưa khảo sát đủ. Rủi ro mất chất giọng, giữ accent trong tham chiếu, overfit từng từ, tăng latency/RAM. Nếu frontend chưa đủ, tham chiếu song ngữ cùng người nói hoặc adaptation/model comparison là đề xuất nghiên cứu cần dữ liệu/quyền, benchmark/resource/migration/rollback và owner approval; chưa tải model, lấy mẫu giọng, train hoặc chọn giải pháp mới. [Assessment](../evidence/d74-bilingual-identity-assessment.json).

## XI và xi măng

Không thêm luật đọc; chạy original SDK/tokenizer và đường chia câu cũ:

| Nội dung | Chuẩn hóa thực tế |
|---|---|
| Xi măng được dùng để xây nhà. | xi măng được dùng để xây nhà. |
| XI MĂNG được dùng để xây nhà. | xi măng được dùng để xây nhà. |
| Chương XI có mười một mục. | chương mười một có mười một mục. |
| Chương XI nói về xi măng và cách sử dụng. | chương mười một nói về xi măng và cách sử dụng. |
| CHƯƠNG XI nói về XI MĂNG. | chương mười một nói về xi măng. |

VI/vi đã được chủ dự án xác nhận trên panel trước, không chỉ còn là kết quả frontend. XI mới có xác minh 5/5 đầu vào và actual native phoneme trace khớp; **chưa suy ra audio đọc đúng khi chưa nghe**. Identifier XI, bare XI, lowercase identifier xi và IIX không chuẩn được lưu quan sát, không chấm đúng/sai theo một kỳ vọng tự bịa. Không suy rộng thành mọi số La Mã/tên viết tắt.

[Trang nghe sáu clip XI](../../data/backups/d74-vi-approved-campaign-20261103/xi-context-first/review/index.html): ba câu viết thường/số chương/cùng câu cho cả Trúc Ly và Ngọc Huyền; không sinh lại bộ VI/API. Sáu WAV nguyên hash, no JS/server/mic/upload/network. [Toàn bộ hai file code/test mới](../../data/backups/d74-vi-approved-campaign-20261103/xi-context-first/review/full-code.zip), exact source lưu trong `executed-source/`.

## Kiểm thử và trạng thái

**282 PASS/0 FAIL/0 ERROR/0 SKIP, 5,25giây**, Ruff format/check PASS trước freeze; bảy tests mới kiểm explicit word/Roman expectations, unscored ambiguity, source/token drift, six-slot media, no replay, first failure/cancellation/join và budget6/6. Đây là scope phần mềm liên quan; full5889 giữ lịch sử, không mới chạy full hoặc chứng nhận accent.

**6 TTS/6innerchunks/EOStrue**, không retry/lỗi/chưa gọi; worker exit0/joined. Wall6,301giây; peak RSS RAM lấy mẫu1277,1MiB; TTS riêng0,550–0,969giây. Giữ CPU0,1/hai threads/AS8GiB/RSS2GiB/headroom14GiB/root8GiB/wall120s/originalcaps. Không suy ra first-audible vật lý≤4giây.

750application/210protected/31prior research/4295SDKentries/weights/presets/audio cũ giữ nguyên, native/container baseline phục hồi. Không reading-rule/model/reference/download/training/ASR/CORE/Brave/Vault/database/Docker mutation; chỉ đọc tài liệu công khai và thêm benchmark/test/báo cáo.

Python/English-US và bilingual identity còn mở; API pronunciation/date/clauses/VI accepted-scope giữ nguyên, APIbuzz/timbre không tự đóng. D60 deferred; ADR155workflow chưa duyệt/chưa chạy, rights/no-speech/physical4second/model/voice/product/D90release vẫn mở.


## Same-voice US term comparison — 2026-11-04

[ADR160 actual result and paired listening pages](D74_US_TERMS_COMPARISON_RESULT.md): owner explicitly continues PythonUS plus other words. Six exact sentences/two retained voices; change only Python US vowel, GitHub whole-word dictionary form and server rhotic hypothesis. Docker/browser/database input phones unchanged, accepted API function and clause path retained. Shared min(original) frame budgets never increased; GitHub fresh baseline allowance conservatively reduced140→136.

16newTTS/16chunks/EOS/exit0/no retry +4oldPythonbaselines +4sharedunchangedcontrols =24logicalobservations/12pairs,20actualplayers split into two voice pages. Eight changed pairs differ in waveform; no acoustic PASS inferred. Four fresh GitHub/server pairs match measuredspeaker/reference hashes; oldPython provenance bound to retained source/audio without retrospective measurements.295scoped software PASS5.31s/RuffPASS;4newsource/test,33oldresearch/750application/210protected/SDK/model/audio preserved,baseline restored. No model/reference/training/app/config/ASR/CORE/Brave changes.

VOICE-ENGLISH-READING-001/VOICE-BILINGUAL-IDENTITY-001 now have a real paired word panel; en-US pronunciation/accent, perceived voice similarity, naturalness and API inside new mixed audio await listening. Accepted prior API/VI/date/clauses remain scoped, XI review pending. No model/voice/default/policy adoption; D60deferred/ADR155workflowunapproved, physical4second/rights/no-speech/product/D90releaseopen;5889full historical.
