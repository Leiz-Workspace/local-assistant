# Voice — Yêu cầu ngôn ngữ, chất giọng và thời gian chờ

**Mục đích:** Ghi đúng yêu cầu chủ dự án để định hướng D74 và backlog voice, tách biệt yêu cầu sản phẩm với việc chọn hoặc triển khai model.

**Ngày:** 2026-11-03, Asia/Ho_Chi_Minh. **Trạng thái:** REQUIREMENTS RECORDED / LATENCY PENDING. [Phát biểu gốc và các trường chưa chốt](evidence/d74-voice-requirements-20261103.json).

## Yêu cầu đã xác nhận

| Nội dung | Yêu cầu và phạm vi |
|---|---|
| Mục tiêu ngôn ngữ | Có cả tiếng Việt và tiếng Anh |
| Ưu tiên triển khai hiện tại | **Tiếng Việt trước** |
| Giọng tiếng Việt | **Nữ, miền Bắc**; độ tự nhiên cần được chủ dự án nghe và chấp nhận |
| Tiếng Anh | Giữ trong mục tiêu sản phẩm; chưa chốt lịch/release hoặc voice EN. Không tự bỏ tiếng Anh hoặc xếp sang một bản cụ thể |
| Thêm ngôn ngữ tùy biến | **PENDING cho bản sau**; chưa chỉ định ngôn ngữ, số phiên bản, ngày phát triển hoặc model |
| Thời gian chờ tối đa | **PENDING** vì chủ dự án chưa rõ ý nghĩa; chưa có con số được chấp nhận |

Các trường ngôn ngữ/giới tính/vùng giọng ở đây là tiêu chí đánh giá và thiết kế. Chúng không phải cấu hình model đã áp dụng, phê duyệt voice cloning, lựa chọn model mới hoặc bằng chứng một checkpoint đáp ứng được yêu cầu.

## Thời gian chờ nghĩa là gì?

Trong trải nghiệm trò chuyện, đó là khoảng thời gian từ lúc bạn **gửi câu hỏi đã nói** đến lúc **bắt đầu nghe được câu trả lời**. Ví dụ minh họa: bạn gửi câu hỏi, 4 giây sau bắt đầu nghe câu trả lời thì thời gian chờ là 4 giây. Con số này chỉ giúp giải thích, **không phải kết quả đo hoặc giới hạn đã chốt**. Độ dài câu trả lời khi phát hết là một đại lượng khác.

Khoảng chờ có thể gồm nhận dạng giọng nói, tạo câu trả lời, tổng hợp giọng và chuyển audio tới thiết bị phát. Thời gian bạn đang nói hoặc đang cân nhắc trước khi bấm gửi không nên tính thành thời gian xử lý của hệ thống.

Luồng D72 hiện có là ví dụ CLI được đệm toàn bộ: ghi thời gian từ submission tới có đủ PCM trả lời, **chưa đo thời điểm loa bắt đầu phát trong một sản phẩm người dùng**. Sáu số đo khoảng 8–49 giây được giữ riêng ở [bảng D74](D74_VOICE_DECISION_BRIEF.md); không tráo chúng thành số đo first-audible, p95 hoặc cam kết cho giọng nữ miền Bắc chưa được đánh giá. Recorder D71 hiện chỉ thu/nghe lại và không có gửi câu hỏi tới model.

Chủ dự án chưa cần chọn một con số từ ví dụ. Ghi pending để giải thích/đối chiếu trải nghiệm và duyệt mục tiêu sau. Không tự đặt 4/5/10 giây làm AC, không dùng timeout kỹ thuật hiện có làm mức chờ được chấp nhận và không sửa bất kỳ timeout/resource cap nào.

## Tác động tới D74

Phương án cần xét trước nay là **VI giọng nữ miền Bắc**, không phải ưu tiên triển khai EN. Qwen Ryan vẫn chỉ là một ứng viên EN đã được nghe; kết quả EN không chứng minh phù hợp yêu cầu VI. VI-Auto đã có lỗi và Piper VI voice đã bị chủ dự án nhận xét không tự nhiên/không thích tông. Chưa có bằng chứng một voice đã đánh giá đáp ứng đồng thời tiếng Việt, nữ, miền Bắc và độ tự nhiên mong muốn; không tự gán giới tính/vùng giọng hoặc đánh dấu model đạt.

Bước chuẩn bị tiếp theo có thể đối chiếu metadata/provenance và bằng chứng của các ứng viên đã thống nhất với tiêu chí mới, lập protocol/đề xuất cụ thể cho khoảng trống còn lại. Một đề xuất tải/đổi model hoặc voice phải có benchmark, hiệu năng/tài nguyên, migration, rollback và chủ dự án duyệt trước khi thực hiện. Tài liệu này không phê duyệt một lượt inference, download hoặc thử nghiệm mới.

## Backlog và đánh giá trước khi xếp lịch

| Task | Ưu tiên / trạng thái | Dependency | Effort | Rủi ro |
|---|---|---|---|---|
| VOICE-VI-NORTH-FEMALE-001 | P1; ưu tiên thiết kế/đánh giá trước kích hoạt VI, chưa có model được chọn | Metadata/rights của ứng viên, benchmark D70/D72, protocol và approval cụ thể khi cần thay đổi | Một milestone đối chiếu/proposal; effort chạy/triển khai chưa ước lượng khi chưa có phương án | Voice không đúng vùng/giới tính/cảm nhận, sai dấu/phát âm, thiếu quyền hoặc vượt tài nguyên |
| VOICE-EN-001 | P1 trong mục tiêu voice; sau ưu tiên VI, lịch/release chưa chốt | Bằng chứng EN đã có, quyết định chất giọng và độ trễ/rights | Một milestone quyết định trước khi ước lượng tích hợp | Tự coi EN benchmark là sản phẩm hoặc bỏ yêu cầu EN khi ưu tiên VI |
| VOICE-LANGUAGE-CUSTOM-001 | P2; **PENDING LATER VERSION**, chưa xếp ngày/phiên bản | Ngôn ngữ ASR/TTS thực sự hỗ trợ, UI chọn language/voice, provenance/rights và thiết kế mapping được duyệt | Một milestone thiết kế; implementation/benchmark chưa ước lượng | Nhầm Auto với hỗ trợ chính thức, silent fallback, sai voice/ngôn ngữ hoặc để input tự tải/chọn model |
| VOICE-LATENCY-AC-001 | P1 trước nghiệm thu hiệu năng; pending giải thích/quyết định | Phạm vi input→first-audible và input→complete-audio được định nghĩa, bằng chứng phù hợp workload | Một milestone định nghĩa/duyệt; đo thêm chỉ khi được scope riêng | Ép con số ví dụ thành AC, nhầm timeout với UX, che load/cache/device/concurrency |

Đây là phân loại backlog, không tự cấp quyền triển khai hay thêm phase/ngày. Nếu thiết kế chọn ngôn ngữ, streaming hoặc runtime làm thay đổi kiến trúc, phải có ADR riêng trước khi áp dụng.

## Những bằng chứng giữ nguyên

D70 nghe 24/24 và bộ capture/playback microphone người dùng đã đạt trong phạm vi đã báo cáo. Giữ mọi audio/nhãn/kết quả chưa đạt, lựa chọn model/config hiện có và D60 đang chờ. D74 sản phẩm và D90 release vẫn mở. Cập nhật yêu cầu này chỉ sửa tài liệu/thêm evidence, không sửa source, download, inference, endpoint, Vault, Docker hoặc database.
