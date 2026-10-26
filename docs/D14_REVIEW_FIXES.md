# D14 — Sửa các lỗi từ code review

**Mục đích:** Ghi lại ba lỗi đã sửa, bằng chứng kiểm thử và giới hạn của lần kiểm chứng ngày 2026-10-26.

Historical cohort below remains unchanged. The later [selected semantic path is independently verified42/42perprofile](D14_SEMANTIC_REMEDIATION_RESULT.md); its result does not rewrite these first scores.

Cả ba phát hiện review đã được sửa. [ADR-134](ADR/134-shared-d14-acceptance-and-retained-request-binding.md) ghi quyết định và ảnh hưởng; [receipt cuối](evidence/d14-structured-review-fixes-verification-final.json) giữ kết quả offline riêng. D14 vẫn **FORMAT FIX VERIFIED / FUNCTIONAL QUALITY GATE FAIL**.

| Phát hiện | Thay đổi | Kiểm chứng |
|---|---|---|
| P1: runner bỏ qua ba bài streaming bổ sung | Runner dùng policy chung, xét đúng danh tính/số lượng và kết quả của toàn bộ bài đã khai báo, cả runtime compatibility | Full mock controller chặn compatibility sai format, sai nội dung và chưa reaped; trường hợp đúng vẫn PASS |
| P2: report bỏ qua provenance | Report dùng cùng policy với runner; yêu cầu đúng năm kiểm tra có tên riêng, tất cả literal `true`, cùng lifecycle/cancel/baseline | Test đối chiếu hai caller: provenance 0/5, thiếu/trùng tên và giá trị truthy đều không PASS |
| P2: hash tự khai không ràng buộc prompt | Tái dựng toàn bộ request từ đề/schema/template/ảnh/tham số; đối chiếu byte request với ZIP cũ đã ghim SHA độc lập | Chặn prompt được thay bằng đáp án dù đã tính lại self-hash, đổi system/turn/ảnh/needle/vị trí/tham số; vẫn xác minh được cả 87 request gốc |

## Kết quả

**418 scoped tests PASS / 0 FAIL / 0 ERROR / 0 SKIP, 5.15 giây.** Bao gồm adapter, controller thực qua mock transport, policy chung, report/artifact, cancellation và delivery. Ruff kiểm tra E4/E7/E9/F đạt; tám file mới/sửa được kiểm tra format. Đây không phải full suite mới. Snapshot ứng dụng vẫn 730 file, toàn bộ 728 file của full lịch sử 5674 PASS giữ nguyên; thay đổi lần này nằm ở benchmark/test và tài liệu.

Không gọi model thêm. Kiểm chứng offline giữ CORE first 39/42 format và 28/42 functional; replay byte cũ 42/42 format và 31/42 functional. UNRESTRICTED first vẫn 42/42 format, 30/42 functional; compatibility 3/3. Mức yêu cầu 42/42 mỗi profile không đổi. Lỗi nội dung của model vẫn chặn quality promotion; ba lỗi phần mềm trong review đã được xử lý.

Đầu vào context được đối chiếu toàn bộ byte với archive cũ, kiểm tra cấu trúc document/needle. Không tuyên bố đã đếm token lại hoặc tạo receipt trước inference. ZIP cũ có SHA `1f2b7d9197a56488b7e7ae9ce1543a43b6817f54a57b4a0aafcd4471046ce463` là dependency của operator report; giữ nó tại `data/backups/local-assistant-d14-quality-gate-20261026-full-files.zip` khi chạy xác minh sau. Test cần artifact nằm trong `data/backups/test_d14_review_fixes_wire_report.py`; public benchmark tests dùng fixture/mock và không cần archive/weights riêng.

Runtime cleanup được xác minh từ receipt lịch sử; boot ID hiện khác, native inventory vẫn rỗng và container inventory khớp. Không coi lượt đọc lại này là benchmark hoặc audit database mới. Model/config/default/Docker/Vault/database/Qdrant/dữ liệu và D70 nghe 0/24 giữ nguyên.

## Lệnh và lưu vết

Operator offline: `uv run --no-sync python -m benchmarks.scripts.d14_structured_report`. Publisher không ghi đè receipt đã có; không chạy lại chỉ để thay một kết quả cũ. Kiểm thử dùng `uv run --no-sync pytest` với các module liên quan; chi tiết terminal tại `data/backups/d14-review-fixes-final-checkout-safe-tests.log` và `data/backups/d14-review-fixes-final-checked-offline.log`.

Các lần collection đầu gặp trùng tên module public/private; thử importlib bộc lộ import theo tên của test cũ. Đã đổi tên và giữ test phụ thuộc artifact ở vùng operator riêng, chạy lại normal collection đạt đầy đủ, không sửa test ứng dụng đã PASS. Lượt lint theo cấu hình bên ngoài báo style C408/RUF059; dùng bộ E4/E7/E9/F tường minh, sửa biến không dùng và kiểm tra format, không thay hàng loạt code cũ để đổi style. Log ban đầu được giữ. Lần audit đầu dừng ở boot ID khác; sau khi tách rõ lịch sử/hiện tại, receipt mới ghi đúng khác biệt đó. Hai receipt review trung gian giữ riêng; receipt có hậu tố `final` là kết quả dùng cho bản sửa cuối.

Gói code đầy đủ: `data/backups/local-assistant-d14-review-fixes-20261026-full-files.zip`, receipt `.receipt.json` cùng thư mục. Gói được tạo sau commit, giữ artifact trước và chỉ thêm evidence đã chọn; không chứa secret/weights/dump/cache. Receipt xác nhận Git-byte, artifact-byte, CRC và SHA sau khi build hoàn tất. Đây là bản review, không phải release.


## Later semantic remediation — 2026-10-26

This document's original cohort/first scores remain unchanged. A separately preregistered selected bounded-reasoning/boolean-contract path now verifies freshCORE42/42andUNRESTRICTED42/42 with full lifecycle/provenance/context checks: [actual remediation, retained failures and cost](D14_SEMANTIC_REMEDIATION_RESULT.md).568scopedPASS/0SKIP, all730priorappfiles exact/current732; no newfull732/model/default/release claim.
