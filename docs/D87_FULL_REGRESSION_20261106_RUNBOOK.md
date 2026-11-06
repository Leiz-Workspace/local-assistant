# D87 — Full regression mới cho snapshot có voice (chủ dự án tự chạy)

**Mục đích:** Chạy lại full regression có dịch vụ thật (PostgreSQL, Vault, Qdrant, CORE) trên snapshot hiện tại, gồm B1/B2 voice, ADR176, CI và LICENSE. Lượt gần nhất là 5.889 PASS trên snapshot 750 file ngày 2026-11-03, nay chỉ còn là lịch sử. Tài liệu này chuẩn bị lệnh; chủ dự án tự unseal Vault và tự chạy. Agent không đọc bootstrap material hay credential.

**Khác với CI GitHub:** CI chạy khoảng 6.098 test, không có DB/CORE, có 39 mục loại trừ và một job cách ly. D87 chạy `pytest tests` trên máy thật, không loại trừ gì, với `DATABASE_URL`, `LOCAL_ASSISTANT_LIVE_E2E=1` và `LOCAL_ASSISTANT_EMBEDDING_COMPARE_LIVE=1`.

## 1. Điều kiện trước khi chạy

1. Chạy trên Home Server, trong `~/Workspace/Server/ai`, nhánh `develop` mới nhất:

   ```bash
   cd ~/Workspace/Server/ai && git fetch origin && git switch develop && git merge --ff-only origin/develop && git log --oneline -1
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

Mỗi lượt dùng một thư mục kết quả **mới**; script từ chối thư mục đã tồn tại.

```bash
uv run --no-sync python -m scripts.full_regression data/backups/d87-20261106-full
```

- Thời gian dự kiến khoảng 35–40 phút; lượt trước mất 2.128,68 giây.
- Log và `result.json` nằm trong thư mục kết quả, credential đã được ẩn. Không sửa hay xóa các file này.
- Lệnh thoát `0` chỉ khi `accepted_full_software_regression` là `true`.

## 3. Sau khi chạy

1. Dừng CORE nếu bạn đã khởi động nó cho lượt này:

   ```bash
   docker compose --profile core stop
   ```

2. Gửi lại cho agent nội dung tóm tắt (không gửi credential):

   ```bash
   python3 -c "import json;d=json.load(open('data/backups/d87-20261106-full/result.json'));print({k:d.get(k) for k in ('status','passed','failed','errors','skipped','exit_code','pytest_seconds','source_files','accepted_full_software_regression','summary')})"
   ```

## 4. Cách đọc kết quả

| Kết quả | Ý nghĩa |
|---|---|
| `failed=0, errors=0, skipped=0`, exit 0 | D87 software regression đạt cho snapshot này |
| Có `skipped` | Không phải PASS: biến môi trường hoặc dịch vụ còn thiếu (D87 yêu cầu 0 SKIP) |
| Lỗi ở `test_video_*`, `test_media_timeline.py` | Có thể là lỗi decoder gián đoạn P2 đã biết; ghi nguyên, không chạy lại để che lỗi |
| Lỗi khác | Ghi nguyên log; agent phân tích trước khi sửa |

Full regression là bằng chứng phần mềm, không phải đo chất lượng model, nghiệm thu thiết bị hay quyết định release (D89/D90).
