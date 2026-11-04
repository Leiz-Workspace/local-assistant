# D74 — Reading policy nối vào luồng thoại thử nghiệm

**Mục đích:** Báo cáo phần tích hợp phần mềm theo [ADR164](ADR/164-reading-policy-bridge-for-voice-workflows.md), sau chỉ dẫn “Làm đi”. Giữ nguyên VoicePipeline, các model và cấu hình sản phẩm.

**Trạng thái: PHẦN NỐI VÀ KIỂM THỬ PHẦN MỀM ĐÃ XÁC MINH; CHƯA ĐO WORKFLOW BẰNG MODEL THẬT.** [Receipt nguồn/kết quả](evidence/d74-workflow-reading-preparation.json).

## Thay đổi

Thêm bốn module nghiên cứu và hai file test; không sửa750application/210protected/46research cũ. Lớp ReadingTTS giữ nguyên câu trả lời CORE để hiển thị, tạo bản speech riêng bằng renderer English/date/clauses đã được nghe. Nó kiểm VoiceSpeech của backend phải đúng owner/model/ngôn ngữ/hash của bản speech và PCM hoàn chỉnh trước khi trả kết quả gắn lại với câu trả lời gốc. Audit bắt buộc lưu hai hash và các edit đã băm; sai hash, lỗi audit, timeout hoặc hủy không được công bố thành công. Không chỉ đổi hash rồi bỏ qua kiểm nguồn.

ReadingResearchTTS dùng lại bộ đọc native WAV và chuyển mono16k PCM gốc; kiểm worker đúng profile/Trúc Ly và actual input/plans/speaker-reference/frame/EOS/chunk hashes/token-roundtrip trước chuyển audio. Hỗ trợ worker cold hoặc resident qua factory được caller kiểm soát; không tự tải hay chọn model. compose_workflow dùng VoicePipeline gốc, hai ASR lane đã có và CORE/Fast512; Piper control không đổi.

Native adapter không còn whitelist câu khảo sát. Nó dùng nguyên API stress có khoảng trắng và ba target Python/GitHub/server của bản Trúc Ly, hỗ trợ0hoặc nhiều lần xuất hiện được đối chiếu lexical/phone counts. Không sửa I hoặc từ lạ, không dùng compact Ngọc Huyền chưa đạt. Tất cả chunk/phone/token được kiểm trước lần generation đầu, caps=min(original,reading,300), giữ referenceON/seed/sampling/chia-ghép gốc. Từ đích trong code/URL/identifier được bảo vệ và SDK-control do caller nhập bị từ chối rõ ràng thay vì phỏng đoán. Một số CORE response vẫn có thể bị từ chối bởi mapping/chunk/token bounds; đây không phải cam kết đọc đúng mọi text.

## Kiểm chứng thực tế

58test mới PASS0,85s; tổng386related PASS/0FAIL/0ERROR/0SKIP6,09s, Ruff E4,E7,E9,F/format/descriptions PASS. Tests đi qua VoicePipeline thật: original answer/source clock, rendered hash, wrong owner/model/language/hash/audio/completion, no-speech, audit failure, busy, Stop/Cancel/shutdown, repeated cancellation và backend/audit nuốt timeout. Gateway gốc được chạy với HTTP mock để xác minh preset fallback/Fast512/context32K. Hai control cold/resident dùng sine-wave do test tạo để chạy native writer/reader và chuyển PCM thật; không phải model inference/giọng nghe hoặc playback trên loa.

Probe bằng SDK/tokenizer gốc, không mount weights và không gọi model:20/20case lập kế hoạch,0refused/0unknown. Trong đó10control Trúc Ly cũ khớp tuyệt đối rendered input/chunks/gaps/phones/shared caps;10câu CORE-style mới gồm API/Python lặp, các thuật ngữ cùng câu, ngày/giờ, câu hỏi và từ gần giống. Không sinh thêm clip hoặc yêu cầu nghe lại. Probe wall0,237s/peak sampledRSS RAM41,59MiB, exit0/joined/baseline giữ nguyên. Đây là frontend proof, không phải số đo latency hay acoustic acceptance.

Source probe được giữ nguyên snapshot sáu file tại thời điểm chạy. Sau probe chỉ bổ sung hai test PCM cold/resident trong file test bridge; cả bốn module thực thi probe/nối vẫn nguyên hash. Final snapshot/ZIP sáu file khớp386test và receipt. [Full version code/tests](../data/backups/d74-vi-approved-campaign-20261103/workflow-reading-preparation-first/full-code.zip).

46research cũ/750application/210protected/4295SDKentries/weights/presets/audio và native/container baseline được xác minh. RootAGENTS/private devlogprefix giữ nguyên/loại khỏi commit.0newASR/CORE/TTS/provider/download/service/config/model/Vault/database/Docker actions trong bước chuẩn bị. Full5889/750 vẫn là snapshot lịch sử, không phải full regression mới.

## Bước kế tiếp

Bước1 của [kế hoạch workflow](D74_NEXT_WORKFLOW_VALIDATION.md) đã có implementation/software proof. Cần một operator/scope hữu hạn dùng đúng bridge/native profile trước khi đo48case thật; ADR155 cũ giữ nguyên/không tự mở khóa và không tráo bản raw thành reading policy mới. Sau benchmark, submission→completePCM vẫn là proxy; first-audible4giây cần đo trên luồng sản phẩm/Brave-PC sau endpoint/auth/retention/playback phù hợp. Không lấy thời gian test/probe/TTS riêng làm PASS.

Trúc Ly accepted-with-limitations/refinement stopped và Ngọc Huyền improved-but-incorrect/refinement stopped giữ nguyên. D60deferred; D74model/default/rights/no-speech/device/product/D90release còn mở.
