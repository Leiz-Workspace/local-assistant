# D74 — Bước tiếp theo sau khi dừng tinh chỉnh phát âm

**Mục đích:** Xếp công việc kế tiếp theo kết quả thật, sau khi chủ dự án dừng vòng sửa Ngọc Huyền. Đây là kế hoạch chuẩn bị; chưa cho phép chạy native hoặc thay lựa chọn model.

## Trạng thái đã chốt

[Phản hồi mới](evidence/d74-ngoc-api-owner-stop.json): API Ngọc Huyền tốt hơn nhưng vẫn đọc sai; dừng tinh chỉnh phần này. Không coi candidate ADR163 là bản sửa thành công hoặc tự đưa vào sản phẩm. Giữ mọi audio/input/kết quả. Trúc Ly đã đủ ổn trong phạm vi được nghe, có hạn chế phụ âm cuối tiếng Anh; vòng tinh chỉnh cũng đã dừng. Chưa chốt model/voice/default triển khai.

D74 vẫn OPEN. Microphone Brave/PC capture/playback smoke đã được chủ dự án xác nhận trong phạm vi ghi nhận; chưa phải recorder→ASR→CORE→TTS sản phẩm. Các số TTS riêng không chứng minh chờ tối đa4giây.

## Công việc ưu tiên kế tiếp

**VOICE-LATENCY-AC-001 / D74 workflow recovery — P1.** Kiểm luồng nhận dạng giọng nói → CORE tạo câu trả lời → TTS, xác minh lời trả lời hoàn chỉnh và đo phần nào gây chờ. Ngừng các lượt thử phát âm bổ sung.

1. Rà soát caller đã sửa, packet/corpus và chính sách đọc đã được chấp nhận. [ADR155](ADR/155-proposed-workflow-recovery-after-caller-metadata-failure.md) khóa kế hoạch2ASR×2TTS×2trạng thái×6nguồn=48slot, lane Turbo Trúc Ly gốc và Piper VI control. Nó chưa mô tả việc ghép toàn bộ renderer/US-term/API nghiên cứu mới vào phản hồi CORE tùy ý. Không âm thầm chạy bản gốc rồi gọi đó là bản đọc đã được nghe; không mở whitelist của các study đã đóng băng. Cần xác định adapter/lifecycle nào đã có và khoảng trống tích hợp, thêm test hoặc ADR riêng nếu thay cách kết hợp.
2. Chuẩn bị bản kế hoạch cụ thể cho caller/renderer đã kiểm thử, nguồn/phạm vi, request/resource limits và rollback; giữ nguyên các model/lane đã thỏa thuận. Trúc Ly chỉ là lane nghiên cứu sẵn trong kế hoạch cũ, không phải lựa chọn sản phẩm mới; Ngọc Huyền có thể giữ pending tùy chọn, không kéo theo vòng tuning tiếp. Không tự đổi ASR, streaming, context, cap hoặc GPU để đạt4giây.
3. Sau khi phạm vi native phù hợp được duyệt, chạy đúng lượt hữu hạn đã đóng băng. Giữ riêng6workflow slot cũ software-invalid/42chưa gọi; không gộp score với lượt mới. Ghi số lỗi, transcript, complete native audio, cold/warm, ASR/CORE/TTS stages, RAM và cleanup. Thử silence/noise/missing speech theo corpus đã duyệt; không biến test phần mềm thành chứng nhận không hallucinate.
4. Phép đo CLI submission→complete PCM là proxy kỹ thuật. Phải nối endpoint/auth/retention và playback phù hợp trước khi xác nhận submission→first-audible trên Brave/PC≤4giây. Kiểm Stop/Hủy trong luồng thật và giữ bộ microphone smoke đã PASS. Không đánh PASS4giây từ TTS-only hoặc từ PCM có sẵn.

## Dependency, effort, rủi ro và giới hạn hiện tại

Dependency: kết quả nghe đã lưu, source/SDK/assets hiện có, caller metadata fix, thiết kế adapter cho phản hồi CORE, bộ test và phê duyệt phạm vi native. Effort một milestone kiểm tra/tích hợp/test chuẩn bị; một milestone benchmark riêng (kế hoạch ADR155 gốc tối đa60phút), rồi đo thiết bị khi có luồng sản phẩm phù hợp. Chưa hứa mọi việc xong trong một lượt.

Rủi ro có căn cứ: bản benchmark gốc chưa chứa reading policy mới, các study giới hạn câu/preset, ASR đã có độ trễ và hallucination trên negative, PCM không đồng nghĩa đã phát tiếng, co-residency/cancel/cleanup và nhầm chất lượng nghiên cứu với sản phẩm. Giữ immutable first outcomes, finite budgets và rollback dừng/join riêng workers, xác minh baseline/source; không chạm shared services/weights/Vault/database.

ADR155 yêu cầu **“Request one new explicit approval for one replacement48-slot workflow campaign only.”** Chủ dự án trước đó chọn “Chờ nghe24clip”; các nhận xét nghe và yêu cầu dừng tinh chỉnh không tự phê duyệt48lượt native. Tài liệu này chỉ chuẩn bị bước tiếp theo, không gỡ khóa entry point hoặc sửa kế hoạch/hash cũ.

D60 tiếp tục deferred theo chủ dự án. Rights/model/default/product/D90release và4giây thật còn mở; không chuyển ngày hoặc ghi hoàn tất chỉ vì dừng tinh chỉnh phát âm.
