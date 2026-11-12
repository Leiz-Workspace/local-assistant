# D87 — Full regression trên source hiện tại

**Mục đích:** Ghi kết quả full suite hiện hành trên cây source của `develop` `48d5694` (cây `a2d1318`, sau PR #67: regression test của bridge UI cho HAR-002). Các lượt trước được giữ ở các mục lịch sử bên dưới.

**Trạng thái: PASS — full software regression cho cây source của `develop` `48d5694` (cây `a2d1318091d35e04ab431f3ba79d92cc934bc1fa`), lượt chạy kết thúc 12:10 ngày 2026-11-12.** [Receipt công khai](../evidence/d87-20261112-develop-48d5694-acceptance.json). Đây là bằng chứng hồi quy phần mềm, không phải đo chất lượng model, nghiệm thu thiết bị, D89 hay quyết định release.

| Phạm vi | Kết quả thực tế (lượt `d87-20261112-full-5`) |
|---|---|
| Toàn bộ `pytest tests` | **6.743 PASS / 0 FAIL / 0 ERROR / 0 SKIP**, exit 0, status `complete`, `accepted_full_software_regression: true` |
| Thời gian pytest | **1,816.28 giây** (summary "6743 passed, 1 warning in 1816.28s (0:30:16)"); wrapper 1,817.76 giây |
| Source snapshot | **883 file**, `source_bytes_unchanged: true`; source freeze `6169dea74b9f9cfb6da1aa845a29e246ae908931d35e48d04b39ef7f5ebeecc1` |
| Commit và cây | `develop` `48d5694` (merge PR #67), cây trùng `origin/develop`; ngoài source chỉ có dòng kết nối editor ở đầu `dev_log/dev_log.md` |
| Log SHA-256 | `807e17563787ff9c16171dc2f878e80bbe7027048fb0d5af43ef9e802971ce77` |
| So với full trước | 6.739 PASS trên 883 file (`dde7c39`) nay là lịch sử; PR #67 thêm 4 regression test của bridge UI, không thêm file source. `develop` khác `production` ở 64 file source |

- **Thời gian.** Lượt chạy từ 11:40:37 tới 12:10:55 ngày 2026-11-12 (04:40:37Z–05:10:55Z).
- **Máy rảnh.** Điều kiện rảnh đạt sau 90 giây (0,30 / 0,34 / 0,33).
- **Tải trong lúc chạy.** 61 lần đo: trung bình 1,38, trung vị 1,28, tối đa 2,31 CPU bận. Test reranker PASS.
- **Dịch vụ.** Vault đã ở trạng thái unseal. CORE chạy bằng `docker compose --profile core` rồi được dừng sau lượt chạy. Dịch vụ dùng chung không bị restart.
- **Database và Qdrant (read-only).** Kết quả trước và sau giống nhau: các bảng hội thoại, bộ nhớ và ingestion đều 0; usage 1 dòng mỗi bảng; Alembic `0006`; Qdrant không có collection nào.
- **Phạm vi.** Chưa promote, chưa tag, chưa release, chưa deploy. D81, D89, D90 vẫn mở.

## Lịch sử: lượt 2026-11-12 trên `develop` `dde7c39`

**Mục đích (lượt này):** Ghi kết quả full suite trên cây source của `develop` `dde7c39` (cây `9edff17`, sau PR #65: contract tóm tắt HAR-009-C v2 đã đo trên held-out và nhãn `/status`). Các lượt trước được giữ ở các mục lịch sử bên dưới.

**Trạng thái lượt này: PASS — full software regression cho cây source của `develop` `dde7c39` (cây `9edff17624369e933b40afcfe1d738d4467bea11`), lượt chạy kết thúc 11:19 ngày 2026-11-12.** [Receipt công khai](../evidence/d87-20261112-develop-dde7c39-acceptance.json). Đây là bằng chứng hồi quy phần mềm, không phải đo chất lượng model, nghiệm thu thiết bị, D89 hay quyết định release.

| Phạm vi | Kết quả thực tế (lượt `d87-20261112-full-4`) |
|---|---|
| Toàn bộ `pytest tests` | **6.739 PASS / 0 FAIL / 0 ERROR / 0 SKIP**, exit 0, status `complete`, `accepted_full_software_regression: true` |
| Thời gian pytest | **1.817,70 giây** (summary "6739 passed, 1 warning in 1817.70s (0:30:17)"); wrapper 1.819,24 giây |
| Source snapshot | **883 file**, `source_bytes_unchanged: true`; source freeze `19b3dd2c888ac374354b4ea232f4be46b81b297f764924ea0a9759afac86f890` |
| Commit và cây | `develop` `dde7c39` (merge PR #65), cây trùng `origin/develop`; ngoài source chỉ có dòng kết nối editor ở đầu `dev_log/dev_log.md` |
| Log SHA-256 | `9906c3afa288d347d4296ec7b03314a5c0a0851f0a3931396b9d9db0e95d34cf` |
| So với full trước | 6.578 PASS trên 883 file (`d8ed1cb`) nay là lịch sử. PR #65 thêm 161 test case trong `tests/` (contract tóm tắt v2, hash được pin, nhãn `/status`) và không thêm file source. `develop` khác `production` ở 64 file source |

- **Thời gian.** Lượt chạy từ 10:49:00 tới 11:19:20 ngày 2026-11-12 (03:49:00Z–04:19:20Z).
- **Máy rảnh.** Điều kiện rảnh đạt sau 90 giây (0,29 / 0,31 / 0,33).
- **Tải trong lúc chạy.** 61 lần đo: trung bình 1,37, trung vị 1,25, tối đa 2,30 CPU bận. Test reranker PASS.
- **Dịch vụ.** Vault đã ở trạng thái unseal. CORE chạy bằng `docker compose --profile core` rồi được dừng sau lượt chạy. Dịch vụ dùng chung không bị restart.
- **Database và Qdrant (read-only).** Kết quả trước và sau giống nhau: các bảng hội thoại, bộ nhớ và ingestion đều 0; usage 1 dòng mỗi bảng; Alembic `0006`; Qdrant không có collection nào.
- **Trên nhánh trước khi merge.** D87 cũng đạt hai lần trên `feat/har009-c-summary-v2`: 6.738 PASS trước S0 (`058d09d`) và 6.739 PASS lúc freeze (`ac9b9f2`).
- **Phạm vi.** Chưa promote, chưa tag, chưa release, chưa deploy. D81, D89, D90 vẫn mở.

## Lịch sử: lượt 2026-11-12 trên `develop` `d8ed1cb`

**Mục đích (lượt này):** Ghi kết quả full suite trên cây source của `develop` `d8ed1cb` (cây `2eaf191`, sau PR #63: lệnh approval của CLI và mã 403 cho query của UI). Các lượt trước được giữ ở các mục lịch sử bên dưới.

**Trạng thái lượt này: PASS — full software regression cho cây source của `develop` `d8ed1cb` (cây `2eaf1914e952afd1cc36e974780a96e9c6b1b915`), lượt chạy kết thúc 01:18 ngày 2026-11-12.** [Receipt công khai](../evidence/d87-20261112-develop-d8ed1cb-acceptance.json). Đây là bằng chứng hồi quy phần mềm, không phải đo chất lượng model, nghiệm thu thiết bị, D89 hay quyết định release.

| Phạm vi | Kết quả thực tế (lượt `d87-20261112-full`) |
|---|---|
| Toàn bộ `pytest tests` | **6.578 PASS / 0 FAIL / 0 ERROR / 0 SKIP**, exit 0, status `complete`, `accepted_full_software_regression: true` |
| Thời gian pytest | **1.831,98 giây** (summary "6578 passed, 1 warning in 1831.98s (0:30:31)"); wrapper 1.833,56 giây |
| Source snapshot | **883 file**, `source_bytes_unchanged: true`; source freeze `b379f01f113b0fce294d108de81fc66792e24107a6ceece1c2a92178b9ce68c7` |
| Commit và cây | `develop` `d8ed1cb` (merge PR #63), cây trùng `origin/develop`; ngoài source chỉ có dòng kết nối editor ở đầu `dev_log/dev_log.md` |
| Log SHA-256 | `74cdae8300cd3aae1368dcdd11459c47dd08b6cc0f6a2f4e79c3cfd56f5dffca` |
| So với full trước | 6.556 PASS trên 883 file (`695a52e`) nay là lịch sử; thêm 22 test case của CLI approval, không thêm file source. `develop` khác `production` ở 64 file source |

- **Thời gian.** Lượt chạy từ 00:47:45 tới 01:18:18 ngày 2026-11-12 (17:47:45Z–18:18:18Z ngày 2026-11-11).
- **Máy rảnh.** Điều kiện rảnh đạt sau 90 giây (0,41 / 0,28 / 0,22).
- **Tải trong lúc chạy.** 62 lần đo: trung bình 1,44, trung vị 1,33, tối đa 2,36 CPU bận, gồm cả một workflow thiết kế chỉ đọc chạy song song (không chạy test, không gọi model). Test reranker PASS.
- **Dịch vụ.** Vault đã ở trạng thái unseal. CORE chạy bằng `docker compose --profile core` rồi được dừng sau lượt chạy. Dịch vụ dùng chung không bị restart.
- **Database và Qdrant (read-only).** Kết quả trước và sau giống nhau: các bảng hội thoại, bộ nhớ và ingestion đều 0; usage 1 dòng mỗi bảng; Alembic `0006`; Qdrant không có collection nào.
- **Phạm vi.** Chưa promote, chưa tag, chưa release, chưa deploy. D81, D89, D90 vẫn mở.

## Lịch sử: lượt 2026-11-12 trên `develop` `695a52e`

**Mục đích (lượt này):** Ghi kết quả full suite trên cây source của `develop` `695a52e` (cây `e16fca4`, sau PR #60: tóm tắt opt-in HAR-009-C). Các lượt trước được giữ ở các mục lịch sử bên dưới.

**Trạng thái lượt này: PASS — full software regression cho cây source của `develop` `695a52e` (cây `e16fca4840bbd12cb0b8686ec2d98d637e44b0db`), lượt chạy kết thúc 00:07 ngày 2026-11-12.** [Receipt công khai](../evidence/d87-20261112-develop-695a52e-acceptance.json). Đây là bằng chứng hồi quy phần mềm, không phải đo chất lượng model, nghiệm thu thiết bị, D89 hay quyết định release.

| Phạm vi | Kết quả thực tế (lượt `d87-20261111-full-5`) |
|---|---|
| Toàn bộ `pytest tests` | **6.556 PASS / 0 FAIL / 0 ERROR / 0 SKIP**, exit 0, status `complete`, `accepted_full_software_regression: true` |
| Thời gian pytest | **1.853,25 giây** (summary "6556 passed, 1 warning in 1853.25s (0:30:53)"); wrapper 1.854,85 giây |
| Source snapshot | **883 file**, `source_bytes_unchanged: true`; source freeze `b808c4bf9556712d542e661be81f54d2e5085d55fddea0683b4977c8f739cb7b` |
| Commit và cây | `develop` `695a52e` (merge PR #60), cây trùng `origin/develop`; ngoài source chỉ có dòng kết nối editor ở đầu `dev_log/dev_log.md` |
| Log SHA-256 | `bb48ffe8abed5edbd5ea4e77c45eec7282d3b932a23cf83ceff5737ada969e80` |
| So với full trước | 6.509 PASS trên 879 file (`a657709`) nay là lịch sử; thêm 47 test tóm tắt và 4 file source. `develop` khác `production` ở 64 file source |

- **Thời gian.** Lượt chạy từ 23:36:24 ngày 2026-11-11 tới 00:07:19 ngày 2026-11-12 (16:36:24Z–17:07:19Z).
- **Máy rảnh.** Điều kiện rảnh đạt sau 90 giây (0,27 / 0,27 / 0,25).
- **Tải trong lúc chạy.** 62 lần đo: trung bình 1,57, trung vị 1,45, tối đa 2,48 CPU bận. Test reranker PASS.
- **Dịch vụ.** Vault đã ở trạng thái unseal. CORE chạy bằng `docker compose --profile core` rồi được dừng sau lượt chạy. Dịch vụ dùng chung không bị restart.
- **Database và Qdrant (read-only).** Kết quả trước và sau giống nhau: các bảng hội thoại, bộ nhớ và ingestion đều 0; usage 1 dòng mỗi bảng; Alembic `0006`; Qdrant không có collection nào.
- **Phạm vi.** Chưa promote, chưa tag, chưa release, chưa deploy. D81, D89, D90 vẫn mở.

## Lịch sử: lượt 2026-11-11 trên `develop` `a657709`

**Mục đích (lượt này):** Ghi kết quả full suite trên cây source của `develop` `a657709` (cây `a53f51d`, sau PR #58: giấy phép llama.cpp được đưa vào package). Các lượt trước được giữ ở các mục lịch sử bên dưới.

**Trạng thái lượt này: PASS — full software regression cho cây source của `develop` `a657709` (cây `a53f51dfee821378680f498542c5f2354ab7b2b4`), ngày 2026-11-11.** [Receipt công khai](../evidence/d87-20261111-develop-a657709-acceptance.json). Đây là bằng chứng hồi quy phần mềm cho đúng cây source này, không phải đo chất lượng model, nghiệm thu thiết bị, D89 hay quyết định release.

| Phạm vi | Kết quả thực tế (lượt `d87-20261111-full-4`) |
|---|---|
| Toàn bộ `pytest tests` | **6.509 PASS / 0 FAIL / 0 ERROR / 0 SKIP**, exit 0, status `complete`, `accepted_full_software_regression: true` |
| Thời gian pytest | **1.872,49 giây** (summary "6509 passed, 1 warning in 1872.49s (0:31:12)"); wrapper 1.874,02 giây |
| Source snapshot | **879 file**, `source_bytes_unchanged: true`; source freeze `afe1bbc73a39533e68f6cfd74b0433470abe5a7364e23ebd51ca03a1e68ef13e` |
| Commit và cây | `develop` `a657709` (merge PR #58), cây trùng `origin/develop`; ngoài source chỉ có dòng kết nối editor ở đầu `dev_log/dev_log.md` |
| Log SHA-256 | `4f92918915005dac699cf807595ada3fa6a86ea3f295df8561762f66ec8614e6` |
| So với full trước | 6.508 PASS trên 878 file (`cdbcdd4`) nay là lịch sử; thêm 1 test và file giấy phép trong package. `develop` khác `production` ở 60 file source |

- **Thời gian.** Lượt chạy từ 21:43:26 tới 22:14:40 (14:43:26Z–15:14:40Z).
- **Máy rảnh.** Điều kiện rảnh đạt sau 90 giây (0,35 / 0,33 / 0,33).
- **Tải trong lúc chạy.** 63 lần đo: trung bình 1,82, trung vị 1,50 CPU bận. Có một đợt tăng ngắn (4,80 / 10,69 / 4,48) vào khoảng phút 6,5–8; chưa xác định được nguyên nhân. Test reranker giới hạn CPU vẫn PASS. Test này chạy ở khoảng 7% tiến độ pytest; log không ghi thời gian từng test nên không xác định được nó có trùng đợt tăng tải hay không.
- **Dịch vụ.** Vault đã ở trạng thái unseal. CORE chạy bằng `docker compose --profile core up -d` rồi được dừng sau lượt chạy. Dịch vụ dùng chung không bị restart.
- **Database và Qdrant (read-only).** Kết quả trước và sau giống nhau: các bảng hội thoại, bộ nhớ và ingestion đều 0; usage 1 dòng mỗi bảng; Alembic `0006`; Qdrant không có collection nào.
- **Phạm vi.** Chưa promote, chưa tag, chưa release, chưa deploy. D81, D89, D90 vẫn mở.

## Lịch sử: lượt 2026-11-11 trên `develop` `cdbcdd4`

**Mục đích (lượt này):** Ghi kết quả full suite trên cây source của `develop` `cdbcdd4` (cây `3038817`, sau khi merge HAR-009-C1 ngày 2026-11-11), cùng lượt trước đó bị gián đoạn do máy chủ khởi động lại. Các lượt trên `develop` `7fb5999`, `production` `dd7fac3`, `0b67d95` và ngày 2026-10-27 được giữ nguyên ở các mục lịch sử bên dưới.

**Trạng thái lượt này: PASS — full software regression cho cây source của `develop` `cdbcdd4` (cây `3038817580a6cf679dbe086e55b2903fbab0a6d1`), ngày 2026-11-11.** [Receipt công khai](../evidence/d87-20261111-develop-cdbcdd4-acceptance.json). Đây là bằng chứng hồi quy phần mềm cho đúng cây source này, không phải đo chất lượng model, nghiệm thu thiết bị, D89 hay quyết định release.

| Phạm vi | Kết quả thực tế (lượt `d87-20261111-full-3`) |
|---|---|
| Toàn bộ `pytest tests` | **6.508 PASS / 0 FAIL / 0 ERROR / 0 SKIP**, exit 0, status `complete`, `accepted_full_software_regression: true` |
| Thời gian pytest | **1.839,05 giây** (summary "6508 passed, 1 warning in 1839.05s (0:30:39)"); wrapper 1.840,64 giây |
| Source snapshot | **878 file** trong `src`, `apps`, `scripts`, `tests`, `configs`, `pyproject.toml`, `uv.lock`; `source_bytes_unchanged: true` |
| Commit và cây | Checkout `develop` tại `cdbcdd4` (merge PR #56), cây `3038817580a6cf679dbe086e55b2903fbab0a6d1`, trùng cây của `origin/develop`; ngoài file source chỉ có dòng kết nối editor ở đầu `dev_log/dev_log.md` (không thuộc phạm vi source freeze) |
| Source freeze SHA-256 | `3351564763ee7b3e1819a8717a98e120a61868c2b84a95d22a0ae84eaa076163` (giống lượt bị gián đoạn) |
| Log SHA-256 | `63c69b1aa9d2dc41b8ebd69a7510f0ebc802c71156a0c29533261399fa560db7` |
| Cảnh báo | 1 warning: `UserWarning: Duplicate name: 'piper/voice.py'` từ test archive TTS cố ý tạo tên trùng |
| So với full trước | 6.479 PASS trên 876 file (`develop` `7fb5999`) nay là lịch sử; cây này thêm HAR-009-C1 (PR #56: 6 file source, 29 test working state). `develop` khác `production` ở 59 file source |

Lượt chạy bắt đầu 19:27:43 (2026-11-11T12:27:43Z) và kết thúc 19:58:24 (12:58:24Z) theo Asia/Ho_Chi_Minh. Thư mục kết quả `data/backups/d87-20261111-full-3` là private, bị git bỏ qua; receipt chỉ ghi tên thư mục và các SHA-256.

## Lượt bị gián đoạn: `d87-20261111-full-2` (không phải kết quả)

- **Thời gian.** Lượt bắt đầu 18:56:43 (11:56:43Z) trên cùng cây, có cùng source freeze `3351564…`.
- **Gián đoạn.** Container CORE dừng lúc 19:08:35 (exit 0) trong quá trình máy chủ tắt. Máy khởi động lại khoảng 19:18, `uptime` lúc 19:20 là 2 phút. Tiến trình pytest và wrapper bị dừng theo máy, nên `result.json` vẫn ở trạng thái `running`.
- **Log riêng.** Log riêng (SHA-256 `bad9934d…`) dừng ở khoảng 4%: 277 PASSED, rồi `tests/integration/test_grounded_tcp.py::test_actual_grounded_core_tcp_citation_and_joined_delivery` FAILED và ERROR, đúng lúc CORE dừng.
- **Không phải phán quyết về code.** Lượt này không phải kết quả hợp lệ và không được tính PASS hay FAIL. Test hỏng cần CORE qua TCP, và lượt `full-3` sau đó pass test này trên cùng cây.
- **Dữ liệu dở do teardown chưa kịp chạy** (đã đọc read-only trước khi xử lý):
  - collection Qdrant tạm `la_d25_probe_1f074c9f…` (0 point);
  - cho principal test `09fc75e0…`: 1 dòng `files` (`worker.txt`, 40 byte, request key `grounded-tcp`), 1 `ingestion_jobs` ở trạng thái `running`, 1 `ingestion_heads` và 1 `file_owner_usage`;
  - bộ đếm `file_global_usage` tăng thêm 1 file/40 byte.
- **Dọn dẹp.** Chủ dự án chọn "Dọn rồi chạy D87". Assistant chạy lại đúng logic teardown của fixture: xóa ingestion rows của principal, gọi `cleanup_owners` từ `tests/integration/test_file_http.py`, rồi xóa collection probe sau khi kiểm lại tên và 0 point. Kết quả: 1 `ingestion_heads` và 1 `ingestion_jobs` bị xóa, `files` về 0, `file_global_usage` về 0 file/0 byte, Alembic `0006`. Blob tạm nằm trong `/tmp` đã mất khi khởi động lại.

## Lệnh, source và dịch vụ (lượt `full-3`)

1. Checkout `develop` `cdbcdd4`, cây trùng `origin/develop^{tree}`.
2. Sau khi khởi động lại, Vault ở trạng thái seal. Assistant unseal bằng bootstrap file theo ủy quyền có sẵn của chủ dự án; key share được nộp trong process, không in ra. Các dịch vụ dùng chung (PostgreSQL, Vault, Qdrant…) đã được máy khởi động lại; assistant không restart dịch vụ nào.
3. Điều kiện rảnh (CPU logic bận dưới 0,5 trong 3 lần đo 30 giây liên tiếp) đạt sau 210 giây: 0,41 / 0,29 / 0,30. Tải trong lúc chạy: 62 lần đo, trung bình 1,47, tối đa 2,31 CPU bận.
4. CORE chạy bằng `docker compose --profile core up -d` (`local-assistant-core-1`, `local-assistant/llama-cuda:5c8854fd8`) và được dừng bằng `docker compose --profile core stop` sau lượt chạy.
5. Lệnh: `uv run --no-sync python -m scripts.full_regression data/backups/d87-20261111-full-3` (`pytest tests`, không loại trừ gì).
6. Test reranker CPU (`test_actual_pinned_reranker_paired_comparison`) PASS.

## Kiểm tra database và Qdrant (lượt `full-3`)

- **Database.** Truy vấn read-only bằng runtime role (database `local_assistant`, schema `assistant`) trước và sau lượt chạy cho cùng kết quả:
  - conversations, messages, inference_runs, files, memories, memory_consents, memory_settings, ingestion_jobs và ingestion_heads đều 0;
  - file_owner_usage 1, file_global_usage 1;
  - Alembic `0006`.
- **Qdrant.** Trước và sau lượt chạy không có collection nào.

## Phạm vi và ảnh hưởng (lượt `full-3`)

- Đây là full software regression cho cây `3038817` của `develop` `cdbcdd4`. Nếu `develop` được promote mà không đổi source thêm, cây source của `production` sẽ trùng cây đã kiểm này.
- Promotion vẫn chưa làm, vì GitHub Actions bị chặn do billing và promotion là quyết định của chủ dự án. Không tag, không release, không deploy. D81, D89 và D90 vẫn mở.

## Lịch sử: lượt 2026-11-11 trên `develop` `7fb5999`

**Mục đích (lượt này):** Ghi kết quả full suite trên cây source của `develop` `7fb5999` (cây `d5ed277`, sau khi merge HAR-009-B1/B2 ngày 2026-11-11): lệnh, source, dịch vụ, số liệu, kiểm tra database, phạm vi và ảnh hưởng tới promotion/D90. Lượt ngày 2026-11-09 trên `production` `dd7fac3`, lượt sáng 2026-11-09 trên `0b67d95` và kết quả ngày 2026-10-27 được giữ nguyên ở các mục lịch sử bên dưới.

**Trạng thái lượt này: PASS — full software regression cho cây source của `develop` `7fb5999` (cây `d5ed277a682ef7455fa26fd653b6cb450b0ac6a7`), ngày 2026-11-11.** [Receipt công khai](../evidence/d87-20261111-develop-7fb5999-acceptance.json). Đây là bằng chứng hồi quy phần mềm cho đúng cây source này, không phải đo chất lượng model, nghiệm thu thiết bị, D89 hay quyết định release.

| Phạm vi | Kết quả thực tế |
|---|---|
| Toàn bộ `pytest tests` | **6.479 PASS / 0 FAIL / 0 ERROR / 0 SKIP**, exit 0, status `complete`, `accepted_full_software_regression: true` |
| Thời gian pytest | **1.898,66 giây** (summary "6479 passed, 1 warning in 1898.66s (0:31:38)"); wrapper 1.900,30 giây |
| Source snapshot | **876 file** trong `src`, `apps`, `scripts`, `tests`, `configs`, `pyproject.toml`, `uv.lock`; `source_bytes_unchanged: true` |
| Commit và cây | Checkout `develop` tại `7fb5999` (merge PR #54), cây `d5ed277a682ef7455fa26fd653b6cb450b0ac6a7`, trùng cây của `origin/develop`; ngoài file source chỉ có dòng kết nối editor ở đầu `dev_log/dev_log.md` (không thuộc phạm vi source freeze) |
| Source freeze SHA-256 | `5ed6c60f4a3323763010b469f98c3c8a1b1afdb7b7871649ff47218fd663260f` |
| Log SHA-256 | `6025da45ec6fa20be1bdd51a3a9173ed6cff63c8760aa1d77c44c9ec22903c53` |
| Cảnh báo | 1 warning: `UserWarning: Duplicate name: 'piper/voice.py'` từ test archive TTS cố ý tạo tên trùng |
| So với full trước | 6.233 PASS trên 821 file (cây `production` `dd7fac3`, 2026-11-09) nay là lịch sử; cây này thêm công việc HAR v1–v1.7/Aevra (PR #52), HAR-009-B1 (PR #53) và HAR-009-B2 (PR #54): 57 file source khác `production` |

Lượt chạy bắt đầu 17:31:56 (2026-11-11T10:31:56Z) và kết thúc 18:03:37 (2026-11-11T11:03:37Z) theo Asia/Ho_Chi_Minh. Thư mục kết quả `data/backups/d87-20261111-full` (`result.json`, log, source freeze) là private, bị git bỏ qua; receipt chỉ ghi tên thư mục và các SHA-256.

## Lệnh, source và dịch vụ (2026-11-11)

Mục tiêu của chủ dự án là hoàn thành việc tồn đọng; ledger ghi rằng PASS D87 trên `dd7fac3` không còn khớp `develop` sau khi code HAR được merge. Assistant chạy theo [runbook](D87_FULL_REGRESSION_20261106_RUNBOOK.md):

1. Checkout là `develop` `7fb5999`, cây trùng `origin/develop^{tree}`. `develop` khác `production` (57 file source), nên đây là bằng chứng cho cây sẽ được promote, chưa phải cho commit đang ở `production`. `uv sync --locked --dev` chỉ cài lại package dự án.
2. Vault đang seal (container đã chạy khoảng 9 giờ). Assistant unseal bằng bootstrap file theo ủy quyền đã có của chủ dự án: ba key share được nộp trong process, không in ra. Script đọc credential trong bộ nhớ qua `../infras/scripts/vault_static_secret.py`.
3. Điều kiện rảnh như lượt `d87-20261109-full-3`: CPU logic bận dưới 0,5 trong 3 lần đo 30 giây liên tiếp. Lần chờ đầu đạt sau 390 giây; vì đã trôi qua khoảng 10 phút, assistant đo lại ngay trước khi chạy và đạt sau 90 giây (0,43 / 0,40 / 0,39). Assistant không tắt ứng dụng nào của chủ dự án. Tải trong lúc chạy (64 lần đo, gồm cả chính bộ test): trung bình 1,54, tối đa 2,49 CPU bận.
4. CORE khởi động bằng `docker compose --profile core up -d` (container `local-assistant-core-1`, image `local-assistant/llama-cuda:5c8854fd8`, health OK ở `127.0.0.1:8080`) và được dừng bằng `docker compose --profile core stop` sau lượt chạy. PostgreSQL, Vault và Qdrant không bị restart. Trước đó, CORE launcher dùng cho benchmark B2 đã được dừng và cổng 8080 trống.
5. Lệnh: `uv run --no-sync python -m scripts.full_regression data/backups/d87-20261111-full`. Script chạy `pytest tests` (không gồm `benchmarks/tests`, không loại trừ gì) và tự đặt `DATABASE_URL`, `LOCAL_ASSISTANT_LIVE_E2E=1`, `LOCAL_ASSISTANT_EMBEDDING_COMPARE_LIVE=1`.
6. Test reranker CPU (`tests/integration/test_reranker_live.py::test_actual_pinned_reranker_paired_comparison`) PASS; log không ghi thời gian từng vòng, nên lượt này không cập nhật ước tính dư địa 1–3% của nó.

## Kiểm tra database (2026-11-11)

Truy vấn read-only bằng runtime role trên database `local_assistant`, schema `assistant`, trước và sau lượt chạy cho cùng kết quả: conversations 0, messages 0, inference_runs 0, files 0, memories 0, memory_consents 0, memory_settings 0, ingestion_jobs 0, ingestion_heads 0, file_owner_usage 1, file_global_usage 1; Alembic revision `0006`. Đây là số dòng và revision, không phải so sánh từng dòng; không ghi inventory Qdrant.

## Phạm vi và ảnh hưởng (2026-11-11)

- Đây là full software regression cho cây `d5ed277` của `develop` `7fb5999`. Nếu `develop` được promote lên `staging` và `production` mà không thay đổi source thêm, cây source của `production` sẽ trùng cây đã kiểm này; mọi thay đổi source sau đó cần chạy lại D87.
- Promotion vẫn chưa làm: GitHub Actions đang bị chặn do billing của tài khoản, và promotion là quyết định của chủ dự án. D90 vẫn yêu cầu D87 trên đúng commit sẽ tag; các commit chỉ có tài liệu (ví dụ PR ghi lại lượt này) không đổi phạm vi source freeze, việc chấp nhận khác biệt đó là quyết định của chủ dự án khi điền phiếu D90.
- Không tag, không GitHub Release, không deploy. D81, D89, D90 vẫn mở; D60 hoãn.

## Lịch sử: lượt 2026-11-09 trên `production` `dd7fac3`

**Mục đích (lượt này):** Ghi kết quả full suite trên cây source của `production` `dd7fac3` (cây `5f2653d`, sau đợt promote ADR179 ngày 2026-11-09): lệnh, source, dịch vụ, lượt chưa đạt trước đó, số liệu, kiểm tra database, so sánh với CI, phạm vi và ảnh hưởng tới D90. Lượt sáng ngày 2026-11-09 trên `production` `0b67d95` và kết quả ngày 2026-10-27 được giữ nguyên ở các mục lịch sử cuối trang.

**Trạng thái lượt này: PASS — full software regression cho cây source của `production` `dd7fac3` (cây `5f2653d`), lượt thứ ba trong ngày 2026-11-09.** Lượt thứ hai trên cùng cây chưa đạt (1 FAIL ở test reranker do chạm trần CPU) và được giữ nguyên bên dưới, không bị lượt thứ ba thay thế. [Receipt công khai](../evidence/d87-20261109-production-dd7fac3-acceptance.json). Đây là bằng chứng hồi quy phần mềm cho đúng cây source này, không phải đo chất lượng model, nghiệm thu thiết bị, D89 hay quyết định release.

| Phạm vi | Kết quả thực tế (lượt thứ ba) |
|---|---|
| Toàn bộ `pytest tests` | **6.233 PASS / 0 FAIL / 0 ERROR / 0 SKIP**, exit 0, status `complete`, `accepted_full_software_regression: true` |
| Thời gian pytest | **1.830,43 giây** (summary "6233 passed, 1 warning in 1830.43s (0:30:30)"); wrapper 1.831,98 giây |
| Source snapshot | **821 file** trong `src`, `apps`, `scripts`, `tests`, `configs`, `pyproject.toml`, `uv.lock`; `source_bytes_unchanged: true` |
| Commit và cây | Checkout tách rời (detached) tại `production` `dd7fac3`, cây `5f2653d7814672b73c7d6b982b7600e63e17cea2`, trùng cây của `origin/production` |
| Source freeze SHA-256 | `c5c9ff586fe06cb266923ea8b1218b891448209d8ca62ba22c2c717d60ba08e7` (giống lượt thứ hai) |
| Log SHA-256 | `720fe50632c17a71a23ede1235e1e2a7b5ab1939553be9fec8d4db1e9421039a` |
| Cảnh báo | Summary ghi 1 warning; receipt công khai không ghi nội dung warning |
| So với full trước | 6.200 PASS trên 817 file sáng 2026-11-09 (cây `0b67d95`) nay là lịch sử; thêm 33 test (5 từ PR #46, 28 từ PR #47) và 4 file source |

Lượt thứ ba bắt đầu 17:36 (2026-11-09T10:36:26Z) và kết thúc 18:06 (2026-11-09T11:06:58Z) theo Asia/Ho_Chi_Minh. Các thư mục kết quả `data/backups/d87-20261109-full-2` và `data/backups/d87-20261109-full-3` (`result.json`, log, source freeze) là private, bị git bỏ qua và không công bố; receipt chỉ ghi tên thư mục và các SHA-256.

## Lệnh, source và dịch vụ (lượt thứ hai và thứ ba)

Sau đợt promote ADR179 (PR #48 `develop` → `staging`, `11b4020`; PR #49 `staging` → `production`, `dd7fac3`), chủ dự án yêu cầu "Chạy D87". Assistant chạy theo [runbook](D87_FULL_REGRESSION_20261106_RUNBOOK.md), với một khác biệt ở bước kiểm tra cây:

1. Lúc chạy, `develop` (`fd1a2a5`) hơn `production` một PR chỉ có tài liệu (PR #50), nên lệnh kiểm tra "develop trùng production" của runbook sẽ báo khác. Phạm vi source freeze của hai nhánh giống hệt (git diff rỗng). Vì vậy cả hai lượt chạy trên checkout tách rời tại `origin/production` `dd7fac3`; cây của checkout trùng `origin/production^{tree}`, rồi checkout được trả về `develop`. `uv sync --locked --dev` không thay đổi gì; phạm vi source sạch.
2. Vault đang ở trạng thái unseal sẵn, không cần unseal. Script đọc credential trong bộ nhớ qua `../infras/scripts/vault_static_secret.py` như thiết kế.
3. CORE khởi động bằng `docker compose --profile core up -d` trước mỗi lượt (container `local-assistant-core-1`, image `local-assistant/llama-cuda:5c8854fd8`, model `qwen3.5-9b-core` ở `127.0.0.1:8080`, health 200) và được dừng bằng `docker compose --profile core stop` sau mỗi lượt. PostgreSQL, Vault và Qdrant không bị restart.
4. Lệnh: `uv run --no-sync python -m scripts.full_regression data/backups/d87-20261109-full-2`, rồi `... data/backups/d87-20261109-full-3`. Script chạy `pytest tests` (không gồm `benchmarks/tests`, không loại trừ gì) và tự đặt `DATABASE_URL`, `LOCAL_ASSISTANT_LIVE_E2E=1`, `LOCAL_ASSISTANT_EMBEDDING_COMPARE_LIVE=1`.

## Lượt thứ hai trong ngày (lượt đầu trên cây này): chưa đạt, giữ nguyên

`data/backups/d87-20261109-full-2`, 16:48–17:20 (09:48:07Z–10:20:34Z): **6.232 PASS / 1 FAIL / 0 ERROR / 0 SKIP**, exit 1, `accepted_full_software_regression: false`, pytest 1.945,21 giây, 821 file không đổi, source freeze `c5c9ff58…` (giống lượt thứ ba), log `1f1f69f7da96baa2bcd7f6716387a224051d605c0fda137c4df46253989b8dfc`.

- Test hỏng: `tests/integration/test_reranker_live.py::test_actual_pinned_reranker_paired_comparison`, `ValueError: reranker_evaluation_failed`, log `reranker_worker_nonzero exit_code=152 completed_rounds=2`. Mã 152 = 128 + SIGXCPU (24): worker reranker chạm giới hạn CPU do chính nó đặt (480 giây soft / 481 giây hard, `scripts/qwen_reranker_worker.py`) ở vòng thứ ba trong ba vòng. Tải máy không được đo trong lượt này.
- Không liên quan ADR179: code so sánh reranker không đổi và không dùng phần sandbox ADR179 sửa. Cùng dạng lỗi với các lượt full ngày 2026-11-02 (5.836 PASS / 1 FAIL, exit 152 sau 2 vòng); khi đó ADR150 và ADR151 chỉ được duyệt cho một probe và một lượt full.
- Phân tích sau lượt chạy (không phải lượt D87, không được tính): chạy riêng test này với CORE đã dừng, trên cùng cây, đo bằng `/usr/bin/time -v`: 1 failed trong 241,94 giây, exit 152 sau 2 vòng, CPU của cả cây tiến trình 479,43 giây user + 2,29 giây system, 198% CPU. Load average 1,26 trước và 3,15 sau; tải nền gồm RustDesk, Claude desktop, k3s, GNOME Shell. Lượt sáng (cây `0b67d95`) pass test này với thời gian mỗi vòng 79,39 / 79,13 / 79,19 giây, tức ước tính khoảng 475 giây CPU cho hai luồng: dư địa chỉ khoảng 1%.
- Assistant không chạy lại để che lỗi. Chủ dự án được hỏi chọn giữa soạn ADR ghim CPU cho test reranker hoặc chạy lại khi máy rảnh, và chọn "Chạy lại khi máy rảnh".

## Lượt thứ ba: chạy lại khi máy rảnh

- Điều kiện rảnh: số CPU logic bận (tính từ `/proc/stat`) dưới 0,5 trong 3 lần đo liên tiếp, mỗi lần 30 giây, chờ tối đa 6 giờ. Máy đạt điều kiện sau 421 giây chờ (ba lần đo cuối: 0,48 / 0,38 / 0,28). Assistant không tắt ứng dụng nào của chủ dự án.
- Tải trong lúc chạy (61 lần đo, gồm cả chính bộ test): trung bình 1,49 và tối đa 2,65 CPU bận.
- Test reranker đạt, thời gian mỗi vòng 78,19 / 77,26 / 77,00 giây, mọi gate tài nguyên đạt, `adoption_authorized: false`.
- Rủi ro còn lại: khi đạt, test reranker dùng ước tính 465–475 giây trong giới hạn 480 giây CPU trên máy này (dư khoảng 1–3%), nên tải nền thông thường có thể làm nó hỏng. Lượt D87 sau cũng nên bắt đầu khi máy rảnh. Cách khắc phục bền vững (ví dụ dùng phân vùng CPU của ADR151 làm môi trường test thường trực) cần ADR riêng và chủ dự án duyệt. Giới hạn 480 giây, model, profile và thuật toán không đổi.

## Kiểm tra database sau lượt chạy

Truy vấn read-only bằng runtime role trên database `local_assistant`, sau lượt thứ hai và sau lượt thứ ba, cho cùng kết quả: conversations 0, messages 0, inference_runs 0, files 0, memories 0, memory_consents 0, memory_settings 0, ingestion_jobs 0, ingestion_heads 0, file_owner_usage 1, file_global_usage 1; Alembic revision `0006`, như trước các lượt chạy. Đây là số dòng sau test và revision, không phải so sánh từng dòng trước/sau; receipt không ghi inventory Qdrant.

## So sánh với CI

Số 6.490 của CI (run push `production` 42591324567 tại `dd7fac3`: 6.490 passed, 368 skipped, 30 deselected; artifact `local-assistant-production-dd7fac3`, 14.081.040 byte) đếm `tests` cùng `benchmarks/tests`, có mục loại trừ và không có DB/CORE; số 6.233 của D87 chỉ là `pytest tests`, không loại trừ gì, với dịch vụ thật. Hai số này không so được với nhau.

## Phạm vi và ảnh hưởng tới D90

Lượt thứ ba là bằng chứng hồi quy phần mềm cho cây source của `production` `dd7fac3` (cây `5f2653d`), gồm ADR179 (PR #47), thay đổi test timeout (PR #46), code D81 mặc định tắt, bản sửa decoder của PR #33, code voice B1/B2, ADR176 và ADR178. Đây không phải đo chất lượng model, nghiệm thu thiết bị, D89 hay quyết định release.

D87 dùng cho D90 phải chạy trên đúng nội dung của commit sẽ tag ([hồ sơ D90](D90_RELEASE_DECISION_DOSSIER.md) mục 6, [runbook D87](D87_FULL_REGRESSION_20261106_RUNBOOK.md) bước 1). Lượt này khớp `production` `dd7fac3` hiện tại. Các commit chỉ có tài liệu về sau (PR #50, PR ghi lại lượt chạy này và phiếu D90 chủ dự án sẽ điền) làm đổi cây của commit nhưng không đổi phạm vi source freeze của D87; chấp nhận khác biệt đó cho tag hay chạy lại D87 trên commit tag cuối cùng là quyết định của chủ dự án khi điền phiếu D90 (ô ngoại lệ có tên). Phiếu D90 chưa được điền ở đây. `src/**/*.py` nằm trong snapshot nguồn của bằng chứng voice B3/B4; bằng chứng đó vẫn gắn với snapshot đã ghi.

Vẫn mở hoặc không đổi: D81 vẫn OPEN (code đã merge ở trạng thái mặc định tắt và đã promote; chưa có nghiệm thu full-flow và chưa chạy native v4). D89 và D90 mở; D60 hoãn; quyết định model/voice/default/sản phẩm cho voice còn mở; voice mặc định tắt; không tag, không release, không deploy. D88 chỉ cần nếu phân phối.

## Lịch sử: lượt sáng ngày 2026-11-09 trên `production` `0b67d95`

**Trạng thái (lịch sử): PASS — full software regression cho cây source của `production` `0b67d95` (sáng 2026-11-09).** Cập nhật 2026-11-09: `production` hiện tại `dd7fac3` (cây `5f2653d`, sau PR #49) khác cây này ở `src/` và `tests/`; D87 cho cây đó ở các mục phía trên. [Receipt công khai](../evidence/d87-20261109-full-acceptance.json). Đây là bằng chứng hồi quy phần mềm cho đúng cây source này, không phải đo chất lượng model, nghiệm thu thiết bị, D89 hay quyết định release.

| Phạm vi | Kết quả thực tế |
|---|---|
| Toàn bộ `pytest tests` | **6.200 PASS / 0 FAIL / 0 ERROR / 0 SKIP**, exit 0, status `complete`, `accepted_full_software_regression: true` |
| Thời gian pytest | **1.869,85 giây** (summary "6200 passed, 1 warning in 1869.85s (0:31:09)"); wrapper 1.871,66 giây |
| Source snapshot | **817 file** trong `src`, `apps`, `scripts`, `tests`, `configs`, `pyproject.toml`, `uv.lock`; `source_bytes_unchanged: true` |
| Commit và cây | `develop` `3812e5c`, cây `0ed89bcbfad4ffafb14cea32bd27f73c63467ada`, trùng cây của `production` `0b67d95` |
| Source freeze SHA-256 | `307a312938952bbb16edae149bf58959e98bfb78dfb4966335fb89bacf1391c6` |
| Log SHA-256 | `11fdb7102c8c08c6fdd73f2cf16ae159e8b9e7ca13c448571c9c44521fb359a2` |
| Cảnh báo | Summary ghi 1 warning; receipt công khai không ghi nội dung warning |
| So với full trước | 5.889 PASS trên 750 file ngày 2026-11-03 ([receipt](../evidence/d60-fresh-20261103-final-acceptance.json)) nay là lịch sử |

Lượt chạy bắt đầu 10:31 (2026-11-09T03:31:46Z) và kết thúc 11:02 (2026-11-09T04:02:58Z) theo Asia/Ho_Chi_Minh. Thư mục kết quả `data/backups/d87-20261109-full` (`result.json`, log, source freeze) là private, bị git bỏ qua và không công bố; receipt chỉ ghi tên thư mục và các SHA-256 ở trên.

### Lệnh, source và dịch vụ (2026-11-09)

Ngày 2026-11-09 chủ dự án yêu cầu "Tiếp theo làm D81, D87 đi"; với câu hỏi về thứ tự D87, chủ dự án chọn "Sau D81 + promote (Recommended)": merge D81, promote `develop` → `staging` → `production` (không tag, không deploy), rồi chạy D87 trên commit đó. Assistant chạy D87 theo yêu cầu đó, theo [runbook](D87_FULL_REGRESSION_20261106_RUNBOOK.md):

1. Chạy từ `ai/` trên `develop` `3812e5c`; lệnh kiểm tra cây ở bước 1 của runbook in "develop trùng production". `uv sync --locked --dev` không thay đổi gì. Phạm vi source sạch: không có file sửa dở hay untracked trong `src/`, `apps/`, `scripts/`, `tests/`, `configs/`, `pyproject.toml`, `uv.lock`.
2. Vault đã bị seal lại (container chạy được khoảng 3 giờ). Assistant unseal Vault từ bootstrap file theo ủy quyền của chủ dự án ngày 2026-11-08: ba key share được nộp trong process, không in ra. Script đọc credential trong bộ nhớ qua `../infras/scripts/vault_static_secret.py` như thiết kế.
3. CORE khởi động bằng `docker compose --profile core up -d`: container `local-assistant-core-1`, image `local-assistant/llama-cuda:5c8854fd8`, model `qwen3.5-9b-core` ở `127.0.0.1:8080`, health 200. Sau lượt chạy, CORE được dừng bằng `docker compose --profile core stop`. PostgreSQL, Vault và Qdrant không bị restart.
4. Lệnh:

   ```bash
   uv run --no-sync python -m scripts.full_regression data/backups/d87-20261109-full
   ```

   Script chạy `pytest tests` (không gồm `benchmarks/tests`, không loại trừ gì) và tự đặt các biến môi trường, trong đó có `DATABASE_URL`, `LOCAL_ASSISTANT_LIVE_E2E=1`, `LOCAL_ASSISTANT_EMBEDDING_COMPARE_LIVE=1`.

Đợt merge và promote trước lượt chạy: PR #42 (D81) merge vào `develop` lúc 10:03 (2026-11-09T03:03:20Z) thành `3812e5c`; PR #43 (`develop` → `staging`) merge lúc 10:13 (2026-11-09T03:13:38Z) thành `2790b4e`; PR #44 (`staging` → `production`) merge lúc 10:30 (2026-11-09T03:30:56Z) thành `0b67d95`. Sau đợt promote, `origin/develop` (`3812e5c`) và `origin/production` (`0b67d95`) có cùng cây (kiểm bằng `git rev-parse <ref>^{tree}`). Không có tag, GitHub Release hay deploy lên Home Server; voice vẫn mặc định tắt.

### Kiểm tra database sau lượt chạy

Truy vấn read-only bằng runtime role trên database `local_assistant` sau lượt chạy: conversations 0, messages 0, inference_runs 0, files 0, memories 0, memory_consents 0, memory_settings 0, ingestion_jobs 0, ingestion_heads 0, file_owner_usage 1 (dòng giá trị 0 có từ trước), file_global_usage 1 (dòng bộ đếm bằng 0); Alembic revision `0006`, như trước lượt chạy. Đây là số dòng sau test và revision, không phải phép so sánh từng dòng trước/sau như audit ngày 2026-10-27; receipt này cũng không ghi inventory Qdrant.

### So sánh với CI

CI và D87 đo hai thứ khác nhau. Số 6.456 của CI đếm `tests` cùng `benchmarks/tests`, có 39 mục loại trừ và không có DB/CORE; số 6.200 của D87 chỉ là `pytest tests`, không loại trừ gì, với dịch vụ thật. Hai số này không so được với nhau.

Run push lên `production` (run 42556825440, commit `0b67d95`) thành công: job chính 6.456 passed, 368 skipped, 31 deselected; job cách ly thành công; `package` tạo artifact `local-assistant-production-0b67d95` (14.017.331 byte). Trong đợt promote, run push lên `staging` (run 42555210293, commit `2790b4e`) lỗi ở lần đầu: 1 failed, 6.455 passed, tại `tests/test_pdf_extractor.py::test_real_timeout_reaps_worker` (marker của worker bị treo vẫn thấy trong một `/proc/*/cmdline` ngay sau khi reap do timeout). Cùng commit đã pass ở PR run 42554274811, và lần chạy lại các job lỗi thành công. Lỗi này cùng dạng với test đã cách ly `tests/test_page_ocr.py::test_timeout_reaps_worker_and_descendant`; test PDF chưa có trong `.github/ci/hosted-runner-quarantine.txt` và chưa có gì được sửa. Việc tiếp theo có thể làm: thêm test này vào danh sách cách ly (PR cấu hình CI) hoặc làm chắc phần kiểm tra reap.

Cập nhật 2026-11-09 (sau lượt chạy): chủ dự án chọn cách thứ hai ("Làm cách 2 đi"). Trên nhánh `fix/timeout-reap-tests` (tách từ `develop` `2912f00`), test PDF này và `tests/test_page_ocr.py::test_timeout_reaps_worker_and_descendant` không còn kiểm tra `/proc` ngay sau timeout mà cho phép một cửa sổ dọn có giới hạn 5 giây sau khi lời gọi trả về (`reap_survivors` trong `tests/process_probe.py` chờ hết cửa sổ, rồi SIGKILL và mô tả tiến trình còn sót; 5 test riêng trong `tests/test_process_probe.py`); tiến trình treo của probe ngủ 30 giây, nên tiến trình nào còn sau 5 giây vẫn là rò rỉ thật. Đây là kiểm tra yếu hơn kiểm tra tức thời cũ: ở nhánh timeout, code production trả về khi `bwrap` ngoài cùng đã bị SIGKILL và được reap, trước khi PID namespace được dọn, nên worker có thể còn chạy vài mili giây sau khi lời gọi trả về và vẫn giữ bản dup của file descriptor được mượn; lỗi trên `staging` khớp với cơ chế này. Rủi ro nhỏ (trong sandbox, SIGKILL đã chờ sẵn, cửa sổ vài mili giây) và không do thay đổi này gây ra, nhưng ba docstring production (`extract_reader`, `NativeImageNormalizer.normalize`, `prepare_page`) ghi tính chất mạnh hơn ở nhánh timeout. Ứng viên việc theo sau ở production, chưa làm và cần chủ dự án quyết định: chờ (có giới hạn) init của namespace thoát sau timeout rồi mới raise, hoặc sửa lời ba docstring đó. (Cùng ngày đã làm bằng ADR179/PR #47, nay trên `production` `dd7fac3`.) Test OCR được gỡ khỏi danh sách cách ly, danh sách nay rỗng, và job cách ly báo thành công khi không có test nào được chọn (pytest exit 5 chỉ được coi là thành công khi danh sách không có mục nào; một mục cũ hoặc gõ sai vẫn làm job hỏng; job vẫn không chặn). Chỉ đổi test và CI; `src/infrastructure/pdf_extractor.py` và `src/infrastructure/page_ocr.py` không đổi. Kiểm chứng cục bộ: 58 passed trên 3 file test liên quan; với code cuối cùng, hai test timeout đạt 30/30 lượt khi pytest bị ghim vào 2 CPU đang bị hai vòng lặp bận chiếm (kiểm tra tức thời cũ không chạy cùng điều kiện, nên đây không phải phép tái hiện trước/sau). Khoảng trống có từ trước, không đổi: không test timeout nào kiểm tra rằng worker hay tiến trình con bị treo đã tồn tại trước khi bị kill.

### Phạm vi và ảnh hưởng tới D90

Lượt này là bằng chứng hồi quy phần mềm cho cây source của `production` `0b67d95`, gồm code D81 mặc định tắt, bản sửa decoder của PR #33, code voice B1/B2, ADR176 và ADR178. Đây không phải đo chất lượng model, nghiệm thu thiết bị, D89 hay quyết định release.

D87 dùng cho D90 phải chạy trên đúng nội dung của commit sẽ tag ([hồ sơ D90](D90_RELEASE_DECISION_DOSSIER.md) mục 6, [runbook D87](D87_FULL_REGRESSION_20261106_RUNBOOK.md) bước 1). Lượt này khớp `production` `0b67d95` cho tới PR #49 (09:10 UTC ngày 2026-11-09). Mọi commit chỉ có tài liệu về sau (kể cả PR ghi lại lượt chạy này và phiếu D90 chủ dự án đã điền) làm đổi cây của commit, nhưng không đổi phạm vi source freeze của D87 (src, apps, scripts, tests, configs, pyproject.toml, uv.lock). Chấp nhận khác biệt chỉ có tài liệu đó cho tag, hay chạy lại D87 trên commit tag cuối cùng, là quyết định của chủ dự án khi điền phiếu D90 (phiếu có ô ngoại lệ có tên). Phiếu D90 chưa được điền ở đây.

Cập nhật 2026-11-09 (sau lượt chạy): phạm vi source freeze của D87 gồm `tests/`, nên thay đổi test ở mục "So sánh với CI" (`tests/process_probe.py` và `tests/test_process_probe.py` mới, `tests/test_pdf_extractor.py` và `tests/test_page_ocr.py` sửa) không phải khác biệt chỉ ở tài liệu. Lượt PASS ngày 2026-11-09 vẫn là bằng chứng cho cây `production` `0b67d95`, nhưng sau khi thay đổi này vào `develop` thì không còn khớp cây source của `develop`. D87 dùng cho tag phải chạy trên cây cuối cùng của commit sẽ tag, hoặc chủ dự án chấp nhận khác biệt đó bằng ô ngoại lệ có tên trong phiếu D90, đúng như caveat ở trên. Code production không đổi. Phạm vi nguồn B3/B4 của voice chỉ gồm `tests/test_main_voice*` và `tests/main_voice*` trong số các file thuộc `tests/`, nên không bị ảnh hưởng.

Cập nhật 2026-11-09 (ADR179): theo câu trả lời “Làm luôn” của chủ dự án, nhánh `fix/sandbox-namespace-teardown` sửa code production để các chỗ gọi sandbox tài liệu và media chỉ trả quyền điều khiển sau khi PID namespace của sandbox đã được dọn ([ADR179](../ADR/179-retire-sandbox-namespace-before-timeout-returns.md)); các test timeout nay kiểm tra chặt bằng pidfd ngay lúc lời gọi trả về. Thay đổi này nằm trong cả `src/` và `tests/`, tức trong phạm vi source freeze của D87, nên lượt PASS sáng ngày 2026-11-09 chỉ là bằng chứng cho cây `production` `0b67d95` (sau đó D87 đã chạy trên `dd7fac3`, xem ghi chú về lượt đó). D87 dùng cho tag phải chạy trên cây cuối cùng của commit sẽ tag, hoặc chủ dự án ghi ngoại lệ có tên trong phiếu D90. `src/**/*.py` cũng nằm trong snapshot nguồn của bằng chứng voice B3/B4; bằng chứng đó vẫn gắn với snapshot đã ghi.

Cập nhật 2026-11-09 (promote ADR179): theo câu trả lời “Promote luôn” của chủ dự án, `develop` (`0e2d6b7`, gồm #45, #46, #47) đã lên `staging` qua PR #48 (`11b4020`) và lên `production` qua PR #49 (`dd7fac3`); mọi run CI của PR và push đều đạt với pytest chính 6.490 passed (lần đầu của PR #48 chỉ hỏng ở bước `apt` của test-python: cả ba lần `apt-get update` nhận HTTP 403 từ packages.microsoft.com, pytest chưa chạy; chạy lại các job hỏng thì đạt). Sau PR #49 ba nhánh có cùng cây `5f2653d`; khi PR tài liệu này vào `develop`, `develop` đi trước `production` chỉ bằng tài liệu. Không tag, không GitHub Release, không deploy lên Home Server; nhánh `production` nay có code ADR179 (report export fail closed với `export_cleanup_uncertain`), còn những gì đang chạy trên Home Server không đổi. Lượt D87 PASS ngày 2026-11-09 vẫn chỉ là bằng chứng cho cây `production` cũ `0b67d95`; D87 dùng cho tag phải chạy trên cây hiện tại (hoặc cây cuối cùng của commit sẽ tag nếu có thay đổi sau đó), hoặc chủ dự án ghi ngoại lệ có tên trong phiếu D90.

Vẫn mở hoặc không đổi: D81 vẫn OPEN (code đã merge ở trạng thái mặc định tắt và đã promote; chưa có nghiệm thu full-flow và chưa chạy native v4). D89 và D90 mở; D60 hoãn; quyết định model/voice/default/sản phẩm cho voice còn mở; voice mặc định tắt; không tag, không release, không deploy. D88 chỉ cần nếu phân phối.

## Lịch sử: kết quả ngày 2026-10-27

Phần dưới đây là nội dung hiện hành của trang này trước ngày 2026-11-09, giữ nguyên làm lịch sử; các trạng thái "còn mở" trong đó là trạng thái lúc ấy. Sau lượt này còn các full 5.837 PASS trên 745 file (ngày 2026-11-02) và 5.889 PASS trên 750 file (ngày 2026-11-03, [receipt](../evidence/d60-fresh-20261103-final-acceptance.json)), trước lượt 2026-11-09; cả hai cũng là lịch sử.

**Mục đích:** Ghi kết quả full suite ngày 2026-10-27, phạm vi source, kiểm tra bảo toàn sau test và các gate còn mở.

**Trạng thái: VERIFIED — full software regression.** [Terminal và audit receipt](../evidence/d87-current-20261027-full-acceptance.json), [preflight trước lượt chạy](../evidence/d87-current-20261027-preflight.json).

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

### Điều kiện chạy và cleanup

Sau reboot, máy không có native worker và Vault đã initialized nhưng sealed. Operator unseal đúng Vault hiện có bằng bootstrap material đã lưu, chỉ đọc credential vào bộ nhớ; không init/rotate hoặc sửa policy. Vault được giữ unsealed và thay đổi trạng thái này được ghi trong audit.

Supervisor dùng đúng CORE/model/projector/context hiện có tại cổng 8080, fixture umask 0022, log/metadata riêng tư và một process group sở hữu riêng. CORE exit 0, đã reap, guard failure null; full runner cũng exit 0 và đã join. Sau cleanup, cùng boot, cùng 15 container identities/images/ports và native=0 như baseline đầu lượt chạy.

Peak RSS của toàn CORE worker là 8.081.632 KiB, khoảng **7,71 GiB RAM**; sampled peak VRAM **8.910 MiB**. Đây là hai phép đo khác nhau, không phải virtual address-space cap hoặc tổng bộ nhớ cả máy.

Lỗi gọi trực tiếp private script thiếu import `scripts` được giữ trong log. Lỗi xảy ra trước khi có worker hoặc thư mục full suite. Cách gọi được sửa bằng runpy từ `ai/`, không sửa application source hoặc chạy lại một full đã thất bại. [Protocol và lệnh thực thi](D87_FULL_REGRESSION_PROTOCOL.md#current-reboot-aware-run--2026-10-27).

### Kiểm tra dữ liệu sau suite

Đối chiếu read-only với snapshot chụp trước test: schema 0006, security/owners/ACL và 11 bảng khác giữ nguyên. Chỉ `assistant.file_global_usage.updated_at` thay đổi do upload/delete test; complete singleton row vẫn 0 byte, 0 file, 0 active upload. Vì vậy **strict all-row equality=False**, còn qualified preservation=True. Không restore timestamp, chạy restore probe hoặc chuẩn hóa để giấu thay đổi.

Authenticated Qdrant inventory sau test rỗng. Không có authenticated collection snapshot cùng boot trước suite, nên receipt chỉ khẳng định inventory sau test; không bịa một phép so sánh trước/sau. Restore probe count=0, không còn app connection/pending inference khi audit. 916/917 older protected files khớp byte; ngoại lệ duy nhất là thay đổi tài liệu MODEL_REGISTRY đã được duyệt từ trước. Toàn bộ 176 original inputs và worksheet D70 chưa nghe giữ nguyên.

### Phạm vi hoàn tất và việc tiếp theo

D87 current-source software refresh hoàn tất. D14 selected semantic path vẫn VERIFIED_LOCAL_OPT_IN trên fresh 42/42 mỗi profile; mọi điểm FAIL/composite cũ được giữ nguyên. Full software PASS không tự phê duyệt tích hợp API/default hoặc chất lượng coding/web rộng hơn.

D70 nghe thực tế vẫn **0/24 owner-deferred**; [hướng dẫn nghe](D70_MANUAL_LISTENING_TEST.md) đã sẵn sàng. D74 voice/model/license/no-speech, D81 product integration, D86/D89 product/device acceptance, các gate D88 liên quan model/license và D90 release vẫn mở theo [ledger](OUTSTANDING_WORK_STATUS.md). Không push, tag, deploy hoặc tuyên bố toàn dự án hoàn thành.

Root `AGENTS.md` untracked và dòng IDE riêng đầu devlog được giữ nguyên, ngoài commit và ZIP D87. Gói đầy đủ sau commit: `data/backups/local-assistant-d87-20261027-full-files.zip`, kèm receipt và manifest. Gói giữ các artifact lịch sử theo SHA, full phiên bản file Git và operator/test/log được chọn rõ; không chứa weights, SDK, secret, dump hay checkpoint.

Đóng gói phát hiện thêm sáu CE003 latest pointers do `tests/test_coding_feedback_oracles.py` cập nhật trong full suite. Đã đối chiếu từng target summary/SHA: frozen oracle PASS, hai native check, 0 model attempt; đây không phải thay đổi first model score. Builder đầu từ chối trước khi tạo ZIP và log được giữ. Policy cuối chỉ chấp nhận đúng12CE002+6CE003pointer, giữ byte archive cũ và ghi riêng SHA workspace; mọi immutable extra khác phải khớp.43delivery controls PASS/0SKIP/0,58 giây, gồm chặn pointer giả/unknown/archive hỏng/target có model call và active builder stdout.
