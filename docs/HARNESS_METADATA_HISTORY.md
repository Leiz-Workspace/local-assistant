# Harness metadata history — opt-in

**Mục đích:** Hướng dẫn giữ lịch sử trạng thái run qua restart, tách rõ metadata archive khỏi khôi phục execution hoặc hội thoại.

**Ngày:** 2026-11-10. [ADR-182](ADR/182-opt-in-signed-harness-metadata-history.md), [store](../src/infrastructure/harness_history.py), [tests](../tests/test_harness_history.py). Mặc định vẫn memory-only; không đổi schema/database/Vault hoặc cấu hình desktop đang chạy.

## Cách dùng

Chọn thư mục mới hoặc thư mục history hợp lệ, parent đã có; service yêu cầu owner-only `0700` và files `0600`, một tiến trình tại một thời điểm:

```bash
uv run --no-sync la serve --state-dir data/harness-history
```

Hoặc đặt host environment `ASSISTANT_HARNESS_STATE_DIR` khi bật optional factory. Đường dẫn chỉ do operator cấu hình, không nhận từ model/task/API. Không trỏ vào thư mục chứa dữ liệu khác; unknown files, sai permissions, symlink/hardlink, record hỏng hoặc process lock đang giữ sẽ bị từ chối, không tự sửa/xóa hoặc fallback về memory.

`la status` báo `persistence: metadata-only`, `history_healthy`, `raw_results_persisted: false`, `skills_persistent: false`, `durable_resume: false`. Không truyền state-dir thì giữ behavior memory-only cũ.

## Thông tin được giữ

- Run/owner/workspace IDs, state và ordered event sequence.
- SHA-256 của request/result/context; finite error code.
- Signed schema-v1 snapshots, private local key và process-lock file.

Không lưu task text, source evidence, answer body, context text, skill instructions hoặc trust/approval/session/token. HMAC kiểm tra integrity của metadata; không là anti-rollback ledger hoặc bảo vệ trước người kiểm soát cùng OS user/key. Chỉ có file/directory fsync trong scope đã kiểm, chưa chứng minh mọi thiết bị chịu được power loss.

## Sau restart

```text
la runs list
la runs show RUN_UUID
la runs remove RUN_UUID
```

Terminal runs giữ trạng thái nhưng có `archive_only: true`, `result_available: false`. `context inspect` không thể phục hồi context body đã không lưu; dùng `runs show` để đọc digests. Run từng ở `created`/`running` trở thành **interrupted**, không được tự chạy lại. CLI `run --wait` gặp interruption sẽ thoát với `task_interrupted` thay vì đợi mãi hoặc replay.

Skill registry vẫn khởi tạo rỗng; muốn dùng skill phải review/install mới. Không khôi phục action approval, không refund budget hoặc tự resume task. Muốn làm lại, chủ động tạo run mới bằng task đầu vào và quyền hiện hành. Browser history vẫn theo IndexedDB; đây **không** phải đồng bộ PostgreSQL Conversation hoặc lưu câu trả lời lâu dài.

Retained run caps vẫn 8/owner và 64 toàn coordinator, gồm metadata archive; xóa terminal record qua `runs remove` để giải phóng capacity. Không auto-prune lịch sử hoặc xóa thư mục khi shutdown.

## Failure và rollback

Created snapshot được ghi trước khi schedule; running snapshot trước source read/inference. Ghi metadata lỗi làm service dừng nhận run mới. Không retry snapshot hoặc âm thầm chuyển sang memory. Nếu native answer đã tính xong nhưng terminal snapshot lỗi, API không publish persisted success/result; last durable active snapshot được xử lý interrupted khi storage được sửa và service khởi động lại thành công.

Để rollback, dừng đúng tiến trình sở hữu state-dir, giữ thư mục cho audit và khởi động lại bỏ state-dir/environment tương ứng. Không xóa hoặc thay các store trước đó. User chat desktop trên cổng 7090 không bị restart trong đợt kiểm chứng riêng trên 7092.

## Kiểm chứng thực tế

- Final combined related invocation **294 PASS / 0 FAIL / 0 SKIP, 3.80 s**, 24 test files: product/context/skill/planner/auth/security/preset, history và evaluation runners. Có real subprocess/loopback tests nhưng không model calls trong pytest. Lượt 291/3.75 s trước khi thêm post-rename fault test và context-probe tests là checkpoint cũ, không cộng counts.
- Kill một fixture process tại state running, mở process khác cùng directory: run interrupted, archive-only, không raw result/grant/resume, cross-owner GET bị từ chối. Unit test còn chứng minh inference không được gọi khi load/recover metadata.
- Fault injection ở created/running/terminal persistence và directory-fsync sau atomic rename: không retry, không inference trước durable running record, không publish answer nếu terminal snapshot chưa được ghi; renamed active snapshot không thành execution authority và recover interrupted. Corruption/schema/link/permission/process-lock/privacy tests PASS.
- Một CORE completion thật trên cổng probe 7092 trả `HISTORY-READY`; sau stop/start thành tiến trình khác, cùng result/context hashes, state succeeded, archive-only, answer/context body không có, skill registry rỗng. [Native restart receipt](evidence/harness-history-native-restart-20261110.json). Probe đã dừng; primary desktop/CORE giữ nguyên.

Đây là local metadata recovery scope, không full regression D87, off-host disaster recovery, durable execution, chat sync hay specialist quality acceptance.
