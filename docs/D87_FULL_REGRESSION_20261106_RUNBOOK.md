# D87 — Full regression mới cho snapshot có voice (chủ dự án tự chạy)

> **Ghi chú 2026-11-09:** Lượt D87 theo runbook này đã được assistant chạy ngày 2026-11-09 theo yêu cầu của chủ dự án ("Tiếp theo làm D81, D87 đi", thứ tự "Sau D81 + promote (Recommended)"), trên `develop` `3812e5c` có cây trùng `production` `0b67d95`. Kết quả **PASS: 6.200 PASS / 0 FAIL / 0 ERROR / 0 SKIP**, exit 0, 817 file source không đổi ([kết quả](D87_CURRENT_FULL_RESULT.md), [receipt](evidence/d87-20261109-full-acceptance.json)). Khác với cách mặc định dưới đây, lượt này Vault do assistant unseal từ bootstrap file theo ủy quyền của chủ dự án ngày 2026-11-08 (key share không in ra). Thư mục `data/backups/d87-20261109-full` đã dùng; lượt sau phải dùng một thư mục kết quả mới chưa tồn tại (lệnh ở mục 2 đặt tên theo ngày chạy) và vẫn làm đủ mục 1, gồm kiểm tra cây `develop` trùng `production` trên commit sẽ tag.
>
> **Ghi chú 2026-11-09 (sửa test timeout):** Sau lượt D87 trên, theo lựa chọn "Làm cách 2 đi" của chủ dự án, hai test `tests/test_pdf_extractor.py::test_real_timeout_reaps_worker` và `tests/test_page_ocr.py::test_timeout_reaps_worker_and_descendant` được sửa trên nhánh `fix/timeout-reap-tests` để cho phép một cửa sổ dọn tiến trình có giới hạn 5 giây sau khi lời gọi trả về thay vì kiểm tra ngay (kiểm tra yếu hơn trước, xem [ledger](OUTSTANDING_WORK_STATUS.md) mục ngày 2026-11-09); danh sách cách ly CI nay rỗng; code production không đổi. Phạm vi source freeze của D87 gồm `tests/`, nên lượt PASS ngày 2026-11-09 chỉ áp dụng cho cây `production` `0b67d95`; sau khi thay đổi này vào `develop`, cây source của `develop` khác cây đó. D87 dùng cho tag phải chạy trên cây cuối cùng của commit sẽ tag (làm đủ mục 1: promote trước, rồi kiểm tra cây), hoặc chủ dự án ghi ngoại lệ có tên trong phiếu D90, đúng như caveat sẵn có ([hồ sơ D90](D90_RELEASE_DECISION_DOSSIER.md) mục 6).

**Mục đích:** Chạy lại full regression có dịch vụ thật (PostgreSQL, Vault, Qdrant, CORE) trên snapshot hiện tại, gồm B1/B2 voice, ADR176, ADR178, CI, LICENSE và bản sửa lỗi decoder P2 (PR #33). Lượt gần nhất là 6.200 PASS trên 817 file ngày 2026-11-09 (ghi chú trên); lượt 5.889 PASS trên snapshot 750 file ngày 2026-11-03 nay chỉ còn là lịch sử. Tài liệu này chuẩn bị lệnh; chủ dự án tự unseal Vault và tự chạy. Agent không đọc bootstrap material hay credential.

**Khác với CI GitHub:** CI không có DB/CORE, có 39 mục loại trừ và một job cách ly. Run trên `develop` (run 42379106825, commit `cebf9a0`, ngày 2026-11-07) có job chính 6.287 passed, 368 skipped, 31 deselected; job cách ly khi đó chỉ còn 1 test (`tests/test_page_ocr.py::test_timeout_reaps_worker_and_descendant`). Run push lên `production` sau lượt promote ngày 2026-11-08 (run 42450698663, commit `2e5e242`) cho cùng con số: job chính 6.287 passed, 368 skipped, 31 deselected; job cách ly 1 passed. Run push lên `production` sau lượt promote ngày 2026-11-09 (run 42556825440, commit `0b67d95`, có code D81 mặc định tắt): job chính 6.456 passed, 368 skipped, 31 deselected; job cách ly thành công. Cập nhật 2026-11-09: trên nhánh `fix/timeout-reap-tests`, test OCR nói trên và test timeout PDF cho phép cửa sổ dọn tiến trình có giới hạn 5 giây sau khi lời gọi trả về, test OCR được gỡ khỏi danh sách cách ly và danh sách nay rỗng, nên job cách ly không chọn test nào và báo thành công (pytest exit 5 chỉ được coi là thành công khi danh sách không có mục nào; một mục cũ hoặc gõ sai vẫn làm job hỏng) cho tới khi có test chập chờn mới được thêm vào. D87 chạy `pytest tests` trên máy thật, không loại trừ gì, với `DATABASE_URL`, `LOCAL_ASSISTANT_LIVE_E2E=1` và `LOCAL_ASSISTANT_EMBEDDING_COMPARE_LIVE=1`. `pytest tests` không chạy `benchmarks/tests` (gồm test runner B3 của ADR178); phần đó đã được CI và cổng phần mềm B3 kiểm.

## 1. Điều kiện trước khi chạy

1. Chạy trên Home Server, trong `~/Workspace/Server/ai`, nhánh `develop` mới nhất:

   ```bash
   cd ~/Workspace/Server/ai && git fetch origin && git switch develop && git merge --ff-only origin/develop && git log --oneline -1
   ```

   Nếu `git merge` báo có thay đổi cục bộ trong `dev_log/dev_log.md` (dòng kết nối SQL của editor ở đầu file), chạy `git stash`, merge lại, rồi `git stash pop`.

   D87 dùng cho D90 phải chạy trên đúng nội dung của commit sẽ tag trên `production` ([hồ sơ D90](D90_RELEASE_DECISION_DOSSIER.md), mục 6). Kiểm tra cây của `develop` trùng với `production`; nếu khác (ví dụ còn PR `docs:` chưa promote), promote trước rồi mới chạy.

   Ngày 2026-11-07, `develop` có thêm một thay đổi mã chưa promote: PR #33 (merge `cebf9a0`) sửa launcher `child_output` trong `src/infrastructure/ocr_worker.py`; khi đó `staging` (`0ec664d`) và `production` (`4dcf8db`) chưa có thay đổi này. Ngày 2026-11-08, thay đổi đó đã được promote lên `staging` qua PR #36 (`4c99408`) và lên `production` qua PR #37 (`2e5e242`); ngay sau lượt promote, cây của `production` trùng với cây của `develop` tại `dea1b55`. Đây chỉ là promote nhánh: không có tag, GitHub Release hay deploy lên Home Server. Mỗi PR `docs:` vào `develop` sau đó (ví dụ PR ghi lại lượt promote này, hoặc phiếu D90 đã điền theo mục 6 của hồ sơ D90) sẽ làm cây của `develop` lại khác `production` cho tới lượt promote kế tiếp. Vì vậy trước D87 vẫn chạy lệnh kiểm tra dưới đây:

   ```bash
   test "$(git rev-parse origin/develop^{tree})" = "$(git rev-parse origin/production^{tree})" && echo "develop trùng production" || echo "develop khác production: promote trước"
   ```

2. Cài đúng dependency đã khóa:

   ```bash
   uv sync --locked --dev
   ```

3. Vault đã unseal bằng bootstrap material của bạn; không init hoặc rotate. Script đọc credential qua `../infras/scripts/vault_static_secret.py`, mặc định dùng `vault-server/vault.env`, `vault-init.json` và `tls/ca.crt` trong workspace, hoặc `VAULT_TOKEN`/`VAULT_ENV_FILE`/`VAULT_INIT_FILE`/`VAULT_CA_FILE` nếu bạn đặt.
4. CORE đang phục vụ ở `127.0.0.1:8080` với cấu hình hiện có (CORE profile trong `docker-compose.yaml`). Chỉ khởi động CORE, không restart PostgreSQL/Vault/Qdrant dùng chung:

   ```bash
   docker compose --profile core up -d && curl -s 127.0.0.1:8080/health
   ```

5. Không chạy trang thử voice 8092, lượt B3 hay job GPU khác cùng lúc. GPU 16 GiB phải dành cho CORE.

## 2. Chạy

Mỗi lượt dùng một thư mục kết quả **mới**; script từ chối thư mục đã tồn tại. `data/backups/d87-20261109-full` đã dùng cho lượt 2026-11-09. Lệnh dưới đặt tên thư mục theo ngày chạy; nếu chạy lại trong cùng ngày, thêm hậu tố (ví dụ `-2`). Giữ nguyên terminal này cho mục 3, vì lệnh ở đó dùng lại `D87_DIR`.

```bash
D87_DIR=data/backups/d87-$(date +%Y%m%d)-full
uv run --no-sync python -m scripts.full_regression "$D87_DIR"
```

- Thời gian dự kiến khoảng 30–40 phút; lượt 2026-11-09 mất 1.869,85 giây (pytest), lượt 2026-11-03 mất 2.128,68 giây.
- Log và `result.json` nằm trong thư mục kết quả, credential đã được ẩn. Không sửa hay xóa các file này.
- Lệnh thoát `0` chỉ khi `accepted_full_software_regression` là `true`.

## 3. Sau khi chạy

1. Dừng CORE nếu bạn đã khởi động nó cho lượt này:

   ```bash
   docker compose --profile core stop
   ```

2. Gửi lại cho agent nội dung tóm tắt (không gửi credential), trong cùng terminal đã đặt `D87_DIR` ở mục 2:

   ```bash
   python3 -c "import json;d=json.load(open('$D87_DIR/result.json'));print({k:d.get(k) for k in ('status','passed','failed','errors','skipped','exit_code','pytest_seconds','source_files','accepted_full_software_regression','summary')})"
   ```

## 4. Cách đọc kết quả

| Kết quả | Ý nghĩa |
|---|---|
| `failed=0, errors=0, skipped=0`, exit 0 | D87 software regression đạt cho snapshot này |
| Có `skipped` | Không phải PASS: biến môi trường hoặc dịch vụ còn thiếu (D87 yêu cầu 0 SKIP) |
| Lỗi ở `test_video_*`, `test_media_timeline.py` | Nguyên nhân đã biết của lỗi decoder P2 đã được sửa ở PR #33 ([phân tích](P2_MEDIA_DECODER_ROOT_CAUSE.md)), nên lỗi ở đây giờ được coi là hồi quy: ghi nguyên log, không chạy lại để che lỗi; agent phân tích trước khi sửa |
| Lỗi khác | Ghi nguyên log; agent phân tích trước khi sửa |

Full regression là bằng chứng phần mềm, không phải đo chất lượng model, nghiệm thu thiết bị hay quyết định release (D89/D90).
