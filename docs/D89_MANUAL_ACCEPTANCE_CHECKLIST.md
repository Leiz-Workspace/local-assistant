# D89 — Phiếu nghiệm thu và đối chiếu workflow

**Mục đích:** Gom bằng chứng kỹ thuật và các kiểm tra người dùng cần làm sau, không bắt chủ dự án chỉnh JSON hoặc chấm lại benchmark.

**Trạng thái:** ENGINEERING WORKFLOW EVIDENCE CHECKED / OWNER ACCEPTANCE PENDING. Full snapshot mới nhất đã hoàn tất5596PASS/0FAIL/0ERROR/0SKIP/1760.86s,719files giữ nguyên, audit sau kiểm thử đạt với delta timestamp quota đã ghi rõ. Các bằng chứng kỹ thuật dưới đây không tự trở thành nghiệm thu thủ công hay quyền chọn/triển khai model. Chưa có xác nhận nghe/thiết bị của chủ dự án.

## Mở phần nghe khi bạn rảnh

1. Mở [trang24WAV gốc](../data/backups/d89-native-tts-listening/index.html). Chỉ cần chép riêng file HTML này về máy có loa/tai nghe; đủ audio đã nhúng, không cần mạng/server/key.
2. Nghe hết từng mục. Ghi mã mục và nhận xét phát âm, nhịp/ngắt, lỗi âm thanh, độ tự nhiên/mức chắc chắn vào [phiếu đã tạo](D70_MANUAL_LISTENING_RESULTS.pending.md), hoặc gửi nhận xét trong chat sau. Không cần biết JSON, không bắt buộc MOS; có thể chia nhiều buổi.
3. Nếu chưa nghe/không hiểu đủ ngôn ngữ, giữ CHƯA TEST/chưa chắc. Không mặc định QwenVI-Auto là hỗ trợ tiếng Việt chính thức; sáu explicit-VI refusals vẫn ở báo cáo.

Trang mới giữ nguyên byte WAV. Kiểm tra hash và browser metadata24/24đã hoàn tất, **không phải đã nghe24/24**. [Hướng dẫn đầy đủ](D70_MANUAL_LISTENING_TEST.md); packet nhãn gốc vẫn null/unlistened.

## Ít nhất10workflow đại diện để đối chiếu

| # | Workflow | Bằng chứng kỹ thuật / giới hạn |
|---|---|---|
| 1 | Text CORE có nguồn và model identity | D80actual CORE/source citation; D83usage/stream timing. Không thay model |
| 2 | Authenticated conversation/history/replay và owner isolation | Existing HTTP/PostgreSQL suites trong D87; không coi unowned history là dữ liệu được phép xem |
| 3 | Upload/read/replace/delete theo owner/hash/quota | Existing actual file/HTTP/native fault suites; D87đối chiếu toàn bộ |
| 4 | PDF/DOCX/XLSXtext/table/cell/source quotes | Existing native parsing/field provenance suites; scope OCR/imperfect quality giữ nguyên |
| 5 | Ingestion/retrieval/chunk/source deletion | Existing actual Qwen/Qdrant integration controls; D24E5rollback giữ nguyên, không production cutover |
| 6 | Read code → exact proposal → explicit approval → atomic patch → separate approved check | D79actual disposable patch/read/pinned Ruff and existing workflow HTTP/TCPtests; không cấp approval thật cho code do model tự nói |
| 7 | Web source/canonical/injection boundaries | D81workflow gốc hiện PASS3giá trị/3trích dẫn chính xác qua adapter tùy chọn; các FAIL lịch sử vẫn giữ. Không phải chứng nhận live-search; Brave vẫn qualified/degraded |
| 8 | Image/chart/document screenshot | D61–D63native existing-model evidence/source association/abstention; no universal OCRaccuracy claim |
| 9 | Video frames/timestamps/transcript composition | D64–D66native FFmpeg/source clocks; supplied-reference and sparse-frame limits remain |
|10| Explicit recording/stop/Escape/hidden/TTL/local storage | D71/D73/D86actual fake-device browser controls; **mic vật lý/thiết bị người dùng chưa test** |
|11| ASR/VAD/TTSbuffered voice paths | D68–D72actual CPU candidates/sixcompatible paths; **nghe D70/default/license/no-speech policy còn mở** |
|12| Plan pause/crash/explicit resume/action uncertainty | D78actual subprocess crash/recovery; source/attempt/time budgets retained, không tự chạy lại write |
|13| Backup/restore và failure cleanup | D84actual12table/ACLrestore plus owned vector/blob/config canaries; D85actual private resource faults/read overload. Không off-host/hostOOM/SLOclaim |
|14| Memory consent/revoke/owner/retention | Existing actual DB/HTTPmemory controls trong D87; không tự học từ conversation hoặc phục hồi consent cũ |

Kết quả D87thực tế đã được lưu tại [full evidence](evidence/d87-current-full-acceptance.json); không điền nghiệm thu người dùng chỉ từ bảng này. Các test do máy chạy trên fixture là kiểm thử kỹ thuật, không giả chữ ký/nghe/nghiệm thu người dùng.

## Kiểm tra thiết bị thực tế còn chờ

- [ ] Tôi đã nghe đủ24WAV và lưu nhận xét theo từng mã, có danh tính/ngày/thiết bị; bất định/điểm kém được giữ nguyên.
- [ ] Trên trình duyệt/thiết bị của tôi, microphone chỉ mở sau bấm Start+permission; Stop/Escape/chuyển trang dừng chỉ báo mic; xóa/TTLthu hồi preview. Xem [runbook ghi âm](D71_EXPLICIT_RECORDING.md).
- [ ] Tôi đã xem phạm vi/giới hạn model, license, ASR/VAD/no-speech và đề xuất lựa chọn trước khi phê duyệt triển khai. Nghe xong không tự phê duyệt model.
- [ ] Tôi đã duyệt phạm vi release thực tế và các known limitations; chưa tạo tag/deployv1.0 chỉ vì các mục kỹ thuật đã có code.

Chủ dự án đã cho phép để phần nghe sau và tiếp tục công việc độc lập. Phiếu này giữ quyết định đó; không yêu cầu phản hồi ngay, không đổi AC hoặc tự gán người đánh giá.
