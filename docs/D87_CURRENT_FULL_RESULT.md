# D87 — Full regression trên source hiện tại

**Mục đích:** Ghi kết quả full suite ngày 2026-10-27, phạm vi source, kiểm tra bảo toàn sau test và các gate còn mở.

**Trạng thái: VERIFIED — full software regression.** [Terminal và audit receipt](evidence/d87-current-20261027-full-acceptance.json), [preflight trước lượt chạy](evidence/d87-current-20261027-preflight.json).

| Phạm vi | Kết quả thực tế |
|---|---|
| Toàn bộ `pytest tests` | **5.759 PASS / 0 FAIL / 0 ERROR / 0 SKIP**, exit 0 |
| Thời gian pytest | **1.870,65 giây**; wrapper 1.872,69 giây |
| Source/config/test snapshot | **732 file**, inventory và SHA giữ nguyên trước/sau |
| So với full cũ | Toàn bộ 728 file của full 5.674 vẫn khớp byte; bốn file adapter/test D14 bổ sung đã nằm trong full mới |
| Cảnh báo | Một warning cố ý từ fixture ZIP có entry trùng `piper/voice.py`; test từ chối archive này PASS |
| Benchmark controls riêng | 183 PASS / 2,26 giây; không cộng vào 5.759 |
| Operator controls riêng | Supervisor/runner/lifecycle 71 PASS; audit policy 46 PASS; delivery policy ban đầu32 PASS, cuối43 PASS; các scope có overlap, không cộng thành một full suite |

Lượt chạy bắt đầu 11:29:08 và kết thúc 12:00:21 theo Asia/Ho_Chi_Minh. Source ứng dụng không cần sửa. Không tải hoặc thay model, thay default/API/config, đổi provider, schema, ACL hay collection. Các live integration test dùng runtime và credential hiện có; kết quả software regression không ghi đè điểm benchmark đầu tiên.

## Điều kiện chạy và cleanup

Sau reboot, máy không có native worker và Vault đã initialized nhưng sealed. Operator unseal đúng Vault hiện có bằng bootstrap material đã lưu, chỉ đọc credential vào bộ nhớ; không init/rotate hoặc sửa policy. Vault được giữ unsealed và thay đổi trạng thái này được ghi trong audit.

Supervisor dùng đúng CORE/model/projector/context hiện có tại cổng 8080, fixture umask 0022, log/metadata riêng tư và một process group sở hữu riêng. CORE exit 0, đã reap, guard failure null; full runner cũng exit 0 và đã join. Sau cleanup, cùng boot, cùng 15 container identities/images/ports và native=0 như baseline đầu lượt chạy.

Peak RSS của toàn CORE worker là 8.081.632 KiB, khoảng **7,71 GiB RAM**; sampled peak VRAM **8.910 MiB**. Đây là hai phép đo khác nhau, không phải virtual address-space cap hoặc tổng bộ nhớ cả máy.

Lỗi gọi trực tiếp private script thiếu import `scripts` được giữ trong log. Lỗi xảy ra trước khi có worker hoặc thư mục full suite. Cách gọi được sửa bằng runpy từ `ai/`, không sửa application source hoặc chạy lại một full đã thất bại. [Protocol và lệnh thực thi](D87_FULL_REGRESSION_PROTOCOL.md#current-reboot-aware-run--2026-10-27).

## Kiểm tra dữ liệu sau suite

Đối chiếu read-only với snapshot chụp trước test: schema 0006, security/owners/ACL và 11 bảng khác giữ nguyên. Chỉ `assistant.file_global_usage.updated_at` thay đổi do upload/delete test; complete singleton row vẫn 0 byte, 0 file, 0 active upload. Vì vậy **strict all-row equality=False**, còn qualified preservation=True. Không restore timestamp, chạy restore probe hoặc chuẩn hóa để giấu thay đổi.

Authenticated Qdrant inventory sau test rỗng. Không có authenticated collection snapshot cùng boot trước suite, nên receipt chỉ khẳng định inventory sau test; không bịa một phép so sánh trước/sau. Restore probe count=0, không còn app connection/pending inference khi audit. 916/917 older protected files khớp byte; ngoại lệ duy nhất là thay đổi tài liệu MODEL_REGISTRY đã được duyệt từ trước. Toàn bộ 176 original inputs và worksheet D70 chưa nghe giữ nguyên.

## Phạm vi hoàn tất và việc tiếp theo

D87 current-source software refresh hoàn tất. D14 selected semantic path vẫn VERIFIED_LOCAL_OPT_IN trên fresh 42/42 mỗi profile; mọi điểm FAIL/composite cũ được giữ nguyên. Full software PASS không tự phê duyệt tích hợp API/default hoặc chất lượng coding/web rộng hơn.

D70 nghe thực tế vẫn **0/24 owner-deferred**; [hướng dẫn nghe](D70_MANUAL_LISTENING_TEST.md) đã sẵn sàng. D74 voice/model/license/no-speech, D81 product integration, D86/D89 product/device acceptance, các gate D88 liên quan model/license và D90 release vẫn mở theo [ledger](OUTSTANDING_WORK_STATUS.md). Không push, tag, deploy hoặc tuyên bố toàn dự án hoàn thành.

Root `AGENTS.md` untracked và dòng IDE riêng đầu devlog được giữ nguyên, ngoài commit và ZIP D87. Gói đầy đủ sau commit: `data/backups/local-assistant-d87-20261027-full-files.zip`, kèm receipt và manifest. Gói giữ các artifact lịch sử theo SHA, full phiên bản file Git và operator/test/log được chọn rõ; không chứa weights, SDK, secret, dump hay checkpoint.

Đóng gói phát hiện thêm sáu CE003 latest pointers do `tests/test_coding_feedback_oracles.py` cập nhật trong full suite. Đã đối chiếu từng target summary/SHA: frozen oracle PASS, hai native check, 0 model attempt; đây không phải thay đổi first model score. Builder đầu từ chối trước khi tạo ZIP và log được giữ. Policy cuối chỉ chấp nhận đúng12CE002+6CE003pointer, giữ byte archive cũ và ghi riêng SHA workspace; mọi immutable extra khác phải khớp.43delivery controls PASS/0SKIP/0,58 giây, gồm chặn pointer giả/unknown/archive hỏng/target có model call và active builder stdout.
