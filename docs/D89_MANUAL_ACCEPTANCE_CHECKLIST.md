# D89 — Phiếu nghiệm thu và đối chiếu workflow

**Mục đích:** Gom bằng chứng kỹ thuật và các kiểm tra người dùng cần làm sau, không bắt chủ dự án chỉnh JSON hoặc chấm lại benchmark.

**Trạng thái:** ENGINEERING WORKFLOW EVIDENCE CHECKED / OWNER ACCEPTANCE PENDING. Full snapshot lúc chuẩn bị phiếu đã hoàn tất5674PASS/0FAIL/0ERROR/0SKIP/1798.59s,728files giữ nguyên (snapshot hiện tại xem [release status](RELEASE_CANDIDATE_STATUS.md)), audit sau kiểm thử đạt với delta timestamp quota đã ghi rõ. Các bằng chứng kỹ thuật dưới đây không tự trở thành nghiệm thu thủ công hay quyền chọn/triển khai model. Đã có [xác nhận nghe đủ 24/24 bằng loa và nhận xét](D70_OWNER_LISTENING_20261103.md) ngày 2026-11-03; đã có [microphone thật cơ bản PASS do chủ dự án báo cáo](D74_PHYSICAL_MIC_CHECK.md) trên Brave/PC; ba tình huống mở trang/từ chối quyền/giới hạn30giây cũng đã PASS theo follow-up. Bộ smoke thu âm/nghe lại hoàn tất; preview/delete/TTL, các chi tiết chưa nêu và nghiệm thu sản phẩm/release vẫn riêng.

## Đối chiếu phần nghe đã hoàn tất

Chủ dự án đã làm xong bước nghe ngày báo cáo 2026-11-03; các bước dưới đây là hướng dẫn tham khảo, không yêu cầu chấm lại.

1. Mở [trang24WAV gốc](../data/backups/d89-native-tts-listening/index.html). Chỉ cần chép riêng file HTML này về máy có loa/tai nghe; đủ audio đã nhúng, không cần mạng/server/key.
2. Nghe hết từng mục. Ghi mã mục và nhận xét phát âm, nhịp/ngắt, lỗi âm thanh, độ tự nhiên/mức chắc chắn vào [phiếu đã tạo](D70_MANUAL_LISTENING_RESULTS.pending.md), hoặc gửi nhận xét trong chat sau. Không cần biết JSON, không bắt buộc MOS; có thể chia nhiều buổi.
3. Nếu chưa nghe/không hiểu đủ ngôn ngữ, giữ CHƯA TEST/chưa chắc. Không mặc định QwenVI-Auto là hỗ trợ tiếng Việt chính thức; sáu explicit-VI refusals vẫn ở báo cáo.

Trang mới giữ nguyên byte WAV. Kiểm tra hash và browser metadata24/24là bằng chứng chuẩn bị lịch sử; nay chủ dự án đã xác nhận nghe hết/lặp lại24/24bằng loa, lưu riêng trong [kết quả mới](D70_OWNER_LISTENING_20261103.md). [Hướng dẫn đầy đủ](D70_MANUAL_LISTENING_TEST.md); packet nhãn gốc vẫn null/unlistened.

## Ít nhất10workflow đại diện để đối chiếu

| # | Workflow | Bằng chứng kỹ thuật / giới hạn |
|---|---|---|
| 1 | Text CORE có nguồn và model identity | D80actual CORE/source citation; D83usage/stream timing. Không thay model |
| 2 | Authenticated conversation/history/replay và owner isolation | Existing HTTP/PostgreSQL suites trong D87; không coi unowned history là dữ liệu được phép xem |
| 3 | Upload/read/replace/delete theo owner/hash/quota | Existing actual file/HTTP/native fault suites; D87đối chiếu toàn bộ |
| 4 | PDF/DOCX/XLSXtext/table/cell/source quotes | Existing native parsing/field provenance suites; scope OCR/imperfect quality giữ nguyên |
| 5 | Ingestion/retrieval/chunk/source deletion | Existing actual Qwen/Qdrant integration controls; D24E5rollback giữ nguyên, không production cutover |
| 6 | Read code → exact proposal → explicit approval → atomic patch → separate approved check | D79actual disposable patch/read/pinned Ruff and existing workflow HTTP/TCPtests; không cấp approval thật cho code do model tự nói |
| 7 | Web source/canonical/injection boundaries | D81workflow gốc hiện PASS3giá trị/3trích dẫn chính xác qua adapter tùy chọn; các FAIL lịch sử vẫn giữ. Không phải chứng nhận live-search; Brave có lượt mới trả kết quả; biến thể theo liên kết nguồn đã kiểm chứng riêng, gate direct-result gốc vẫn FAIL |
| 8 | Image/chart/document screenshot | D61–D63native existing-model evidence/source association/abstention; no universal OCRaccuracy claim |
| 9 | Video frames/timestamps/transcript composition | D64–D66native FFmpeg/source clocks; supplied-reference and sparse-frame limits remain |
|10| Explicit recording/stop/Escape/hidden/TTL/local storage | D71/D73/D86actual fake-device browser controls; [owner physical capture/playback smoke PASS](D74_PHYSICAL_MIC_CHECK.md), preview/delete/TTL và chi tiết lifecycle chưa báo cáo riêng |
|11| ASR/VAD/TTSbuffered voice paths | D68–D72actual CPU candidates/sixcompatible paths; D70owner listening24/24đã ghi với hạn chế chất lượng; **default/license/no-speech/product policy còn mở** |
|12| Plan pause/crash/explicit resume/action uncertainty | D78actual subprocess crash/recovery; source/attempt/time budgets retained, không tự chạy lại write |
|13| Backup/restore và failure cleanup | D84actual12table/ACLrestore plus owned vector/blob/config canaries; D85actual private resource faults/read overload. Không off-host/hostOOM/SLOclaim |
|14| Memory consent/revoke/owner/retention | Existing actual DB/HTTPmemory controls trong D87; không tự học từ conversation hoặc phục hồi consent cũ |

Kết quả D87thực tế đã được lưu tại [full evidence](evidence/ce003-full-acceptance.json); không điền nghiệm thu người dùng chỉ từ bảng này. Các test do máy chạy trên fixture là kiểm thử kỹ thuật, không giả chữ ký/nghe/nghiệm thu người dùng.

## Kết quả kiểm tra thực tế và phần còn chờ

- [x] Chủ dự án đã nghe đủ24WAV, lưu nhận xét và xác nhận nghe hết/lặp lại bằng loa: [D70report](D70_OWNER_LISTENING_20261103.md). Ngày nhận báo cáo đã ghi; metadata chưa cung cấp giữ null, không tự suy ra.
- [x] Bộ capture/playback smoke đã yêu cầu: owner báo cáo bản ghi rõ/đủ/không rè; Dừng/Hủy/Escape/chuyển tab tắt thu; mở/reload không tự thu; từ chối quyền hiện lỗi/không thu; giới hạn30giây tự dừng. [Evidence tổng hợp](evidence/d74-owner-physical-mic-completion-20261103.json).
- [ ] Các thuộc tính ngoài smoke đã báo cáo: xóa/TTLthu hồi preview và các chi tiết lifecycle chưa nêu. Giữ riêng, không mặc định đã test từ báo cáo tắt thu. Xem [runbook ghi âm](D71_EXPLICIT_RECORDING.md).
- [ ] Tôi đã xem phạm vi/giới hạn model, license, ASR/VAD/no-speech và đề xuất lựa chọn trước khi phê duyệt triển khai. Nghe xong không tự phê duyệt model.
- [ ] Tôi đã duyệt phạm vi release thực tế và các known limitations; chưa tạo tag/deployv1.0 chỉ vì các mục kỹ thuật đã có code.

Chủ dự án đã cho phép để phần nghe sau và tiếp tục công việc độc lập. Phiếu này giữ quyết định đó; không yêu cầu phản hồi ngay, không đổi AC hoặc tự gán người đánh giá.
